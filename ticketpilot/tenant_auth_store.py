"""Private versioned authentication records; never mixed with concern collections.

Logical IDs are namespaced separately on DynamoDB and use a dedicated collection
or SQL table elsewhere. No auth record has the concern GSI key attributes. TTL is
optional housekeeping; the auth layer always checks expiry itself.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
from threading import local
from ticketpilot import storage

COLLECTION = "ticketpilot_tenant_auth"
PREFIX = "tenant_auth#"
_runtime = local()


class Conflict(Exception):
    """The supplied version no longer identifies the current record."""


class Unavailable(Exception):
    """Authentication persistence failed; callers must fail closed."""


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", value):
        raise ValueError("Invalid authentication record identifier")
    return value


def _table():
    # Resources are thread-local rather than shared between FastAPI worker threads.
    import boto3
    from botocore.config import Config
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    name = os.environ["DYNAMODB_TABLE"]
    key = (region, name, os.getenv("AWS_PROFILE"))
    if getattr(_runtime, "key", None) != key:
        session = boto3.Session(region_name=region)
        _runtime.table = session.resource("dynamodb", config=Config(
            connect_timeout=3, read_timeout=5, retries={"mode": "standard", "total_max_attempts": 3},
            ignore_configured_endpoint_urls=True)).Table(name)
        _runtime.key = key
    return _runtime.table


def _sql_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS tenant_auth_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL)")


def _reference(record_id):
    from ticketpilot.firestore_store import client
    return client().collection(COLLECTION).document(record_id)


def _get(record_id):
    mode = storage.mode()
    if mode == "sqlite":
        with storage._sql() as conn:
            _sql_schema(conn)
            row = conn.execute("SELECT payload FROM tenant_auth_records WHERE id=?", (record_id,)).fetchone()
            return json.loads(row[0]) if row else None
    if mode == "dynamodb":
        item = _table().get_item(Key={"id": PREFIX + record_id}, ConsistentRead=True).get("Item")
        if not item:
            return None
        item = storage._native(item)
        item["id"] = record_id
        return item
    if mode == "firestore":
        snapshot = _reference(record_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    raise Unavailable("Tenant authentication persistence is disabled")


def get(record_id):
    record_id = _identifier(record_id)
    try:
        value = _get(record_id)
        if value is not None and (not isinstance(value, dict) or value.get("id") != record_id or type(value.get("version")) is not int or value["version"] < 1):
            raise Unavailable("Authentication record is invalid")
        return value
    except (Conflict, Unavailable):
        raise
    except Exception as exc:
        raise Unavailable("Tenant authentication persistence is unavailable") from exc


def _put(record_id, record, expected_version):
    mode = storage.mode()
    if mode == "sqlite":
        with storage._sql() as conn:
            _sql_schema(conn)
            if expected_version is None:
                changed = conn.execute("INSERT OR IGNORE INTO tenant_auth_records VALUES (?, ?, ?)",
                    (record_id, json.dumps(record), record["version"])).rowcount
            else:
                changed = conn.execute("UPDATE tenant_auth_records SET payload=?, version=? WHERE id=? AND version=?",
                    (json.dumps(record), record["version"], record_id, expected_version)).rowcount
            if changed != 1:
                raise Conflict("Authentication record changed")
            conn.commit()
    elif mode == "dynamodb":
        from boto3.dynamodb.conditions import Attr
        table = _table()
        condition = Attr("id").not_exists() if expected_version is None else Attr("version").eq(expected_version)
        try:
            table.put_item(Item={**record, "id": PREFIX + record_id}, ConditionExpression=condition)
        except table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise Conflict("Authentication record changed") from exc
    elif mode == "firestore":
        from ticketpilot.firestore_store import _run_transaction
        reference = _reference(record_id)
        def write(transaction):
            snapshot = reference.get(transaction=transaction)
            if expected_version is None:
                if snapshot.exists:
                    raise Conflict("Authentication record changed")
            elif not snapshot.exists or snapshot.to_dict().get("version") != expected_version:
                raise Conflict("Authentication record changed")
            transaction.set(reference, record)
        _run_transaction(write)
    else:
        raise Unavailable("Tenant authentication persistence is disabled")


def put_if_version(record_id, record, expected_version=None):
    record_id = _identifier(record_id)
    if expected_version is not None and (type(expected_version) is not int or expected_version < 1):
        raise ValueError("Expected version must be a positive integer")
    if not isinstance(record, dict) or "queue" in record or "created_at" in record:
        raise ValueError("Authentication records cannot use concern index keys")
    value = {**record, "id": record_id, "version": (expected_version or 0) + 1}
    if len(json.dumps(value).encode("utf-8")) > 32768:
        raise ValueError("Authentication record exceeds its size limit")
    try:
        _put(record_id, value, expected_version)
    except (Conflict, Unavailable):
        raise
    except Exception as exc:
        raise Unavailable("Tenant authentication persistence is unavailable") from exc
    return value


def _delete(record_id, expected_version):
    mode = storage.mode()
    if mode == "sqlite":
        with storage._sql() as conn:
            _sql_schema(conn)
            changed = conn.execute("DELETE FROM tenant_auth_records WHERE id=? AND version=?", (record_id, expected_version)).rowcount
            conn.commit()
            return changed == 1
    if mode == "dynamodb":
        from boto3.dynamodb.conditions import Attr
        table = _table()
        try:
            table.delete_item(Key={"id": PREFIX + record_id}, ConditionExpression=Attr("version").eq(expected_version))
            return True
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
    if mode == "firestore":
        from ticketpilot.firestore_store import _run_transaction
        reference = _reference(record_id)
        def remove(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists or snapshot.to_dict().get("version") != expected_version:
                return False
            transaction.delete(reference)
            return True
        return _run_transaction(remove)
    raise Unavailable("Tenant authentication persistence is disabled")


def delete(record_id, expected_version):
    record_id = _identifier(record_id)
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("Expected version must be a positive integer")
    try:
        return _delete(record_id, expected_version)
    except (Conflict, Unavailable):
        raise
    except Exception as exc:
        raise Unavailable("Tenant authentication persistence is unavailable") from exc
