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
