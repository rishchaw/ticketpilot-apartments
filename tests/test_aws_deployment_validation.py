"""Acceptance cleanup and deployment binding must protect unrelated records."""
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock
import boto3
from moto import mock_aws
import pytest
from scripts import validate_aws_deployment as validator
from scripts.validate_gcp_deployment import ConcernReceipt, ValidationError

MARKER = "Synthetic AWS check test-run: "


def synthetic(record_id="apt_synthetic_test_id"):
    receipt = ConcernReceipt(record_id, MARKER + "water concern", key="synthetic-private-tracking-value", version=4, status="received")
    item = {"id": receipt.record_id, "title": receipt.title, "queue": "apartment_tickets", "kind": "apartment_ticket", "version": receipt.version, "status": receipt.status, "updated_at": "2026-01-01T00:00:00+00:00", "tracking_hash": hashlib.sha256(receipt.key.encode()).hexdigest()}
    return receipt, item


@pytest.fixture
def table():
    with mock_aws():
        value = boto3.resource("dynamodb", region_name="ap-southeast-1").create_table(TableName="synthetic-validation", KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
        yield value


def test_cleanup_removes_only_exact_owned_record(table):
    receipt, item = synthetic()
    table.put_item(Item=item)
    unrelated = {"id": "synthetic-unrelated", "title": "Existing fictional concern", "queue": "apartment_tickets"}
    notice = {"id": "apartment_notice", "title": "Existing fictional notice", "queue": "apartment_notices"}
    for value in (unrelated, notice):
        table.put_item(Item=value)
    assert validator.read_exact(table, receipt, MARKER)["version"] == 4
    result = validator.cleanup_owned(table, [receipt], MARKER)
    assert result == {"created": 1, "deleted": 1, "already_absent": 0, "skipped": 0, "error_types": []}
    for value in (unrelated, notice):
        assert table.get_item(Key={"id": value["id"]}, ConsistentRead=True)["Item"] == value


def test_cleanup_skips_renamed_or_foreign_record(table):
    receipt, item = synthetic()
    item["title"] = "Existing fictional record, no longer validator-owned"
    table.put_item(Item=item)
    result = validator.cleanup_owned(table, [receipt], MARKER)
    assert result["skipped"] == 1 and result["deleted"] == 0
    assert table.get_item(Key={"id": receipt.record_id}, ConsistentRead=True)["Item"] == item


def test_cleanup_conditional_delete_refuses_concurrent_change(table):
    receipt, item = synthetic()
    table.put_item(Item=item)
    class RacingTable:
        meta = table.meta
        def get_item(self, **arguments):
            return table.get_item(**arguments)
        def delete_item(self, **arguments):
            changed = {**item, "version": 99, "updated_at": "2026-01-02T00:00:00+00:00"}
            table.put_item(Item=changed)
            return table.delete_item(**arguments)
    result = validator.cleanup_owned(RacingTable(), [receipt], MARKER)
    assert result["skipped"] == 1 and result["deleted"] == 0 and result["error_types"] == []
    assert table.get_item(Key={"id": receipt.record_id}, ConsistentRead=True)["Item"]["version"] == 99


def test_binding_rejects_mismatched_table_before_workflow():
    client = Mock()
    client.get_function_configuration.return_value = {"State": "Active", "LastUpdateStatus": "Successful", "Environment": {"Variables": {"STORAGE_MODE": "dynamodb", "DYNAMODB_TABLE": "actual-table", "LLM_PROVIDER": "none"}}}
    client.get_function_url_config.return_value = {"FunctionUrl": "https://synthetic.lambda-url.ap-southeast-1.on.aws/", "AuthType": "NONE"}
    with pytest.raises(ValidationError, match="table does not match"):
        validator.verify_binding(client, "synthetic-function", "wrong-table", "https://synthetic.lambda-url.ap-southeast-1.on.aws")
