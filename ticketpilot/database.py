"""Legacy local SQLite utilities; AWS runtime persistence uses storage.py."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "data/triage.db"))


def enabled() -> bool:
    return os.getenv("STORAGE_MODE", "sqlite").lower() == "sqlite"


def connect():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(SQLITE_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS tickets (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       text TEXT NOT NULL,
       team TEXT NOT NULL,
       priority TEXT NOT NULL,
       confidence REAL NOT NULL,
       needs_review INTEGER NOT NULL,
       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    return db


def save_ticket(text: str, team: str, priority: str, confidence: float, needs_review: bool) -> int | None:
    if not enabled():
        return None
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO tickets (text, team, priority, confidence, needs_review) VALUES (?, ?, ?, ?, ?)",
            (text, team, priority, confidence, int(needs_review)),
        )
        db.commit()
        return int(cursor.lastrowid)


def recent_tickets(limit: int = 15) -> list[dict]:
    if not enabled():
        return []
    with connect() as db:
        rows = db.execute(
            "SELECT id, text, team, priority, confidence, needs_review, created_at "
            "FROM tickets ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 50),)
        ).fetchall()
        return [dict(row) for row in rows]
