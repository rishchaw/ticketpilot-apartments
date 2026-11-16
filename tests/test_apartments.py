"""Apartment ownership, privacy, workflow and persistence on SQLite and emulated DynamoDB."""
import hashlib
import json
import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from ticketpilot.api import app
from ticketpilot import apartment_store, apartments, storage

OWNER = {"X-Admin-Token": "apartment-test-owner"}
BODY = {"unit": "1", "category": "water", "title": "Walang tubig", "description": "Walang tubig sa lahat ng gripo mula ngayong umaga.", "language": "fil"}


@pytest.fixture(params=["sqlite", "dynamodb"])
def client(request, monkeypatch, tmp_path):
    for key, value in {"ADMIN_TOKEN": "apartment-test-owner", "METRICS_TOKEN": "apartment-test-metrics", "STORAGE_MODE": request.param, "LLM_PROVIDER": "none", "APARTMENT_UNITS": "1,2,3,4,5,6,7,8", "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_DEFAULT_REGION": "ap-southeast-1", "DYNAMODB_TABLE": "apartment-tests"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(storage, "PATH", tmp_path / "apartment.db")
    apartments._attempts.clear()
    storage._dynamodb.cache_clear()
    with mock_aws():
        if request.param == "dynamodb":
            boto3.client("dynamodb").create_table(TableName="apartment-tests", BillingMode="PAY_PER_REQUEST",
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("id", "queue", "created_at")],
                GlobalSecondaryIndexes=[{"IndexName": "recent-tickets", "KeySchema": [{"AttributeName": "queue", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}])
        yield TestClient(app)
    storage._dynamodb.cache_clear()
    apartments._attempts.clear()


def create(client, **fields):
    result = client.post("/api/apartments/concerns", json={**BODY, **fields})
    assert result.status_code == 201, result.text
    return result.json()


def key_headers(receipt):
    return {"X-Ticket-Key": receipt["tracking_key"]}


def path(receipt):
    return "/api/apartments/concerns/" + receipt["ticket"]["id"]


def patch(client, receipt, **changes):
    return client.patch("/api/apartments/manage/concerns/" + receipt["ticket"]["id"], headers=OWNER,
        json={"version": receipt["ticket"]["version"], "status": "acknowledged", "priority": "high", **changes})


def test_tenant_capabilities_are_private_and_not_stored_raw(client):
    first = create(client)
    second = create(client, unit="2", category="billing", title="Rent concern")
    assert first["ticket"]["status"] == "received"
    assert "Management" in first["guidance"] or "management" in first["guidance"]
    assert client.get(path(first)).status_code == 404
    assert client.get(path(first), headers=key_headers(second)).status_code == 404
    assert client.post(path(first) + "/replies", headers=key_headers(second), json={"version": 1, "message": "Try another ticket"}).status_code == 404
    response = client.get(path(first), headers=key_headers(first))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "tracking_hash" not in response.text and "internal_notes" not in response.text
    stored = apartment_store.get(first["ticket"]["id"])
    assert stored["tracking_hash"] == hashlib.sha256(first["tracking_key"].encode()).hexdigest()
    assert first["tracking_key"] not in json.dumps(stored)
    assert client.get("/api/apartments/manage/concerns").status_code == 401
    assert client.get("/api/apartments/manage/concerns/" + first["ticket"]["id"]).status_code == 401
    assert patch(client, first, message="We are checking", internal_note="Private account discussion").status_code == 200
    public = client.get(path(first), headers=key_headers(first))
    assert "We are checking" in public.text
    assert "Private account discussion" not in public.text
    assert "assigned_to" not in public.text


def test_complete_workflow_concurrent_updates_reopen_and_legacy_isolation(client):
    receipt = create(client)
    update = patch(client, receipt, status="resolved", message="Water restored", assigned_to="Building manager")
    assert update.status_code == 200
    assert update.json()["resolved_at"]
    assert patch(client, receipt, message="Stale edit").status_code == 409
    future = patch(client, receipt, version=99, message="Future version")
    assert future.status_code == 409
    reopened = client.post(path(receipt) + "/replies", headers=key_headers(receipt), json={"version": update.json()["version"], "message": "Mahina pa rin ang tubig", "reopen": True})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "received" and reopened.json()["resolved_at"] is None
    assert reopened.json()["updates"][-1]["author"] == "tenant"
    saved = TestClient(app).get(path(receipt), headers=key_headers(receipt)).json()
    assert saved["version"] == 3
    manager_rows = client.get("/api/apartments/manage/concerns", headers=OWNER).json()["items"]
    assert manager_rows[0]["id"] == receipt["ticket"]["id"]
    assert "tracking_hash" not in json.dumps(manager_rows)
    assert client.get("/api/tickets", headers=OWNER).json()["items"] == []
    assert client.get("/api/knowledge").json()["total"] == 14


def test_notice_is_manager_controlled_and_versioned(client):
    assert client.get("/api/apartments/config").json()["notice"] is None
    assert client.put("/api/apartments/manage/notice", json={"title": "Notice", "message": "Water check"}).status_code == 401
    notice = client.put("/api/apartments/manage/notice", headers=OWNER, json={"title": "Water check", "message": "Management is checking the water supply. No restoration estimate confirmed."})
    assert notice.status_code == 200
    public = client.get("/api/apartments/config").json()["notice"]
    assert set(public) == {"title", "message", "updated_at"}
    assert "No restoration estimate confirmed" in public["message"]
    assert client.put("/api/apartments/manage/notice", headers=OWNER, json={"title": "Stale overwrite", "message": "No version"}).status_code == 409
    hidden = client.put("/api/apartments/manage/notice", headers=OWNER, json={"version": notice.json()["version"], "active": False})
    assert hidden.status_code == 200
    assert client.get("/api/apartments/config").json()["notice"] is None


def test_shared_issue_suggestions_do_not_expose_other_tenants(client):
    first = create(client)
    create(client, unit="1")
    assert not client.get("/api/apartments/manage/concerns", headers=OWNER).json()["possible_shared_issues"]
    create(client, unit="2", description="No water in the kitchen since this morning.")
    q = client.get("/api/apartments/manage/concerns", headers=OWNER).json()
    assert q["possible_shared_issues"][0]["unit_count"] == 2
    public = client.get(path(first), headers=key_headers(first)).json()
    assert "unit_count" not in public and "possible_shared_issues" not in public
    assert client.get("/api/apartments/config").json()["notice"] is None


def test_validation_fail_closed_and_no_paid_provider(client, monkeypatch):
    def no_provider(*args, **kwargs):
        raise AssertionError("Tenant workflow must never invoke an LLM")
    monkeypatch.setattr("ticketpilot.assistant.call_bedrock", no_provider)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    create(client, urgent=True)
    assert client.post("/api/apartments/concerns", json={**BODY, "unit": "9"}).status_code == 422
    assert client.post("/api/apartments/concerns", json={**BODY, "title": "   "}).status_code == 422
    assert client.post("/api/apartments/concerns", json={**BODY, "tracking_hash": "injected"}).status_code == 422
    assert client.post("/api/apartments/concerns", json={**BODY, "category": "infrastructure"}).status_code == 422
    assert client.get("/api/apartments/manage/concerns", headers={"X-Admin-Token": "bad"}).status_code == 401
    monkeypatch.delenv("ADMIN_TOKEN")
    assert client.post("/api/apartments/concerns", json=BODY).status_code == 503


def test_process_local_rate_limit_and_privacy_in_metrics(client):
    for _ in range(30):
        create(client)
    assert client.post("/api/apartments/concerns", json=BODY).status_code == 429
    metrics = client.get("/metrics", headers={"Authorization": "Bearer apartment-test-metrics"})
    assert "ticketpilot_apartment_events_total" in metrics.text
    assert BODY["description"] not in metrics.text
    assert "apartment-test-owner" not in metrics.text


def test_mobile_pages_and_original_demo_are_available(client):
    for path in ("/", "/tenant", "/manager"):
        page = client.get(path)
        assert page.status_code == 200
        assert 'name="viewport"' in page.text
        assert page.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/assets/apartments.js").status_code == 200
    assert client.get("/assets/apartments.css").status_code == 200
    assert "AI Playground" in client.get("/demo").text


def test_cloud_demo_manual_refresh_and_bounded_queue(client, monkeypatch):
    monkeypatch.setenv("APARTMENT_REFRESH_SECONDS", "0")
    monkeypatch.setenv("APARTMENT_QUEUE_LIMIT", "2")
    first = create(client, title="Older concern")
    create(client, title="Recent concern")
    last = create(client, title="Newest concern")
    config = client.get("/api/apartments/config").json()
    assert config["manager_refresh_seconds"] == 0
    assert config["queue_limit"] == 2
    rows = client.get("/api/apartments/manage/concerns", headers=OWNER).json()["items"]
    assert len(rows) == 2
    assert last["ticket"]["id"] in {row["id"] for row in rows}
    assert first["ticket"]["id"] not in {row["id"] for row in rows}
    monkeypatch.delenv("APARTMENT_REFRESH_SECONDS")
    monkeypatch.delenv("APARTMENT_QUEUE_LIMIT")
    defaults = client.get("/api/apartments/config").json()
    assert defaults["manager_refresh_seconds"] == 30
    assert defaults["queue_limit"] == 200
