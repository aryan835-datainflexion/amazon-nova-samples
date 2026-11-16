"""Command-line entry point for the Reachy voice assistant.

Usage::

    python app.py                 # run with config.yaml
    python app.py --robot fake    # run without hardware
    python app.py --check         # non-network preflight (imports, creds, config)

Anything that pulls in pipecat (``run_voicebot``) or the robot SDK is imported
lazily inside the run/check paths, so ``--check`` can *report* a missing import
gracefully instead of crashing at module load.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys

from voicebot.config import load_config


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="reachy-voice-assistant",
        description="All-AWS voice assistant for the Reachy Mini robot.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML config file (default: config.yaml).",
    )
    parser.add_argument(
        "--robot",
        choices=["reachy", "fake"],
        default=None,
        help="Robot backend override (default: use the value from config).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a non-network preflight check and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


def _try_import(module: str) -> bool:
    """Return True if ``module`` imports cleanly, printing an OK/MISSING line."""

    try:
        importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 - report any import failure
        print(f"  [MISSING] {module}: {exc}")
        return False
    print(f"  [OK]      {module}")
    return True


def run_checks(cfg) -> int:
    """Lightweight, non-network preflight. Return 0 if OK, 1 otherwise.

    Verifies the Python version, the importability of the pipecat services this
    sample depends on, the presence of AWS credential signals, and prints the
    resolved model/voice/region/backend. Makes no AWS or daemon network calls.
    """

    ok = True

    print("Reachy voice assistant -- preflight check")
    print()

    # --- Python version ---------------------------------------------------
    py = sys.version_info
    print(f"Python: {py.major}.{py.minor}.{py.micro}")
    if (py.major, py.minor) not in {(3, 11), (3, 12)}:
        print("  [WARN]    expected Python 3.11 or 3.12; other versions are untested.")

    # --- Required imports -------------------------------------------------
    print("Imports:")
    required = [
        "pipecat",
        "pipecat.services.aws.stt",
        "pipecat.services.aws.tts",
        "pipecat.services.aws.llm",
        "pipecat.transports.local.audio",
    ]
    for module in required:
        ok = _try_import(module) and ok

    # The reachy-mini SDK is only needed for the real backend; missing is a
    # warning, not a failure.
    if cfg.robot.backend == "reachy":
        try:
            importlib.import_module("reachy_mini")
            print("  [OK]      reachy_mini")
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN]    reachy_mini: {exc} (needed for the 'reachy' backend)")

    # --- AWS credential signals (no network calls) ------------------------
    print("AWS:")
    region = os.getenv("AWS_REGION") or cfg.region
    if region:
        print(f"  [OK]      region resolved: {region}")
    else:
        print("  [MISSING] no region set (AWS_REGION or config aws.region).")
        ok = False

    if os.getenv("AWS_ACCESS_KEY_ID"):
        print("  [OK]      AWS_ACCESS_KEY_ID present in environment.")
    else:
        print(
            "  [NOTE]    AWS_ACCESS_KEY_ID not set; relying on SSO, an instance "
            "role, or a shared profile via the default credential chain."
        )

    # --- Resolved configuration -------------------------------------------
    print("Configuration:")
    print(f"  model:   {cfg.llm.model_id}")
    print(f"  voice:   {cfg.tts.voice} ({cfg.tts.engine})")
    print(f"  region:  {region}")
    print(f"  backend: {cfg.robot.backend}")

    print()
    print("Preflight:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv=None) -> int:
    """Parse arguments, configure logging, and run (or check) the assistant."""

    args = build_arg_parser().parse_args(argv)

    cfg = load_config(args.config)
    if args.robot:
        cfg.robot.backend = args.robot

    level = logging.DEBUG if args.debug else getattr(logging, cfg.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level)

    if args.check:
        return run_checks(cfg)

    # Lazy imports: keep pipecat/SDK off the module-load path so --check works
    # even when those packages are missing or broken.
    from voicebot.robot import make_robot
    from voicebot.pipeline import run_voicebot

    import asyncio

    robot = make_robot(cfg)
    try:
        asyncio.run(run_voicebot(cfg, robot))
    except KeyboardInterrupt:
        print("\nGoodbye!")
        return 0
    finally:
        robot.close()
    return 0
