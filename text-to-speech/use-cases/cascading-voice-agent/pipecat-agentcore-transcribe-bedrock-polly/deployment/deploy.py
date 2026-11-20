#!/usr/bin/env python3
"""
Deploy the Pipecat cascading voice agent to Amazon Bedrock AgentCore Runtime.

Self-contained version of the aws-samples deployment script, scoped to this one
sample. It:

  1. Creates (or updates) an IAM execution role for the agent runtime.
  2. Leaves MCP Gateway wiring disabled for now; the flag is reserved for a
     future tool-calling pass.
  3. Launches the agent (websocket/server.py) onto AgentCore Runtime using the
     bedrock-agentcore-starter-toolkit (CodeBuild by default — no local Docker
     required).
  4. Writes setup_config.json (used by start_client.sh and cleanup.py).

Usage:
    export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    python deploy.py                        # deploy with defaults (no gateway)
    python deploy.py --region us-west-2
    python deploy.py --with-gateway         # reserved; currently deploys without a gateway
    python deploy.py --local-build          # build the image locally (needs Docker)
"""

import argparse
import json
import os
import sys
import subprocess
import shutil
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

if sys.version_info < (3, 10):
    print("ERROR: This deployment requires Python 3.10 or newer.")
    print("Recreate the virtual environment with:")
    print("  deactivate 2>/dev/null || true")
    print("  rm -rf .venv")
    print("  python3.10 -m venv .venv")
    print("  source .venv/bin/activate")
    print("  pip install -r deployment/requirements.txt")
    sys.exit(1)

import boto3
import yaml
from bedrock_agentcore_starter_toolkit.operations.runtime.launch import launch_bedrock_agentcore


DEFAULT_AGENT_NAME = "pipecat_cascading_voice_agent"
IAM_ROLE_NAME = "PipecatCascadingVoiceAgentRole"


class Colors:
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    NC = "\033[0m"


