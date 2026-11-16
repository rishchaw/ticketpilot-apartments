"""Optional Firestore persistence; ADC and transactions, with no AWS dependency changes.

The collections separate legacy demo tickets, apartment concerns and settings so
recent-record queries need only the automatic created_at index.
"""
from __future__ import annotations
from functools import lru_cache
import os

LEGACY_COLLECTION = "ticketpilot_tickets"
APARTMENT_COLLECTION = "ticketpilot_apartment_tickets"
SETTINGS_COLLECTION = "ticketpilot_apartment_settings"


class Conflict(Exception):
    """The document no longer matches the caller's expected version."""


@lru_cache(maxsize=1)
def client():
    # Import only for STORAGE_MODE=firestore. Cloud Run uses its attached identity;
    # local development uses ADC or the explicitly configured emulator.
    from google.cloud import firestore
    return firestore.Client(
        project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
        database=os.getenv("FIRESTORE_DATABASE", "(default)"),
    )


def _document(collection: str, record_id: str):
    if not isinstance(record_id, str) or not record_id or "/" in record_id:
        raise ValueError("Document ID must be a nonempty single path component")
    return client().collection(collection).document(record_id)


def _read(reference):
    snapshot = reference.get()
    return {**snapshot.to_dict(), "id": snapshot.id} if snapshot.exists else None


def _recent(collection: str, limit: int):
    query = client().collection(collection).order_by("created_at", direction="DESCENDING").limit(limit)
    return [{**snapshot.to_dict(), "id": snapshot.id} for snapshot in query.stream()]


def _run_transaction(operation):
    from google.cloud import firestore
    return firestore.transactional(operation)(client().transaction())


def legacy_upsert(record: dict):
    _document(LEGACY_COLLECTION, record["id"]).set(record)


def legacy_get(record_id: str):
    return _read(_document(LEGACY_COLLECTION, record_id))


def legacy_recent(limit: int):
    return _recent(LEGACY_COLLECTION, limit)


def legacy_delete(record_id: str) -> bool:
    reference = _document(LEGACY_COLLECTION, record_id)
    def remove(transaction):
        if not reference.get(transaction=transaction).exists:
            return False
        transaction.delete(reference)
        return True
    return _run_transaction(remove)


def _apartment_collection(record_id: str) -> str:
    return SETTINGS_COLLECTION if record_id == "apartment_notice" else APARTMENT_COLLECTION


def apartment_get(record_id: str):
    return _read(_document(_apartment_collection(record_id), record_id))


def apartment_recent(limit: int):
    return _recent(APARTMENT_COLLECTION, limit)


def apartment_save(record: dict, expected_version: int | None):
    reference = _document(_apartment_collection(record["id"]), record["id"])
    def write(transaction):
        # Read before writing: Firestore retries the entire transaction if another
        # writer changes the document. A retry rechecks the application version.
        snapshot = reference.get(transaction=transaction)
        if expected_version is None:
            if snapshot.exists:
                raise Conflict("Document already exists")
        elif not snapshot.exists or snapshot.to_dict().get("version") != expected_version:
            raise Conflict("Record changed; refresh before saving")
        transaction.set(reference, record)
    _run_transaction(write)
