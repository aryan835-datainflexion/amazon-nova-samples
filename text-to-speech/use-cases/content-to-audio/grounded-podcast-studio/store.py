"""DynamoDB store — the single source of truth for every run.

Layout (single table, on-demand billing):

    PK = SESSION#<run_id>   SK = META            -> topic, timestamp, status,
                                                    and each stage's artifacts
                                                    (sources / script / report /
                                                    synthesis) as JSON strings
    PK = SESSION#<run_id>   SK = FACT#000, ...   -> one source-backed claim

Claims stay as individual FACT# items so the fact-checker can Query them
exactly. The larger stage artifacts are stored as JSON attributes on the META
item, which lets the History pane reload a past run in one GetItem. Listing
runs is a small Scan filtered to META items (fine at demo volume).
"""

import json
import time
from decimal import Decimal

from boto3.dynamodb.conditions import Attr, Key

import settings


def _table(session):
    return session.resource("dynamodb", region_name=settings.AGENT_REGION).Table(
        settings.DDB_TABLE
    )


def _meta_key(run_id: str) -> dict:
    return {"PK": f"SESSION#{run_id}", "SK": "META"}


def start_session(session, run_id: str, topic: str) -> None:
    _table(session).put_item(
        Item={
            **_meta_key(run_id),
            "topic": topic,
            "created_at": Decimal(int(time.time())),
            "status": "running",
        }
    )


def save_artifact(session, run_id: str, key: str, value) -> None:
    """Persist a stage's output (list/dict/number) onto the META item as JSON."""
    _table(session).update_item(
        Key=_meta_key(run_id),
        UpdateExpression="SET #k = :v",
        ExpressionAttributeNames={"#k": key},
        ExpressionAttributeValues={":v": json.dumps(value)},
    )


def put_facts(session, run_id: str, facts: list[dict]) -> None:
    """Write source-backed claims containing subject, predicate, object,
    type, and source URL."""
    table = _table(session)
    with table.batch_writer() as batch:
        for i, fact in enumerate(facts):
            batch.put_item(
                Item={
                    "PK": f"SESSION#{run_id}",
                    "SK": f"FACT#{i:03d}",
                    "subject": fact.get("subject", ""),
                    "predicate": fact.get("predicate", ""),
                    "object": fact.get("object", ""),
                    "type": fact.get("type", ""),
                    "source_url": fact.get("source_url", ""),
                }
            )


def get_facts(session, run_id: str) -> list[dict]:
    """Return all source-backed claims for a run."""
    response = _table(session).query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{run_id}")
        & Key("SK").begins_with("FACT#")
    )
    return [
        {
            "subject": it.get("subject", ""),
            "predicate": it.get("predicate", ""),
            "object": it.get("object", ""),
            "type": it.get("type", ""),
            "source_url": it.get("source_url", ""),
        }
        for it in response.get("Items", [])
    ]


def finish_session(session, run_id: str, status: str = "done") -> None:
    _table(session).update_item(
        Key=_meta_key(run_id),
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )


def list_sessions(session, limit: int = 100) -> list[dict]:
    """Return run summaries, newest first (Scan filtered to META items)."""
    response = _table(session).scan(FilterExpression=Attr("SK").eq("META"))
    items = response.get("Items", [])
    items.sort(key=lambda i: int(i.get("created_at", 0)), reverse=True)
    return [
        {
            "run_id": it["PK"].split("#", 1)[1],
            "topic": it.get("topic", ""),
            "created_at": int(it.get("created_at", 0)),
            "status": it.get("status", ""),
        }
        for it in items[:limit]
    ]


def delete_run(session, run_id: str) -> None:
    """Delete a run's META item and all its FACT# items."""
    table = _table(session)
    items = table.query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{run_id}")
    ).get("Items", [])
    with table.batch_writer() as batch:
        for it in items:
            batch.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})


def _load_json(meta: dict, key: str, default):
    raw = meta.get(key)
    return json.loads(raw) if raw else default


def get_run(session, run_id: str) -> dict | None:
    """Return the full stored run (all stage artifacts + facts), or None."""
    meta = _table(session).get_item(Key=_meta_key(run_id)).get("Item")
    if not meta:
        return None
    return {
        "run_id": run_id,
        "topic": meta.get("topic", ""),
        "status": meta.get("status", ""),
        "created_at": int(meta.get("created_at", 0)),
        "sources": _load_json(meta, "sources", []),
        "facts": get_facts(session, run_id),
        "script": _load_json(meta, "script", []),
        "report": _load_json(meta, "report", {}),
        "synthesis": _load_json(meta, "synthesis", {}),
    }
