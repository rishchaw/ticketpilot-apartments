"""SQLite locally, DynamoDB in AWS; bounded queue queries avoid table scans."""
from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any
from decimal import Decimal

PATH = Path(os.getenv("SQLITE_PATH", "data/operations.db"))
COLUMNS = ("id", "title", "text", "predicted_category", "assigned_team", "confidence", "priority",
           "status", "requires_human_review", "review_reason", "suggested_answer", "answer_mode",
           "sources", "created_at", "updated_at", "resolved_at")

def mode() -> str:
    value = os.getenv("STORAGE_MODE", "sqlite").strip().lower()
    if value not in {"sqlite", "dynamodb", "none"}:
        raise ValueError("STORAGE_MODE must be sqlite, dynamodb or none")
    return value

@contextmanager
def _sql():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL,
        predicted_category TEXT NOT NULL, assigned_team TEXT NOT NULL,
        confidence REAL NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL,
        requires_human_review INTEGER NOT NULL, review_reason TEXT,
        suggested_answer TEXT NOT NULL, answer_mode TEXT NOT NULL,
        sources TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, resolved_at TEXT
    )""")
    try:
        yield conn
    finally:
        conn.close()

@lru_cache(maxsize=1)
def _dynamodb():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["DYNAMODB_TABLE"])


def _native(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _native(v) for k, v in value.items() if k != "queue"}
    if isinstance(value, list):
        return [_native(v) for v in value]
    return value

def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["requires_human_review"] = bool(out.get("requires_human_review", False))
    if isinstance(out.get("sources"), str):
        out["sources"] = json.loads(out["sources"])
    return out

def upsert(item: dict) -> dict:
    if mode() == "none":
        return item
    item = _decode(item)
    if mode() == "dynamodb":
        record = json.loads(json.dumps({**item, "queue": "tickets"}), parse_float=Decimal)
        _dynamodb().put_item(Item=record)
    else:
        record = dict(item)
        record["requires_human_review"] = int(record["requires_human_review"])
        record["sources"] = json.dumps(record["sources"])
        with _sql() as c:
            c.execute("INSERT OR REPLACE INTO tickets (" + ",".join(COLUMNS) + ") VALUES (" + ",".join("?" for _ in COLUMNS) + ")",
                      [record.get(k) for k in COLUMNS])
            c.commit()
    return item

def recent(limit: int = 50) -> list[dict]:
    limit = min(max(int(limit), 1), 200)
    if mode() == "none":
        return []
    if mode() == "dynamodb":
        from boto3.dynamodb.conditions import Key
        response = _dynamodb().query(
            IndexName="recent-tickets", KeyConditionExpression=Key("queue").eq("tickets"),
            ScanIndexForward=False, Limit=limit,
        )
        return [_decode(_native(v)) for v in response.get("Items", [])]
    with _sql() as c:
        values = c.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_decode(dict(v)) for v in values]

def get(ticket_id: str) -> dict | None:
    if mode() == "none":
        return None
    if mode() == "dynamodb":
        item = _dynamodb().get_item(Key={"id": ticket_id}, ConsistentRead=True).get("Item")
        return _decode(_native(item)) if item else None
    with _sql() as c:
        row = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return _decode(dict(row)) if row else None

def delete(ticket_id: str) -> bool:
    if mode() == "none":
        return False
    if mode() == "dynamodb":
        return bool(_dynamodb().delete_item(Key={"id": ticket_id}, ReturnValues="ALL_OLD").get("Attributes"))
    with _sql() as c:
        c.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
        changed = c.execute("SELECT changes()").fetchone()[0] > 0
        c.commit()
        return changed

def summary(items: list[dict]) -> dict:
    """Finite recent-record sample. Not a full production historical aggregation."""
    n = len(items)
    by_team, by_priority, by_status = {}, {}, {}
    for t in items:
        for dest, key in ((by_team, t["assigned_team"]), (by_priority, t["priority"]), (by_status, t["status"])):
            dest[key] = dest.get(key, 0) + 1
    return {
        "sample_size": n,
        "scope": "most recent 200 stored tickets (not lifetime totals)",
        "by_team": by_team, "by_priority": by_priority, "by_status": by_status,
        "requires_review": sum(bool(t["requires_human_review"]) for t in items),
        "review_rate": round(sum(bool(t["requires_human_review"]) for t in items) / n, 3) if n else 0,
        "avg_confidence": round(sum(float(t["confidence"]) for t in items) / n, 3) if n else 0,
        "resolved": by_status.get("resolved", 0),
    }
