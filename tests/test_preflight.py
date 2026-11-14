"""Regression checks for deployment gating; all AWS clients are mocks."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

from botocore.exceptions import ClientError
import pytest

spec = importlib.util.spec_from_file_location("preflight_aws", Path(__file__).resolve().parents[1] / "scripts/preflight_aws.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


@pytest.fixture
def clients(monkeypatch):
    clients = {name: Mock() for name in ("sts", "lambda", "dynamodb", "ecr", "ssm")}
    clients["sts"].get_caller_identity.return_value = {"Account": "000000000000", "Arn": "arn:aws:iam::000000000000:role/test"}
    clients["lambda"].get_account_settings.return_value = {"AccountLimit": {"ConcurrentExecutions": 10}}
    session = Mock()
    session.client.side_effect = lambda name: clients[name]
    monkeypatch.setattr(preflight.boto3, "Session", Mock(return_value=session))
    return clients


def test_unactivated_account_stops_deployment(clients, capsys):
    clients["lambda"].get_account_settings.side_effect = ClientError({"Error": {"Code": "SubscriptionRequiredException", "Message": "The AWS Access Key Id needs a subscription for the service"}}, "GetAccountSettings")
    assert preflight.main(["--profile", "ticketpilot"]) == 2
    output = capsys.readouterr()
    assert "SubscriptionRequiredException" in output.err
    assert "before creating cloud resources" in output.err
    clients["ssm"].describe_parameters.assert_called_once()
    clients["ssm"].put_parameter.assert_not_called()
    clients["ecr"].create_repository.assert_not_called()


def test_available_services_pass_preflight(clients):
    assert preflight.main(["--profile", "ticketpilot", "--region", "ap-southeast-1"]) == 0
    preflight.boto3.Session.assert_called_once_with(profile_name="ticketpilot", region_name="ap-southeast-1")


def test_expired_signin_stops_before_service_checks(clients):
    clients["sts"].get_caller_identity.side_effect = ClientError({"Error": {"Code": "ExpiredToken", "Message": "Expired session"}}, "GetCallerIdentity")
    assert preflight.main(["--profile", "ticketpilot"]) == 1
    clients["lambda"].get_account_settings.assert_not_called()