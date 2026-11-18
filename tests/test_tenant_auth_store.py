"""Auth persistence must isolate records and reject stale cross-worker writes."""
import json
from concurrent.futures import ThreadPoolExecutor
import boto3
from moto import mock_aws
import pytest
from ticketpilot import storage, apartment_store, tenant_auth_store as store


@pytest.fixture(params=["sqlite", "dynamodb"])
def backend(request, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_MODE", request.param)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    monkeypatch.setattr(storage, "PATH", tmp_path / "auth-storage.db")
    if request.param == "sqlite":
        yield request.param
    else:
        with mock_aws():
            monkeypatch.setenv("DYNAMODB_TABLE", "auth-isolation-test")
            store._runtime.__dict__.clear()
            storage._dynamodb.cache_clear()
            boto3.resource("dynamodb", region_name="ap-southeast-1").create_table(
                TableName="auth-isolation-test", KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}, {"AttributeName": "queue", "AttributeType": "S"}, {"AttributeName": "created_at", "AttributeType": "S"}],
                GlobalSecondaryIndexes=[{"IndexName": "recent-tickets", "KeySchema": [{"AttributeName": "queue", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}], BillingMode="PAY_PER_REQUEST")
            yield request.param
            store._runtime.__dict__.clear()
            storage._dynamodb.cache_clear()


def test_auth_record_cas_and_guarded_delete(backend):
    first = store.put_if_version("user:synthetic", {"kind": "tenant_user", "private": "fictional-hash"})
    assert first["id"] == "user:synthetic" and first["version"] == 1
    assert store.get("user:synthetic") == first
    with pytest.raises(store.Conflict):
        store.put_if_version("user:synthetic", {"kind": "tenant_user"})
    second = store.put_if_version("user:synthetic", {**first, "private": "new-fictional-hash"}, first["version"])
    with pytest.raises(store.Conflict):
        store.put_if_version("user:synthetic", first, first["version"])
    assert not store.delete("user:synthetic", first["version"])
    assert store.get("user:synthetic") == second
    assert store.delete("user:synthetic", second["version"])
    assert store.get("user:synthetic") is None


def test_auth_credentials_do_not_enter_concern_queue_or_legacy_api(backend):
    store.put_if_version("user:synthetic", {"kind": "tenant_user", "password_hash": "fictional-private-hash"})
    store.put_if_version("session:" + "a" * 64, {"kind": "tenant_session", "auth_expires_at": 1000})
    assert apartment_store.recent() == []
    assert storage.recent() == []
    assert storage.get(store.PREFIX + "user:synthetic") is None
    if backend == "dynamodb":
        raw = store._table().get_item(Key={"id": store.PREFIX + "user:synthetic"}, ConsistentRead=True)["Item"]
        assert not {"queue", "created_at"}.intersection(raw)
    else:
        with storage._sql() as conn:
            assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == 0


def test_auth_store_rejects_concern_index_attributes(backend):
    for key in ("queue", "created_at"):
        with pytest.raises(ValueError):
            store.put_if_version("user:synthetic", {key: "must-not-be-indexed"})
    assert store.get("user:synthetic") is None


def test_concurrent_writers_cannot_silently_overwrite_another_version(backend):
    initial = store.put_if_version("rate:global", {"kind": "tenant_rate", "count": 0})
    def write(value):
        try:
            store.put_if_version(initial["id"], {**initial, "count": value}, initial["version"])
            return "saved"
        except store.Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(write, [1, 2]))
    assert sorted(outcomes) == ["conflict", "saved"]
    assert store.get(initial["id"])["version"] == 2


def test_storage_failure_is_not_an_empty_directory(monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "none")
    for operation in (lambda: store.get("registry"), lambda: store.put_if_version("registry", {}), lambda: store.delete("registry", 1)):
        with pytest.raises(store.Unavailable):
            operation()


@pytest.mark.parametrize("value", [[], "invalid", {"id": "registry", "version": False}, {"id": "different", "version": 1}])
def test_malformed_stored_auth_records_fail_closed(monkeypatch, value):
    monkeypatch.setattr(store, "_get", lambda _: value)
    with pytest.raises(store.Unavailable):store.get("registry")
