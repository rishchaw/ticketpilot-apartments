"""Apartment documents, isolated from legacy tickets; optimistic writes prevent lost updates."""
import json
from ticketpilot import storage


class Conflict(Exception):
    pass


def save(record: dict, expected_version: int | None = None) -> dict:
    record = {**record, "version": (expected_version or 0) + 1}
    if storage.mode() == "firestore":
        from ticketpilot import firestore_store
        try:
            firestore_store.apartment_save(record, expected_version)
        except firestore_store.Conflict as exc:
            raise Conflict("Record changed; refresh before saving") from exc
    elif storage.mode() == "dynamodb":
        from boto3.dynamodb.conditions import Attr
        table = storage._dynamodb()
        condition = Attr("id").not_exists() if expected_version is None else Attr("version").eq(expected_version)
        try:
            table.put_item(Item=record, ConditionExpression=condition)
        except table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise Conflict("Record changed; refresh before saving") from exc
    elif storage.mode() == "sqlite":
        with storage._sql() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS apartment_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, queue TEXT NOT NULL)")
            if expected_version is None:
                changed = conn.execute("INSERT OR IGNORE INTO apartment_records VALUES (?, ?, ?, ?, ?)",
                    (record["id"], json.dumps(record), record["version"], record["created_at"], record["queue"])).rowcount
            else:
                changed = conn.execute("UPDATE apartment_records SET payload=?, version=? WHERE id=? AND version=?",
                    (json.dumps(record), record["version"], record["id"], expected_version)).rowcount
            if not changed:
                raise Conflict("Record changed; refresh before saving")
            conn.commit()
    else:
        raise RuntimeError("Apartment persistence is disabled")
    return record


def get(record_id: str) -> dict | None:
    if storage.mode() == "firestore":
        from ticketpilot import firestore_store
        return firestore_store.apartment_get(record_id)
    if storage.mode() == "dynamodb":
        item = storage._dynamodb().get_item(Key={"id": record_id}, ConsistentRead=True).get("Item")
        return {**storage._native(item), "queue": item["queue"]} if item else None
    if storage.mode() == "sqlite":
        with storage._sql() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS apartment_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, queue TEXT NOT NULL)")
            row = conn.execute("SELECT payload FROM apartment_records WHERE id=?", (record_id,)).fetchone()
            return json.loads(row[0]) if row else None
    return None


def recent(limit: int = 200) -> list[dict]:
    limit = max(1, min(limit, 200))
    if storage.mode() == "firestore":
        from ticketpilot import firestore_store
        return firestore_store.apartment_recent(limit)
    if storage.mode() == "dynamodb":
        from boto3.dynamodb.conditions import Key
        result = storage._dynamodb().query(IndexName="recent-tickets", KeyConditionExpression=Key("queue").eq("apartment_tickets"), ScanIndexForward=False, Limit=limit)
        return [storage._native(item) for item in result.get("Items", [])]
    if storage.mode() == "sqlite":
        with storage._sql() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS apartment_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, queue TEXT NOT NULL)")
            rows = conn.execute("SELECT payload FROM apartment_records WHERE queue='apartment_tickets' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [json.loads(row[0]) for row in rows]
    return []