class AgentCoreDeployer:
    """Deploys the cascading voice agent to Amazon Bedrock AgentCore Runtime."""

    def __init__(self, args: argparse.Namespace):
        self.args = args

        # deployment/ lives inside the sample folder; the sample root is its parent.
        self.deploy_dir = Path(__file__).parent
        self.sample_dir = self.deploy_dir.parent
        self.websocket_path = self.sample_dir / "websocket"

        if not self.websocket_path.exists():
            self._error(f"websocket/ folder not found at: {self.websocket_path}")
            sys.exit(1)

        self.aws_region = args.region or os.getenv("AWS_REGION", "us-east-1")
        self.account_id = args.account_id or os.getenv("ACCOUNT_ID")
        self.agent_name = args.agent_name or DEFAULT_AGENT_NAME

        if not self.account_id:
            self._error("ACCOUNT_ID is required. Set via --account-id or the ACCOUNT_ID env var.")
            sys.exit(1)

        self.config_file = self.sample_dir / "setup_config.json"

    # --- pretty printing ---------------------------------------------------

    def _print(self, message: str, color: str = Colors.NC):
        print(f"{color}{message}{Colors.NC}")

    def _error(self, message: str):
        self._print(f"❌ {message}", Colors.RED)

    def _success(self, message: str):
        self._print(f"✅ {message}", Colors.GREEN)

    def _info(self, message: str):
        self._print(f"ℹ️  {message}", Colors.BLUE)

    def _warning(self, message: str):
        self._print(f"⚠️  {message}", Colors.YELLOW)

    def _run_command(self, cmd: list, check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=check)
        except subprocess.CalledProcessError as e:
            self._error(f"Command failed: {' '.join(cmd)}")
            self._error(f"Error: {e.stderr}")
            if check:
                raise
            return e

    # --- prerequisites -----------------------------------------------------

    def check_prerequisites(self):
        self._print("\n📋 Checking prerequisites...", Colors.YELLOW)
        required_tools = {
            "python3": "Python 3.10+",
            "aws": "AWS CLI",
            "agentcore": "bedrock-agentcore-starter-toolkit",
        }
        missing = [f"{t} ({d})" for t, d in required_tools.items() if not shutil.which(t)]
        if missing:
            self._error("Missing required tools:")
            for t in missing:
                print(f"  - {t}")
            print("\nInstall with:")
            print("  pip install -r requirements.txt")
            sys.exit(1)
        self._success("All prerequisites met")

    # --- MCP Gateway (optional) -------------------------------------------

    def deploy_mcp_gateway(self) -> Optional[Dict]:
        """Create an MCP Gateway + Lambda target. Only when --with-gateway is set."""
        if self.args.with_gateway:
            self._warning(
                "MCP Gateway wiring is not implemented for this Pipecat AgentCore sample yet; "
                "continuing without a gateway."
            )
            return None
        if not self.args.with_gateway:
            self._info("Skipping MCP Gateway (use --with-gateway to create one)")
            return None

        from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

        self._print("\n🌐 Deploying MCP Gateway...", Colors.YELLOW)
        client = GatewayClient(region_name=self.aws_region)
        bedrock_client = boto3.client("bedrock-agentcore-control", region_name=self.aws_region)

        gateway_name = "cascading-voice-agent-tools"
        mcp_server = "anybank-tools"
        tools = ["get_account_balance", "get_recent_transactions", "get_mortgage_rates"]

        gateway = None
        try:
            for gw in bedrock_client.list_gateways().get("items", []):
                if gw.get("name") == gateway_name:
                    self._info(f"Found existing gateway: {gateway_name} ({gw['gatewayId']})")
                    gateway = bedrock_client.get_gateway(gatewayIdentifier=gw["gatewayId"])
                    break
        except Exception as e:
            self._warning(f"Could not check for existing gateway: {e}")

        if not gateway:
            self._info(f"Creating {gateway_name} gateway...")
            gateway = client.create_mcp_gateway(name=gateway_name)

        gateway_id = gateway["gatewayId"]
        self._success(f"Gateway ready: {gateway_id}")
        self._info(f"   URL: {gateway['gatewayUrl']}")

        try:
            target = client.create_mcp_gateway_target(
                gateway=gateway, name=mcp_server, target_type="lambda", target_payload=None
            )
            self._success(f"MCP Server target created: {target['targetId']}")
        except Exception as e:
            if "already exists" in str(e).lower() or "conflict" in str(e).lower():
                self._warning("MCP Server target already exists, continuing...")
                items = bedrock_client.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
                target = items[0] if items else {}
            else:
                raise

        deployed = [{
            "gateway_name": gateway_name,
            "gateway_id": gateway_id,
            "gateway_arn": gateway["gatewayArn"],
            "gateway_url": gateway["gatewayUrl"],
            "role_arn": gateway["roleArn"],
            "target_id": target.get("targetId", "unknown"),
            "mcp_server_name": mcp_server,
            "tools": tools,
        }]

        gateway_config = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deployment_type": "mcp-gateway",
            "gateways": deployed,
            "aws": {"account_id": self.account_id, "region": self.aws_region},
        }
        with open(self.sample_dir / "gateway_config.json", "w") as f:
            json.dump(gateway_config, f, indent=2)
        self._success("Gateway configuration saved to gateway_config.json")
        return {"gateways": deployed}

    # --- IAM role ----------------------------------------------------------

    def create_iam_role(self) -> str:
        self._print("\n🔐 Creating IAM role...", Colors.YELLOW)
        role_name = IAM_ROLE_NAME

        agent_role_path = self.deploy_dir / "agent_role.json"
        trust_policy_path = self.deploy_dir / "trust_policy.json"
        if not agent_role_path.exists() or not trust_policy_path.exists():
            self._error("Policy files not found (agent_role.json, trust_policy.json)")
            sys.exit(1)

        with open(agent_role_path) as f:
            agent_role_policy = f.read().replace("${ACCOUNT_ID}", self.account_id)

        # If role already exists, refresh its inline policy and return.
        check = self._run_command(["aws", "iam", "get-role", "--role-name", role_name], check=False)
        if check.returncode == 0:
            role_arn = json.loads(check.stdout)["Role"]["Arn"]
            self._info(f"IAM role {role_name} already exists — updating policy")
            self._run_command([
                "aws", "iam", "put-role-policy", "--role-name", role_name,
                "--policy-name", f"{role_name}Policy", "--policy-document", agent_role_policy,
            ])
            self._success(f"Updated policy on existing role: {role_arn}")
            return role_arn

        self._run_command([
            "aws", "iam", "create-role", "--role-name", role_name,
            "--assume-role-policy-document", f"file://{trust_policy_path}", "--output", "json",
        ])
        self._success("Role created")

        self._run_command([
            "aws", "iam", "put-role-policy", "--role-name", role_name,
            "--policy-name", f"{role_name}Policy", "--policy-document", agent_role_policy,
        ])
        self._success("Policy attached")

        result = self._run_command(["aws", "iam", "get-role", "--role-name", role_name, "--output", "json"])
        role_arn = json.loads(result.stdout)["Role"]["Arn"]
        self._success(f"IAM role created: {role_arn}")

        self._info("Waiting 10 seconds for IAM role to propagate...")
        time.sleep(10)
        return role_arn

    # --- agent runtime -----------------------------------------------------

    def deploy_agent(self, role_arn: str, gateway_info: Optional[Dict]) -> Dict:
        self._print("\n🚀 Deploying agent to AgentCore Runtime...", Colors.YELLOW)

        original_dir = Path.cwd()
        os.chdir(self.websocket_path)
        try:
            config_path = Path(".bedrock_agentcore.yaml")
            if config_path.exists():
                config_path.unlink()

            config = {
                "agents": {
                    self.agent_name: {
                        "name": self.agent_name,
                        "entrypoint": "server.py",
                        "runtime": "python3.12",
                        "aws": {
                            "account": self.account_id,
                            "region": self.aws_region,
                            "execution_role": role_arn,
                            "ecr_auto_create": True,
                        },
                    }
                },
                "default_agent": self.agent_name,
                "region": self.aws_region,
            }

            env_vars: Dict[str, str] = {}
            if gateway_info and gateway_info.get("gateways"):
                gateways = gateway_info["gateways"]
                env_vars["MCP_GATEWAY_ARNS"] = json.dumps([g["gateway_arn"] for g in gateways])
                env_vars["MCP_GATEWAY_URLS"] = json.dumps([g["gateway_url"] for g in gateways])
                self._info(f"Added MCP Gateway env vars for {len(gateways)} gateway(s)")

            if env_vars:
                config["agents"][self.agent_name]["environment_variables"] = env_vars

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
            self._success(f"Configuration created: {config_path}")

            local = self.args.local
            use_codebuild = not self.args.local_build
            if local:
                self._info("Deploying with local mode (requires Docker)")
            elif not use_codebuild:
                self._info("Deploying with local build mode (requires Docker)")
            else:
                self._info("Deploying with CodeBuild (no Docker required)")

            self._info("Launching agent (this may take a few minutes)...")
            result = launch_bedrock_agentcore(
                config_path=config_path,
                agent_name=self.agent_name,
                local=local,
                use_codebuild=use_codebuild,
                env_vars=env_vars,
                auto_update_on_conflict=True,
            )

            agent_arn = result.agent_arn
            agent_id = result.agent_id
            if not agent_arn:
                raise RuntimeError("Failed to get agent ARN from deployment result")

            self._success("Agent deployed successfully!")
            self._info(f"   Agent ARN: {agent_arn}")
            self._info(f"   Agent ID:  {agent_id}")

            # The toolkit may not re-apply env vars on updates; force-set them.
            if env_vars:
                try:
                    self._info("Updating runtime environment variables...")
                    boto3.client("bedrock-agentcore-control", region_name=self.aws_region).update_agent_runtime(
                        agentRuntimeId=agent_id, environmentVariables=env_vars
                    )
                    self._success(f"Environment variables updated ({len(env_vars)} vars)")
                except Exception as e:
                    self._warning(f"Failed to update env vars (may already be set): {e}")

            return {"agent_arn": agent_arn, "agent_runtime_name": self.agent_name, "role_arn": role_arn}
        finally:
            os.chdir(original_dir)

    # --- persistence + summary --------------------------------------------

    def save_configuration(self, deployment_info: Dict):
        self._print("\n💾 Saving configuration...", Colors.YELLOW)
        config = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sample": "pipecat-agentcore-transcribe-bedrock-polly",
            "aws_region": self.aws_region,
            "account_id": self.account_id,
            "agent_name": self.agent_name,
            "agent_runtime_name": deployment_info["agent_runtime_name"],
            "agent_arn": deployment_info["agent_arn"],
            "iam_role_arn": deployment_info["role_arn"],
            "iam_role_name": IAM_ROLE_NAME,
            "deployment_method": "agentcore-starter-toolkit",
        }
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        self._success(f"Configuration saved to {self.config_file}")

    def print_summary(self, deployment_info: Dict):
        self._print("\n" + "=" * 80, Colors.GREEN)
        self._print("✅ Deployment Complete!", Colors.GREEN)
        self._print("=" * 80, Colors.GREEN)
        print(f"\n   Account ID:  {self.account_id}")
        print(f"   Region:      {self.aws_region}")
        print(f"   Agent Name:  {deployment_info['agent_runtime_name']}")
        print(f"   Agent ARN:   {deployment_info['agent_arn']}")
        print(f"   IAM Role:    {deployment_info['role_arn']}")
        print(f"\n{Colors.YELLOW}Next steps:{Colors.NC}")
        print("   1. Start the client:   ./deployment/start_client.sh")
        print("   2. When done, clean up: python deployment/cleanup.py")
        self._print("=" * 80 + "\n", Colors.GREEN)

    # --- orchestration -----------------------------------------------------

    def deploy(self):
        try:
            self._print("\n🚀 AgentCore Deployment — cascading voice agent", Colors.BLUE)
            self.check_prerequisites()
            gateway_info = self.deploy_mcp_gateway()
            role_arn = self.create_iam_role()
            deployment_info = self.deploy_agent(role_arn, gateway_info)
            if gateway_info:
                deployment_info["gateway"] = gateway_info
            self.save_configuration(deployment_info)
            self.print_summary(deployment_info)
        except KeyboardInterrupt:
            self._error("\nDeployment cancelled by user")
            sys.exit(1)
        except Exception as e:
            self._error(f"Deployment failed: {e}")
            traceback.print_exc()
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy the cascading voice agent to Amazon Bedrock AgentCore Runtime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--account-id", help="AWS Account ID (or set ACCOUNT_ID env var)")
    parser.add_argument("--region", help="AWS Region (default: us-east-1 or AWS_REGION env var)")
    parser.add_argument("--agent-name", help=f"Custom agent name (default: {DEFAULT_AGENT_NAME})")
    parser.add_argument("--local", action="store_true", help="Build and run locally (requires Docker)")
    parser.add_argument("--local-build", action="store_true", help="Build locally, deploy to cloud (requires Docker)")
    parser.add_argument(
        "--with-gateway",
        action="store_true",
        help="Reserved for future MCP Gateway tool wiring; currently deploys without a gateway",
    )
    args = parser.parse_args()
    AgentCoreDeployer(args).deploy()


if __name__ == "__main__":
    main()
