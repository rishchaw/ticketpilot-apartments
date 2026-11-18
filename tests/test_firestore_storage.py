"""Firestore adapter/HTTP tests with an isolated API fake, not a real database.

The fake makes local transaction callbacks atomic to exercise application version
logic. Firestore emulator/service testing is still required to verify SDK/server
retry and transaction behavior end to end.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock

import pytest
import httpx
from fastapi.testclient import TestClient
from ticketpilot.api import app
from ticketpilot import apartment_store, apartments, firestore_store, storage, tenant_auth, tenant_auth_store

OWNER = {"X-Admin-Token": "firestore-test-owner"}
APARTMENT = {"unit": "1", "category": "water", "title": "No water", "description": "Walang tubig sa kusina mula ngayong umaga.", "language": "fil"}
LEGACY = {"title": "Production API outage", "text": "Production API down with HTTP 503 server errors for every customer."}

TENANT_PASSWORD = "synthetic-tenant-passphrase-only"


def seed_test_tenants():
    accounts = {}
    for index in range(1, 9):
        unit = str(index)
        account = tenant_auth.new_user("unit-" + unit, unit, password=TENANT_PASSWORD + unit)
        tenant_auth_store.put_if_version("user:" + account["username"], account)
        accounts[unit] = account
    tenant_auth_store.put_if_version("registry", {"kind": "tenant_registry", "status": "ready", "slots": [
        {key: account[key] for key in ("tenant_id", "username", "unit")} for account in accounts.values()]})
    return accounts


def as_tenant(client, unit="1"):
    sessions = getattr(client, "_tenant_test_sessions", {})
    if unit not in sessions:
        client.cookies.clear()
        response = client.post("/api/tenant/login", headers={"X-TicketPilot-Login": "1"},
            json={"username": "unit-" + unit, "password": TENANT_PASSWORD + unit})
        assert response.status_code == 200
        sessions[unit] = (httpx.Cookies(client.cookies), response.json()["csrf_token"])
    cookies, csrf = sessions[unit]
    client.cookies = httpx.Cookies(cookies)
    client.headers["X-CSRF-Token"] = csrf
    client._tenant_test_sessions = sessions
    return client


class Snapshot:
    def __init__(self, record_id, record):
        self.id = record_id
        self.exists = record is not None
        self._record = deepcopy(record)

    def to_dict(self):
        return deepcopy(self._record)


class Document:
    def __init__(self, db, collection, record_id):
        self.db, self.collection, self.id = db, collection, record_id

    def get(self, transaction=None):
        return Snapshot(self.id, self.db.data.get(self.collection, {}).get(self.id))

    def set(self, record):
        self.db.data.setdefault(self.collection, {})[self.id] = deepcopy(record)


class Query:
    def __init__(self, db, collection, limit=None):
        self.db, self.collection, self.bound = db, collection, limit

    def limit(self, limit):
        return Query(self.db, self.collection, limit)

    def stream(self):
        assert self.bound is not None, "Recent records must always have a query limit"
        self.db.queries.append((self.collection, self.bound))
        records = self.db.data.get(self.collection, {})
        items = sorted(records.items(), key=lambda pair: pair[1]["created_at"], reverse=True)
        return [Snapshot(key, record) for key, record in items[:self.bound]]


class Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def document(self, record_id):
        return Document(self.db, self.name, record_id)

    def order_by(self, field, direction):
        assert field == "created_at" and direction == "DESCENDING"
        return Query(self.db, self.name)


class Transaction:
    def __init__(self):
        self.writes = []

    def set(self, reference, record):
        self.writes.append(("set", reference, deepcopy(record)))

    def delete(self, reference):
        self.writes.append(("delete", reference, None))


class FakeFirestore:
    def __init__(self):
        self.data, self.queries = {}, []
        self.lock = Lock()
        self.commits = 0

    def collection(self, name):
        return Collection(self, name)

    def transaction(self, operation):
        with self.lock:
            transaction = Transaction()
            result = operation(transaction)
            for kind, reference, record in transaction.writes:
                if kind == "set": reference.set(record)
                else: self.data.get(reference.collection, {}).pop(reference.id, None)
            if transaction.writes: self.commits += 1
            return result


@pytest.fixture
def firestore_client(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setenv("STORAGE_MODE", "firestore")
    monkeypatch.setenv("ADMIN_TOKEN", "firestore-test-owner")
    monkeypatch.setenv("METRICS_TOKEN", "firestore-test-metrics")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("APARTMENT_UNITS", "1,2,3,4,5,6,7,8")
    monkeypatch.setattr(firestore_store, "client", lambda: db)
    monkeypatch.setattr(firestore_store, "_run_transaction", db.transaction)
    apartments._attempts.clear()
    seed_test_tenants()
    with TestClient(app, base_url="https://testserver") as http:
        as_tenant(http)
        yield http, db
    apartments._attempts.clear()


def create(client, **changes):
    as_tenant(client, changes.get("unit", APARTMENT["unit"]))
    response = client.post("/api/apartments/concerns", json={**APARTMENT, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def public_path(receipt):
    return "/api/apartments/concerns/" + receipt["ticket"]["id"]


def test_legacy_firestore_crud_keeps_native_types_and_bounds(firestore_client):
    client, db = firestore_client
    created = client.post("/api/tickets", headers=OWNER, json=LEGACY)
    assert created.status_code == 201
    record = created.json()
    assert isinstance(record["confidence"], float)
    assert isinstance(storage.get(record["id"])["sources"], list)
    assert storage.recent(999)[0]["id"] == record["id"]
    assert db.queries[-1] == (firestore_store.LEGACY_COLLECTION, 200)
    assert client.get("/api/export.csv", headers=OWNER).status_code == 200
    assert storage.delete(record["id"]) is True
    assert storage.delete(record["id"]) is False
    assert storage.get(record["id"]) is None


def test_firestore_tenant_privacy_stale_updates_and_reopening(firestore_client):
    client, db = firestore_client
    receipt = create(client)
    other = create(client, unit="2", category="billing", title="Billing concern")
    path = public_path(receipt)
    # Correct capability keys still cannot cross authenticated tenant identities.
    assert client.get(path, headers={"X-Ticket-Key": receipt["tracking_key"]}).status_code == 404
    assert client.post(path + "/replies", headers={"X-Ticket-Key": receipt["tracking_key"]}, json={"version": 1, "message": "Stolen key attempt"}).status_code == 404
    as_tenant(client, "1")
    key = {"X-Ticket-Key": receipt["tracking_key"]}
    assert client.get(path).status_code == 404
    assert client.get(path, headers={"X-Ticket-Key": other["tracking_key"]}).status_code == 404
    assert client.get("/api/apartments/manage/concerns").status_code == 401
    change = {"version": 1, "status": "resolved", "priority": "high", "message": "Water supply checked", "internal_note": "Private manager discussion"}
    endpoint = "/api/apartments/manage/concerns/" + receipt["ticket"]["id"]
    updated = client.patch(endpoint, headers=OWNER, json=change)
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert client.patch(endpoint, headers=OWNER, json=change).status_code == 409
    public = client.get(path, headers=key)
    assert public.status_code == 200
    assert "Water supply checked" in public.text
    assert "Private manager discussion" not in public.text and "tracking_hash" not in public.text
    result = client.post(path + "/replies", headers=key, json={"version": 2, "message": "Mahina pa rin ang tubig", "reopen": True})
    assert result.status_code == 200 and result.json()["status"] == "received"
    assert result.json()["version"] == 3 and result.json()["resolved_at"] is None
    assert receipt["tracking_key"] not in str(db.data)


def test_firestore_collections_isolate_notice_apartment_and_legacy(firestore_client):
    client, db = firestore_client
    legacy = client.post("/api/tickets", headers=OWNER, json=LEGACY).json()
    receipt = create(client)
    notice = client.put("/api/apartments/manage/notice", headers=OWNER, json={"title": "Water update", "message": "Management is checking; no estimate confirmed."})
    assert notice.status_code == 200
    assert client.put("/api/apartments/manage/notice", headers=OWNER, json={"title": "Overwritten", "message": "Missing version"}).status_code == 409
    recent = apartment_store.recent(999)
    assert [item["id"] for item in recent] == [receipt["ticket"]["id"]]
    assert db.queries[-1] == (firestore_store.APARTMENT_COLLECTION, 200)
    assert [item["id"] for item in storage.recent()] == [legacy["id"]]
    public = client.get("/api/apartments/config").json()["notice"]
    assert set(public) == {"title", "message", "updated_at"}
    assert set(db.data) == {firestore_store.LEGACY_COLLECTION, firestore_store.APARTMENT_COLLECTION, firestore_store.SETTINGS_COLLECTION, tenant_auth_store.COLLECTION}
    assert "password_hash" not in str(recent)
    assert set(db.data[firestore_store.SETTINGS_COLLECTION]) == {"apartment_notice"}
    assert client.put("/api/apartments/manage/notice", headers=OWNER, json={"version": 1, "active": False}).status_code == 200
    assert client.get("/api/apartments/config").json()["notice"] is None


def test_firestore_document_version_conflicts_do_not_write(firestore_client):
    client, db = firestore_client
    receipt = create(client)
    original = apartment_store.get(receipt["ticket"]["id"])
    committed = db.commits
    for version, record in [(None, original), (99, original), (1, {**original, "id": "apt_missing"})]:
        with pytest.raises(apartment_store.Conflict): apartment_store.save(record, version)
    assert db.commits == committed
    assert apartment_store.get(original["id"]) == original


def test_fake_transaction_serializes_same_version_writers(firestore_client):
    client, _ = firestore_client
    receipt = create(client)
    original = apartment_store.get(receipt["ticket"]["id"])
    def write(title):
        try:
            apartment_store.save({**deepcopy(original), "title": title}, expected_version=1)
            return True
        except apartment_store.Conflict:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["First writer", "Second writer"]))
    assert sorted(results) == [False, True]
    assert apartment_store.get(original["id"])["version"] == 2


def test_firestore_query_order_is_newest_first(firestore_client):
    _, _db = firestore_client
    for index in range(5):
        storage.upsert({"id": str(index), "created_at": "2026-01-0" + str(index+1), "sources": [], "requires_human_review": False})
    assert [r["id"] for r in storage.recent(2)] == ["4", "3"]


def test_firestore_transport_failures_are_not_reported_as_version_conflicts(firestore_client, monkeypatch):
    client, db = firestore_client
    receipt = create(client)
    record = apartment_store.get(receipt["ticket"]["id"])
    def unavailable(operation):
        raise RuntimeError("Synthetic transport failure")
    monkeypatch.setattr(firestore_store, "_run_transaction", unavailable)
    with pytest.raises(RuntimeError, match="Synthetic transport failure"):
        apartment_store.save(record, expected_version=1)
    assert apartment_store.get(record["id"])["version"] == 1


def test_firestore_unowned_record_stays_manager_only(firestore_client):
    client, _ = firestore_client
    receipt = create(client)
    record = apartment_store.get(receipt["ticket"]["id"])
    record.pop("tenant_id")
    stored = apartment_store.save(record, expected_version=record["version"])
    assert client.get(public_path(receipt), headers={"X-Ticket-Key": receipt["tracking_key"]}).status_code == 404
    assert client.get("/api/apartments/manage/concerns/" + stored["id"], headers=OWNER).status_code == 200
    assert apartment_store.get(stored["id"]) == stored
