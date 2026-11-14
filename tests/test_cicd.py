"""Release provenance and non-destructive deployment-plan policy tests."""
from copy import deepcopy
import pytest
from scripts.select_release import validate_run
from scripts.check_deployment_plan import validate_plan

SHA = "a" * 40
URI = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/ticketpilot-aws@sha256:" + "b" * 64
RUN = {"id": 123, "repository": {"full_name": "owner/ticketpilot-apartments"}, "head_repository": {"full_name": "owner/ticketpilot-apartments"}, "head_branch": "main", "head_sha": SHA, "path": ".github/workflows/release.yml", "event": "workflow_dispatch", "status": "completed", "conclusion": "success"}


def test_release_run_requires_trusted_success():
    assert validate_run(RUN, "owner/ticketpilot-apartments", "main", "123") == SHA
    for field, value in [("conclusion", "failure"), ("status", "in_progress"), ("head_branch", "feature"), ("event", "pull_request"), ("path", ".github/workflows/ci.yml"), ("head_sha", "mutable-tag"), ("head_repository", {"full_name": "attacker/fork"})]:
        invalid = {**RUN, field: value}
        with pytest.raises(ValueError):
            validate_run(invalid, "owner/ticketpilot-apartments", "main", "123")


def change(actions=None, address="aws_lambda_function.app", after=None):
    return {"address": address, "mode": "managed", "change": {"actions": actions or ["update"], "before": {"image_uri": "old", "role": "runtime", "environment": {"a": "b"}, "last_modified": "old-date"}, "after": after or {"image_uri": URI, "role": "runtime", "environment": {"a": "b"}, "last_modified": None}, "after_unknown": {"last_modified": True}}}


def test_cd_accepts_only_immutable_existing_image_changes():
    assert validate_plan({"resource_changes": [change()]}, URI) == 1
    assert validate_plan({"resource_changes": []}, URI) == 0
    assert validate_plan({"resource_changes": [change(["no-op"])]}, URI) == 0
    for rejected in [change(["delete", "create"]), change(["create"]), change(address="aws_dynamodb_table.tickets"), change(after={"image_uri": URI, "role": "administrator", "environment": {"a": "b"}})]:
        with pytest.raises(ValueError):
            validate_plan({"resource_changes": [rejected]}, URI)
    with pytest.raises(ValueError):
        validate_plan({"resource_changes": [change()]}, "image:latest")
    unknown_role = change()
    unknown_role["change"]["after_unknown"]["role"] = True
    with pytest.raises(ValueError):
        validate_plan({"resource_changes": [unknown_role]}, URI)


def test_unknown_configurable_values_are_not_treated_as_computed_metadata():
    invalid = change()
    invalid["change"]["before"]["memory_size"] = 1024
    invalid["change"]["after"]["memory_size"] = None
    invalid["change"]["after_unknown"]["memory_size"] = True
    with pytest.raises(ValueError):
        validate_plan({"resource_changes": [invalid]}, URI)
