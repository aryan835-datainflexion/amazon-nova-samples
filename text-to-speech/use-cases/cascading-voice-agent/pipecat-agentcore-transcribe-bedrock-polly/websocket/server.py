"""
Pipecat AgentCore cascading voice agent server.

FastAPI owns the AgentCore-compatible HTTP/WebSocket endpoints. The Pipecat
pipeline lives in bot.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime

import requests
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bot import run_bot


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_credential_refresh_task: asyncio.Task | None = None


def get_imdsv2_token() -> str | None:
    try:
        response = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            timeout=2,
        )
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


def get_credentials_from_imds() -> dict:
    result = {"success": False, "credentials": None, "role_name": None, "error": None}
    try:
        token = get_imdsv2_token()
        headers = {"X-aws-ec2-metadata-token": token} if token else {}
        role_response = requests.get(
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            headers=headers,
            timeout=2,
        )
        if role_response.status_code != 200:
            result["error"] = f"Failed to retrieve IAM role: HTTP {role_response.status_code}"
            return result

        role_name = role_response.text.strip()
        creds_response = requests.get(
            f"http://169.254.169.254/latest/meta-data/iam/security-credentials/{role_name}",
            headers=headers,
            timeout=2,
        )
        if creds_response.status_code != 200:
            result["error"] = f"Failed to retrieve credentials: HTTP {creds_response.status_code}"
            return result

        creds = creds_response.json()
        result.update(
            {
                "success": True,
                "role_name": role_name,
                "credentials": {
                    "AccessKeyId": creds.get("AccessKeyId"),
                    "SecretAccessKey": creds.get("SecretAccessKey"),
                    "Token": creds.get("Token"),
                    "Expiration": creds.get("Expiration"),
                },
            }
        )
    except Exception as exc:
        result["error"] = str(exc)
    return result


async def refresh_credentials_from_imds() -> None:
    while True:
        try:
            result = get_credentials_from_imds()
            if result["success"]:
                creds = result["credentials"]
                os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
                os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
                os.environ["AWS_SESSION_TOKEN"] = creds["Token"]
                expiration = datetime.fromisoformat(creds["Expiration"].replace("Z", "+00:00"))
                now = datetime.now(expiration.tzinfo)
                await asyncio.sleep(min(max((expiration - now).total_seconds() - 300, 60), 3600))
            else:
                logger.warning("Credential refresh skipped: %s", result["error"])
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Credential refresh error: %s", exc)
            await asyncio.sleep(300)


app = FastAPI(title="Pipecat AgentCore Cascading Voice Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    global _credential_refresh_task
    logger.info("Starting Pipecat AgentCore cascading voice agent")
    logger.info("AWS region: %s", os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        logger.info("Using AWS credentials from environment")
        return

    result = get_credentials_from_imds()
    if result["success"]:
        creds = result["credentials"]
        os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = creds["Token"]
        _credential_refresh_task = asyncio.create_task(refresh_credentials_from_imds())
        logger.info("Loaded AWS credentials from IMDS role %s", result["role_name"])
    else:
        logger.warning("No IMDS credentials loaded: %s", result["error"])


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if _credential_refresh_task and not _credential_refresh_task.done():
        _credential_refresh_task.cancel()
        try:
            await _credential_refresh_task
        except asyncio.CancelledError:
            pass


@app.get("/ping")
async def ping() -> JSONResponse:
    return JSONResponse({"status": "Healthy", "time_of_last_update": int(time.time())})


@app.post("/invocations")
async def invocations(_request: dict) -> JSONResponse:
    return JSONResponse(
        {
            "message": (
                "This sample uses Pipecat's FastAPI WebSocket transport for an "
                "AgentCore Runtime cascading voice pipeline: Transcribe -> Bedrock -> Polly."
            ),
            "websocket_endpoint": "/ws",
            "client_protocol": "Pipecat WebSocket transport with ProtobufFrameSerializer",
            "available_voices": ["Tiffany", "Matthew", "Joanna", "Ruth", "Gregory", "Ivy"],
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await run_bot(websocket)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
