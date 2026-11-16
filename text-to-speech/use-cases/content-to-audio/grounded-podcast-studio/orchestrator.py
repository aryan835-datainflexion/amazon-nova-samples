"""Pipeline orchestrator.

Runs the five stages in order and yields events describing each stage's
progress. Blocking work (agent/model calls and Polly) runs in a worker thread
so the event loop stays free to flush Server-Sent Events to the browser.

Event shape:  {"stage": <name>, "status": "started"|"done"|"error", "data": {...}}
Stages:       research → extraction → script → factcheck → synthesis
"""

import asyncio
import uuid
from pathlib import Path

import store
from agents import entity_extraction, fact_check, research, script_writer
from polly_audio import synthesize


def _event(stage: str, status: str, data: dict | None = None) -> dict:
    return {"stage": stage, "status": status, "data": data or {}}


async def run(
    session,
    topic: str,
    host_name: str,
    cohost_name: str,
    host_voice: str,
    cohost_voice: str,
    newscaster: bool,
    audio_dir: Path,
):
    run_id = uuid.uuid4().hex[:12]
    yield _event("run", "started", {"run_id": run_id, "topic": topic})

    try:
        store.start_session(session, run_id, topic)

        # 1. Research -------------------------------------------------------
        yield _event("research", "started")
        sources = await asyncio.to_thread(research.research, topic)
        store.save_artifact(session, run_id, "sources", sources)
        yield _event("research", "done", {"sources": sources})

        # 2. Entity extraction ---------------------------------------------
        yield _event("extraction", "started")
        facts = await asyncio.to_thread(
            entity_extraction.extract_and_store, session, run_id, sources
        )
        yield _event("extraction", "done", {"facts": facts})

        # 3. Script writing -------------------------------------------------
        yield _event("script", "started")
        script = await asyncio.to_thread(
            script_writer.write_script, session, topic, facts, host_name, cohost_name
        )
        store.save_artifact(session, run_id, "script", script)
        yield _event("script", "done", {"script": script})

        # 4. Fact / entity check -------------------------------------------
        yield _event("factcheck", "started")
        report = await asyncio.to_thread(fact_check.check, session, run_id, script)
        store.save_artifact(session, run_id, "report", report)
        yield _event("factcheck", "done", {"report": report})

        # 5. Speech synthesis (no agent — reuses the base sample) ----------
        yield _event("synthesis", "started")
        voices = {"host": host_voice, "cohost": cohost_voice}
        audio, characters = await asyncio.to_thread(
            synthesize, session, script, voices, newscaster
        )
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / f"{run_id}.mp3").write_bytes(audio)
        synthesis = {
            "audio_url": f"/audio/{run_id}.mp3",
            "characters": characters,
            "bytes": len(audio),
        }
        store.save_artifact(session, run_id, "synthesis", synthesis)
        yield _event("synthesis", "done", synthesis)

        store.finish_session(session, run_id, "done")
        yield _event("run", "done", {"run_id": run_id})

    except Exception as e:  # surface the failing stage to the UI
        try:
            store.finish_session(session, run_id, "error")
        except Exception:
            pass
        yield _event("run", "error", {"error": f"{type(e).__name__}: {e}"})
