"""FastAPI backend for the podcast studio demo.

Serves the static workflow UI, exposes the Polly voice list, streams pipeline
progress over Server-Sent Events, and serves the generated MP3.

Run:
    uvicorn server:app --reload
    # optional: AWS_PROFILE=<name> uvicorn server:app --reload
"""

import json
from pathlib import Path

import boto3
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import orchestrator
import store
from polly_audio import list_voices

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
AUDIO_DIR = BASE_DIR / "_audio"

# Honours AWS_PROFILE / standard credential chain.
session = boto3.Session()

app = FastAPI(title="Polly Podcast Studio")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


@app.get("/voices")
def voices(newscaster: bool = False) -> JSONResponse:
    return JSONResponse(list_voices(session, newscaster=newscaster))


@app.get("/history")
def history() -> JSONResponse:
    return JSONResponse(store.list_sessions(session))


@app.get("/run/{run_id}")
def run(run_id: str) -> JSONResponse:
    data = store.get_run(session, run_id)
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


@app.delete("/run/{run_id}")
def delete_run(run_id: str) -> JSONResponse:
    store.delete_run(session, run_id)
    # Best-effort removal of the generated audio file.
    path = (AUDIO_DIR / f"{run_id}.mp3").resolve()
    if str(path).startswith(str(AUDIO_DIR.resolve())) and path.exists():
        path.unlink()
    return JSONResponse({"deleted": run_id})


@app.get("/audio/{name}")
def audio(name: str) -> FileResponse:
    # name is "<run_id>.mp3"; reject path traversal.
    path = (AUDIO_DIR / name).resolve()
    if not str(path).startswith(str(AUDIO_DIR.resolve())) or not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/stream")
async def stream(
    topic: str = Query(...),
    host_name: str = Query("Alex"),
    cohost_name: str = Query("Sam"),
    host_voice: str = Query(...),
    cohost_voice: str = Query(...),
    newscaster: bool = Query(False),
) -> StreamingResponse:
    async def event_source():
        async for event in orchestrator.run(
            session,
            topic=topic,
            host_name=host_name,
            cohost_name=cohost_name,
            host_voice=host_voice,
            cohost_voice=cohost_voice,
            newscaster=newscaster,
            audio_dir=AUDIO_DIR,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
