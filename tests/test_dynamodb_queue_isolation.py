"""Queue boundaries must hold through both HTTP routes and atomic Dynamo writes."""
import copy
import boto3
from fastapi.testclient import TestClient
from moto import mock_aws
import pytest
from ticketpilot import apartments, storage
from ticketpilot.api import app


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "dynamodb")
    monkeypatch.setenv("DYNAMODB_TABLE", "synthetic-queue-isolation")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    monkeypatch.setenv("ADMIN_TOKEN", "synthetic-owner-access-only")
    monkeypatch.setenv("APARTMENT_UNITS", "1,2,3,4,5,6,7,8")
    apartments._attempts.clear()
    storage._dynamodb.cache_clear()
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="ap-southeast-1")
        value = resource.create_table(TableName="synthetic-queue-isolation", KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
        yield value
    storage._dynamodb.cache_clear()
    apartments._attempts.clear()


def test_legacy_patch_and_delete_cannot_move_or_remove_apartment(table):
    with TestClient(app) as client:
        response = client.post("/api/apartments/concerns", json={"unit": "1", "category": "water", "title": "Synthetic queue isolation concern", "description": "Fictional test only; do not perform maintenance.", "language": "en"})
        assert response.status_code == 201
        receipt = response.json()
        record_id = receipt["ticket"]["id"]
        before = table.get_item(Key={"id": record_id}, ConsistentRead=True)["Item"]
        owner = {"X-Admin-Token": "synthetic-owner-access-only"}
        assert client.patch("/api/tickets/" + record_id, headers=owner, json={"status": "resolved"}).status_code == 404
        assert client.delete("/api/tickets/" + record_id, headers=owner).status_code == 404
        assert table.get_item(Key={"id": record_id}, ConsistentRead=True)["Item"] == before
        tracking = client.get("/api/apartments/concerns/" + record_id, headers={"X-Ticket-Key": receipt["tracking_key"]})
        assert tracking.status_code == 200 and tracking.json()["status"] == "received"


def test_atomic_legacy_put_refuses_a_queue_changed_after_read(table):
    previous = storage.upsert({"id": "synthetic-raced-id", "title": "Legacy synthetic record", "sources": []})
    assert storage.get(previous["id"])
    replacement = {"id": previous["id"], "title": "Synthetic apartment record", "queue": "apartment_tickets", "kind": "apartment_ticket", "version": 1}
    table.put_item(Item=replacement)
    with pytest.raises(storage.Conflict):
        storage.upsert(copy.deepcopy(previous))
    assert table.get_item(Key={"id": previous["id"]}, ConsistentRead=True)["Item"] == replacement


def test_legacy_get_and_delete_refuse_notice_and_missing_rows(table):
    notice = {"id": "apartment_notice", "queue": "apartment_notices", "title": "Synthetic notice"}
    table.put_item(Item=notice)
    assert storage.get(notice["id"]) is None
    assert storage.delete(notice["id"]) is False
    assert storage.delete("synthetic-missing-id") is False
    assert table.get_item(Key={"id": notice["id"]}, ConsistentRead=True)["Item"] == notice


def test_normal_legacy_crud_preserved(table):
    record = storage.upsert({"id": "synthetic-legacy-id", "title": "Synthetic legacy", "sources": []})
    assert storage.get(record["id"])["title"] == record["title"]
    record["title"] = "Synthetic legacy updated"
    storage.upsert(record)
    assert storage.get(record["id"])["title"] == record["title"]
    assert storage.delete(record["id"]) is True
    assert storage.get(record["id"]) is None
