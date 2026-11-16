#!/usr/bin/env python3
"""
Tear down the AgentCore resources created by deploy.py for this sample.

Deletes, in order:
  1. The AgentCore agent runtime (via `agentcore destroy` when available, else the
     bedrock-agentcore-control API).
  2. The MCP Gateway + targets (only if gateway_config.json exists).
  3. The IAM execution role and its inline policy.
  4. The local setup_config.json / gateway_config.json state files.

Usage:
    python cleanup.py
    python cleanup.py --region us-west-2
"""

import argparse
import json
import os
import sys
import subprocess
import time
from pathlib import Path


class Colors:
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    NC = "\033[0m"


class AgentCoreCleanup:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.deploy_dir = Path(__file__).parent
        self.sample_dir = self.deploy_dir.parent
        self.websocket_path = self.sample_dir / "websocket"
        self.config_file = self.sample_dir / "setup_config.json"
        self.gateway_config_file = self.sample_dir / "gateway_config.json"
        self.config = None
        self.gateway_config = None

    def _print(self, message: str, color: str = Colors.NC):
        print(f"{color}{message}{Colors.NC}")

    def _error(self, message: str):
        self._print(f"❌ {message}", Colors.RED)

    def _success(self, message: str):
        self._print(f"✅ {message}", Colors.GREEN)

    def _info(self, message: str):
        self._print(f"ℹ️  {message}", Colors.YELLOW)

    def _run_command(self, cmd: list, check: bool = False) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=check)
        except subprocess.CalledProcessError as e:
            if check:
                self._error(f"Command failed: {' '.join(cmd)}")
                self._error(f"Error: {e.stderr}")
            return e

    @property
    def region(self) -> str:
        if self.args.region:
            return self.args.region
        if self.config and self.config.get("aws_region"):
            return self.config["aws_region"]
        return os.getenv("AWS_REGION", "us-east-1")

    # --- config ------------------------------------------------------------

    def load_configuration(self):
        if self.config_file.exists():
            with open(self.config_file) as f:
                self.config = json.load(f)
            self._success(f"Loaded {self.config_file}")
        else:
            self._info(f"No configuration file at {self.config_file}")

        if self.gateway_config_file.exists():
            with open(self.gateway_config_file) as f:
                self.gateway_config = json.load(f)
            self._success(f"Loaded {self.gateway_config_file}")

    # --- agent runtime -----------------------------------------------------

    def _agentcore_destroy(self) -> bool:
        """Prefer the toolkit's `agentcore destroy` when a config file is present."""
        if not self._which("agentcore"):
            return False
        if not (self.websocket_path / ".bedrock_agentcore.yaml").exists():
            return False
        original_dir = Path.cwd()
        os.chdir(self.websocket_path)
        try:
            self._info("Running agentcore destroy...")
            result = self._run_command(["agentcore", "destroy", "--force"], check=False)
            if result.returncode == 0:
                self._success("AgentCore resources destroyed via toolkit")
                return True
            self._info("agentcore destroy did not succeed, falling back to API")
            return False
        finally:
            os.chdir(original_dir)

    def _which(self, name: str) -> bool:
        return self._run_command(["which", name], check=False).returncode == 0

    def delete_agent_runtime(self):
        if not self.config or "agent_arn" not in self.config:
            self._info("No agent ARN found, skipping agent runtime deletion")
            return
        agent_id = self.config["agent_arn"].split("/")[-1]
        self._print(f"\n🤖 Deleting agent runtime: {agent_id}", Colors.YELLOW)

        check_cmd = [
            "aws", "bedrock-agentcore-control", "get-agent-runtime",
            "--agent-runtime-id", agent_id, "--region", self.region,
        ]
        if self._run_command(check_cmd, check=False).returncode != 0:
            self._info("Agent runtime not found or already deleted")
            return

        delete_cmd = [
            "aws", "bedrock-agentcore-control", "delete-agent-runtime",
            "--agent-runtime-id", agent_id, "--region", self.region,
        ]
        if self._run_command(delete_cmd, check=False).returncode == 0:
            self._success("Agent runtime deleted")
        else:
            self._error("Agent runtime deletion failed")

    # --- IAM ---------------------------------------------------------------

    def delete_iam_role(self):
        role_name = None
        if self.config:
            role_name = self.config.get("iam_role_name") or (
                self.config.get("iam_role_arn", "").split("/")[-1] or None
            )
        role_name = role_name or "CascadingVoiceAgentRole"
        self._print(f"\n🔐 Deleting IAM role: {role_name}", Colors.YELLOW)

        r = self._run_command([
            "aws", "iam", "delete-role-policy", "--role-name", role_name,
            "--policy-name", f"{role_name}Policy",
        ], check=False)
        self._success("Role policy deleted") if r.returncode == 0 else self._info("Policy already gone")

        r = self._run_command(["aws", "iam", "delete-role", "--role-name", role_name], check=False)
        self._success("IAM role deleted") if r.returncode == 0 else self._info("Role already gone")

    # --- gateway -----------------------------------------------------------

    def delete_gateway(self):
        if not self.gateway_config:
            self._info("\nNo gateway configuration found, skipping gateway cleanup")
            return
        gateways = self.gateway_config.get("gateways", [])
        if not gateways:
            return
        try:
            import boto3
            client = boto3.client("bedrock-agentcore-control", region_name=self.region)
        except Exception as e:
            self._error(f"Could not create boto3 client: {e}")
            return

        for gw in gateways:
            gateway_id = gw.get("gateway_id")
            if not gateway_id:
                continue
            self._print(f"\n🌐 Deleting MCP Gateway: {gateway_id}", Colors.YELLOW)
            try:
                for target in client.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", []):
                    try:
                        client.delete_gateway_target(gatewayIdentifier=gateway_id, targetId=target["targetId"])
                        self._success(f"Target {target['targetId']} deleted")
                    except Exception as e:
                        self._info(f"Target deletion skipped: {e}")
                time.sleep(5)
                client.delete_gateway(gatewayIdentifier=gateway_id)
                self._success("MCP Gateway deleted")
            except Exception as e:
                if "ResourceNotFoundException" in str(e) or "not found" in str(e).lower():
                    self._info("Gateway already deleted")
                else:
                    self._error(f"Gateway deletion failed: {e}")

    # --- state files -------------------------------------------------------

    def delete_state_files(self):
        for f in (self.config_file, self.gateway_config_file):
            if f.exists():
                f.unlink()
                self._success(f"Deleted {f.name}")

    # --- orchestration -----------------------------------------------------

    def cleanup(self):
        try:
            self._print("\n🧹 Cleaning up cascading voice agent resources...", Colors.YELLOW)
            self.load_configuration()

            if not self._agentcore_destroy():
                self.delete_agent_runtime()

            self.delete_gateway()
            self.delete_iam_role()
            self.delete_state_files()

            self._print("\n" + "=" * 70, Colors.GREEN)
            self._success("Cleanup complete!")
            self._print("=" * 70 + "\n", Colors.GREEN)
        except KeyboardInterrupt:
            self._error("\nCleanup cancelled by user")
            sys.exit(1)
        except Exception as e:
            self._error(f"Cleanup failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Clean up AgentCore resources for the cascading voice agent")
    parser.add_argument("--region", help="AWS Region (defaults to setup_config.json / AWS_REGION)")
    AgentCoreCleanup(parser.parse_args()).cleanup()


if __name__ == "__main__":
    main()
