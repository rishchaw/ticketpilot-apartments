"""AWS integration tests use in-process emulation; no account or cloud spend."""
import importlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from moto import mock_aws

from ticketpilot import assistant, storage
from ticketpilot.api import app
from ticketpilot.aws_secrets import load_secrets
from ticketpilot.knowledge import find_articles

BODY = {"title": "Production API outage", "text": "Production API unreachable with HTTP 503 and server errors for all customers."}
HEADERS = {"X-Admin-Token": "test-owner-secret"}


@pytest.fixture
def aws_client(monkeypatch):
    for key, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_DEFAULT_REGION": "ap-southeast-1", "AWS_REGION": "ap-southeast-1", "STORAGE_MODE": "dynamodb", "DYNAMODB_TABLE": "test-tickets", "ADMIN_TOKEN": "test-owner-secret", "METRICS_TOKEN": "test-metrics-secret", "LLM_PROVIDER": "none"}.items():
        monkeypatch.setenv(key, value)
    storage._dynamodb.cache_clear()
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="test-tickets", BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("id", "queue", "created_at")],
            GlobalSecondaryIndexes=[{
                "IndexName": "recent-tickets", "KeySchema": [{"AttributeName": "queue", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"}, "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
            }],
        )
        yield TestClient(app)
    storage._dynamodb.cache_clear()


def test_dynamodb_crud_and_decimal_serialization(aws_client):
    assert aws_client.post("/api/tickets", json=BODY).status_code == 401
    created = aws_client.post("/api/tickets", headers=HEADERS, json=BODY)
    assert created.status_code == 201
    record = created.json()
    assert isinstance(record["confidence"], float)
    saved = storage.get(record["id"])
    assert saved["sources"] == record["sources"]
    assert "queue" not in saved
    rows = aws_client.get("/api/tickets", headers=HEADERS).json()["items"]
    assert rows[0]["id"] == record["id"]
    updated = aws_client.patch("/api/tickets/" + record["id"], headers=HEADERS, json={"status": "resolved"})
    assert updated.status_code == 200
    assert storage.get(record["id"])["resolved_at"]
    assert aws_client.get("/api/export.csv", headers=HEADERS).status_code == 200
    assert aws_client.delete("/api/tickets/" + record["id"], headers=HEADERS).status_code == 204
    assert not storage.delete(record["id"])
    assert storage.get(record["id"]) is None


def test_dynamodb_recent_is_ordered_bounded_query(aws_client):
    table = storage._dynamodb()
    for i in range(5):
        table.put_item(Item={"id": str(i), "queue": "tickets", "created_at": (datetime.now(timezone.utc) + timedelta(seconds=i)).isoformat()})
    assert [r["id"] for r in storage.recent(2)] == ["4", "3"]


def test_metrics_auth_and_bounded_labels(aws_client):
    assert aws_client.get("/metrics").status_code == 401
    aws_client.get("/unknown/unique-user-value")
    aws_client.post("/api/analyze", json=BODY)
    metrics = aws_client.get("/metrics", headers={"Authorization": "Bearer test-metrics-secret"})
    assert metrics.status_code == 200
    assert "ticketpilot_answers_total" in metrics.text
    assert "unique-user-value" not in metrics.text
    assert BODY["text"] not in metrics.text
    assert "test-owner-secret" not in metrics.text


@pytest.fixture
def bedrock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("LLM_MAX_CALLS_PER_MINUTE", "1")
    assistant.reset_generation_state()
    client = Mock()
    client.converse.return_value = {"output": {"message": {"content": [{"text": "Check service health [KB-007]."}]}}}
    monkeypatch.setattr(assistant, "bedrock_client", lambda: client)
    yield client
    assistant.reset_generation_state()


def test_bedrock_citations_cache_and_limiter(bedrock):
    question = BODY["title"] + ". " + BODY["text"]
    assert assistant.suggest(question, "infrastructure", True)[2] == "bedrock"
    assert assistant.suggest(question, "infrastructure", True)[2] == "bedrock_cached"
    assert assistant.suggest(question + " Please investigate.", "infrastructure", True)[2] == "retrieval_rate_limited"
    assert bedrock.converse.call_count == 1
    request = bedrock.converse.call_args.kwargs
    assert request["inferenceConfig"]["maxTokens"] == 400
    assert "retrieved_articles" in request["messages"][0]["content"][0]["text"]


@pytest.mark.parametrize("answer", ["No citations", "Invented answer [KB-999]"])
def test_invalid_generation_falls_back(bedrock, answer):
    bedrock.converse.return_value = {"output": {"message": {"content": [{"text": answer}]}}}
    result = assistant.suggest(BODY["text"], "infrastructure", True)
    assert result[2] == "retrieval_fallback"
    assert result[0].startswith("Suggested troubleshooting")


def test_bedrock_access_denied_preserves_intake(bedrock):
    bedrock.converse.side_effect = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "Unavailable"}}, "Converse")
    assert assistant.suggest(BODY["text"], "infrastructure", True)[2] == "retrieval_fallback"


def test_public_never_calls_bedrock(aws_client, bedrock, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    assert aws_client.post("/api/analyze", json=BODY).json()["answer_mode"] == "retrieval"
    bedrock.converse.assert_not_called()


def test_no_context_never_calls_provider(bedrock):
    assert assistant.suggest("zxyzq 99887766", "product", True)[2] == "retrieval"
    bedrock.converse.assert_not_called()


def test_ssm_secrets_are_loaded_and_missing_secrets_fail(aws_client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN_PARAMETER", "/test/admin")
    monkeypatch.setenv("METRICS_TOKEN_PARAMETER", "/test/metrics")
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/test/admin", Value="private-owner-token", Type="SecureString")
    with pytest.raises(RuntimeError, match="missing"):
        load_secrets()
    ssm.put_parameter(Name="/test/metrics", Value="private-metrics-token", Type="SecureString")
    load_secrets()
    import os
    assert os.environ["ADMIN_TOKEN"] == "private-owner-token"


def test_lambda_function_url_event(aws_client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN_PARAMETER", raising=False)
    monkeypatch.delenv("METRICS_TOKEN_PARAMETER", raising=False)
    handler = importlib.import_module("ticketpilot.lambda_handler").handler
    event = {
        "version": "2.0", "routeKey": "$default", "rawPath": "/health", "rawQueryString": "",
        "headers": {"host": "example.lambda-url.ap-southeast-1.on.aws"},
        "requestContext": {"http": {"method": "GET", "path": "/health", "sourceIp": "127.0.0.1", "protocol": "HTTP/1.1"}},
        "isBase64Encoded": False,
    }
    result = handler(event, {})
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["storage_mode"] == "dynamodb"
