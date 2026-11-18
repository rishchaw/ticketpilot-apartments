"""Source delivery includes both clouds but never generated credentials or state."""
import json
from pathlib import Path
import pytest
from scripts.package_source import ASSET_FILES, ROOT_FILES, collect_source_files


@pytest.fixture
def source_tree(tmp_path):
    for name in ROOT_FILES + ASSET_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]" if path.suffix == ".json" else "reviewed source", encoding="utf-8")
    return tmp_path


def write(root, name, content="generated private data"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def names(root):
    return {path.relative_to(root).as_posix() for path in collect_source_files(root)}


def test_package_keeps_gcp_runtime_and_both_terraform_roots(source_tree):
    for name in ("infra/aws/main.tf", "infra/gcp/bootstrap/main.tf", "infra/gcp/app/main.tf", "infra/gcp/app/.terraform.lock.hcl", "infra/gcp/app/terraform.tfvars.example", ".github/workflows/ci.yml"):
        write(source_tree, name, "reviewed configuration")
    selected = names(source_tree)
    assert {"Dockerfile.gcp", "requirements-gcp.txt", ".env.example", "infra/gcp/bootstrap/main.tf", "infra/gcp/app/.terraform.lock.hcl", "infra/gcp/app/terraform.tfvars.example"} <= selected


def test_package_excludes_generated_secrets_databases_state_and_plans(source_tree):
    generated = [
        "scripts/.env", "infra/gcp/app/terraform.tfvars", "infra/gcp/app/terraform.tfvars.json",
        "infra/gcp/app/private.auto.tfvars.json", "infra/gcp/app/terraform.tfstate.backup",
        "infra/gcp/app/deploy.tfplan", "infra/gcp/app/backend.tfbackend", "infra/gcp/app/backend.ci.tf",
        "infra/gcp/app/backend.gcp.ci.tf", "infra/gcp/app/deployment-gcp-plan.json",
        "scripts/gha-creds-abcdef.json", "scripts/application_default_credentials.json",
        "scripts/test-credentials.json", "ticketpilot/cache.db", "ticketpilot/cache.db-wal",
        "infra/gcp/app/.terraform/environment", "docs/.secrets/manager-token",
        "tests/__pycache__/test.pyc", "scripts/local.key",
    ]
    for name in generated:
        write(source_tree, name)
    assert not set(generated).intersection(names(source_tree))


def test_generated_json_is_excluded_even_when_renamed(source_tree):
    for name, document in {
        "docs/renamed-service.json": {"type": "service_account", "private_key": "fictional-key"},
        "scripts/renamed-login.json": {"type": "authorized_user", "refresh_token": "fictional-token"},
        "infra/gcp/app/renamed-plan.json": {"format_version": "1.2", "resource_changes": []},
        "infra/gcp/app/renamed-state.json": {"lineage": "fictional-id", "serial": 1, "resources": []},
    }.items():
        write(source_tree, name, json.dumps(document))
    write(source_tree, "docs/release-example.json", json.dumps({"schema_version": 1, "commit": "a" * 40}))
    write(source_tree, "docs/typed-example.json", json.dumps({"type": {"name": "public-example"}}))
    selected = names(source_tree)
    assert {"docs/release-example.json", "docs/typed-example.json"} <= selected
    assert not any("renamed-" in name for name in selected)


def test_missing_required_runtime_file_fails_before_creating_an_incomplete_package(source_tree):
    (source_tree / "Dockerfile.gcp").unlink()
    with pytest.raises(FileNotFoundError, match="Dockerfile.gcp"):
        collect_source_files(source_tree)


@pytest.mark.parametrize("location", ["docs/renamed-export.json", "tests/copied-data.json", "ticketpilot/extra-data.json"])
@pytest.mark.parametrize("field,value", [
    ("password", "fictional-private-password"),
    ("password_hash", "$argon2id$fictional-private-digest"),
    ("csrf_token", "fictional-private-csrf"),
    ("session_token", "fictional-private-session"),
    ("session_tokens", ["fictional-private-session"]),
    ("sessionCookie", "fictional-private-cookie"),
])
def test_renamed_nested_tenant_credentials_never_enter_source_package(source_tree, location, field, value):
    document = {"schema_version": 1, "accounts": [{"tenant_id": "fictional-tenant", "username": "unit-fictional", field: value}]}
    write(source_tree, location, json.dumps(document))
    assert location not in names(source_tree)


@pytest.mark.parametrize("kind", ["tenant_user", "tenant_session"])
def test_auth_record_exports_are_excluded_even_without_plaintext_fields(source_tree, kind):
    for location, document in {
        "docs/direct-record.json": {"kind": kind, "id": "fictional-private-record"},
        "tests/list-export.json": [{"kind": kind, "id": "fictional-private-record"}],
        "docs/sdk-record.json": {"kind": {"S": kind}, "id": {"S": "fictional-private-record"}},
    }.items():
        write(source_tree, location, json.dumps(document))
    selected = names(source_tree)
    assert not {"docs/direct-record.json", "tests/list-export.json", "docs/sdk-record.json"}.intersection(selected)


@pytest.mark.parametrize("field", ["password_hash", "csrf_token", "session_token"])
def test_direct_auth_fields_and_native_sdk_wrappers_are_excluded(source_tree, field):
    write(source_tree, "docs/direct-secret.json", json.dumps({field: "fictional-secret"}))
    write(source_tree, "tests/wrapped-secret.json", json.dumps({field: {"S": "fictional-secret"}}))
    selected = names(source_tree)
    assert "docs/direct-secret.json" not in selected and "tests/wrapped-secret.json" not in selected


def test_pending_reset_inventory_is_excluded_when_renamed(source_tree):
    location = "docs/saved-export.json"
    write(source_tree, location, json.dumps({"action": "reset", "inventory": {"schema_version": 1, "accounts": [{"password": "fictional-private-replacement"}]}}))
    assert location not in names(source_tree)


def test_password_guidance_and_unpopulated_public_schema_remain_reviewable_source(source_tree):
    guidance = [{"id": "password-reset", "title": "Reset your password", "summary": "Keep session tokens private", "steps": ["Choose a different password", "Never paste csrf_token values into chat"]}]
    write(source_tree, "docs/password-guidance.json", json.dumps(guidance))
    schema = {"type": "object", "properties": {"password": {"type": "string", "format": "password", "writeOnly": True}, "csrf_token": {"type": "string", "description": "A CSRF token field"}}}
    write(source_tree, "docs/auth-schema.json", json.dumps(schema))
    selected = names(source_tree)
    assert {"docs/password-guidance.json", "docs/auth-schema.json"} <= selected
