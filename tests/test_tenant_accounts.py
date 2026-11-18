"""Closed registry provisioning and durable, explicit credential lifecycle."""
import copy
import io
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from ticketpilot import storage, tenant_accounts as accounts, tenant_auth as auth, tenant_auth_store as store

UNITS = ["1A", "1B", "2A", "2B", "2C", "3A", "3B", "3C"]
CSV = ",".join(UNITS)


@pytest.fixture
def private_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_MODE", "sqlite")
    monkeypatch.setenv("TENANT_COOKIE_SECURE", "true")
    monkeypatch.setattr(storage, "PATH", tmp_path / "auth.db")
    monkeypatch.setattr(accounts, "ROOT", tmp_path / "source-tree")
    return tmp_path / "private" / "tenant-credentials.json"


def inventory(path):
    return json.loads(path.read_text(encoding="utf-8"))


def user_rows(value):
    return [store.get("user:" + entry["username"]) for entry in value["accounts"]]


def signed_in(value, index=0):
    app = FastAPI();app.include_router(auth.router)
    browser = TestClient(app, base_url="https://testserver")
    entry = value["accounts"][index]
    response = browser.post("/api/tenant/login", json={"username": entry["username"], "password": entry["password"]}, headers={"X-TicketPilot-Login": "1"})
    assert response.status_code == 200
    return browser


def test_generate_is_private_exact_eight_and_reuses_identical_file(private_env, monkeypatch):
    def no_store(*args):raise AssertionError("Generate must not access a cloud or database")
    monkeypatch.setattr(store, "get", no_store)
    assert accounts.generate(private_env, CSV) == {"accounts": 8, "created_file": True}
    value, before = inventory(private_env), private_env.read_bytes()
    assert len(value["accounts"]) == 8
    assert [entry["unit"] for entry in value["accounts"]] == UNITS
    assert [entry["username"] for entry in value["accounts"]] == ["unit-" + unit.lower() for unit in UNITS]
    assert len({entry["tenant_id"] for entry in value["accounts"]}) == 8
    assert len({entry["password"] for entry in value["accounts"]}) == 8
    assert accounts.generate(private_env, CSV) == {"accounts": 8, "created_file": False}
    assert private_env.read_bytes() == before


def test_intentional_duplicate_unit_labels_still_get_separate_accounts(private_env):
    units = ["1A", "1A", *UNITS[2:]]
    accounts.generate(private_env, ",".join(units))
    rows = inventory(private_env)["accounts"]
    assert rows[0]["username"] == "unit-1a" and rows[1]["username"] == "unit-1a-2"
    assert rows[0]["unit"] == rows[1]["unit"] == "1A"
    assert rows[0]["tenant_id"] != rows[1]["tenant_id"]


@pytest.mark.parametrize("units", ["1A,1B", CSV + ",4A", "1A,1B,2A,2B,2C,3A,3B,", "1A,1B,2A,2B,2C,3A,3B,bad/label"])
def test_generation_rejects_wrong_unit_count_or_path_like_labels(private_env, units):
    with pytest.raises(accounts.AccountError):accounts.generate(private_env, units)
    assert not private_env.exists()


def test_provision_creates_eight_hash_only_rows_then_commits_ready_registry(private_env):
    result = accounts.provision(private_env, CSV)
    value = inventory(private_env)
    assert result == {"accounts": 8, "created_users": 8, "ready": True, "created_file": True}
    registry = store.get("registry")
    assert registry["status"] == "ready" and registry["slots"] == accounts._slots(value)
    for entry, row in zip(value["accounts"], user_rows(value)):
        assert row["tenant_id"] == entry["tenant_id"] and row["unit"] == entry["unit"]
        assert auth.verify_password(row["password_hash"], entry["password"])
        assert "password" not in row and entry["password"] not in json.dumps(row)


def test_provision_retry_preserves_hashes_ids_versions_and_private_file(private_env):
    accounts.provision(private_env, CSV)
    value, before = inventory(private_env), private_env.read_bytes()
    initial, registry = user_rows(value), store.get("registry")
    result = accounts.provision(private_env, CSV)
    assert result["created_users"] == 0 and result["created_file"] is False
    assert user_rows(value) == initial and store.get("registry") == registry
    assert private_env.read_bytes() == before


def test_partial_provision_is_not_ready_and_retry_uses_same_secret_inventory(private_env, monkeypatch):
    actual = store.put_if_version
    def interrupted(record_id, *args, **kwargs):
        if record_id == "user:unit-2a":raise store.Unavailable("fixed safe simulated interruption")
        return actual(record_id, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(store, "put_if_version", interrupted)
        with pytest.raises(store.Unavailable):accounts.provision(private_env, CSV)
    value, before = inventory(private_env), private_env.read_bytes()
    existing = [store.get("user:unit-1a"), store.get("user:unit-1b")]
    assert store.get("registry")["status"] == "provisioning"
    result = accounts.provision(private_env, CSV)
    assert result["created_users"] == 6 and store.get("registry")["status"] == "ready"
    assert [store.get("user:unit-1a"), store.get("user:unit-1b")] == existing
    assert private_env.read_bytes() == before


def test_missing_file_with_existing_registry_never_generates_new_credentials(private_env):
    accounts.provision(private_env, CSV)
    value, original = inventory(private_env), user_rows(inventory(private_env))
    private_env.unlink()
    with pytest.raises(accounts.AccountError):accounts.provision(private_env, CSV)
    assert not private_env.exists() and user_rows(value) == original


def test_store_error_is_not_mistaken_for_absent_registry(private_env, monkeypatch):
    def unavailable(*args):raise store.Unavailable("fixed safe failure")
    monkeypatch.setattr(store, "get", unavailable)
    with pytest.raises(store.Unavailable):accounts.provision(private_env, CSV)
    assert not private_env.exists()


def test_different_inventory_cannot_adopt_existing_registry(private_env):
    accounts.provision(private_env, CSV)
    original, registry = user_rows(inventory(private_env)), store.get("registry")
    different = accounts.new_inventory(UNITS)
    with pytest.raises(accounts.AccountError):accounts.apply_inventory(different)
    assert user_rows(inventory(private_env)) == original and store.get("registry") == registry


def test_tenant_changed_password_is_not_reset_by_provision(private_env):
    accounts.provision(private_env, CSV)
    value = inventory(private_env)
    row = store.get("user:unit-1a")
    changed = store.put_if_version(row["id"], {**row, "password_hash": auth.hash_password("Tenant chosen fictional phrase 234!"), "credential_version": 2}, row["version"])
    with pytest.raises(accounts.AccountError):accounts.provision(private_env, CSV)
    assert store.get(row["id"]) == changed
    assert not auth.verify_password(changed["password_hash"], value["accounts"][0]["password"])


def test_ready_registry_missing_user_is_not_silently_recreated(private_env):
    accounts.provision(private_env, CSV)
    row = store.get("user:unit-1a")
    assert store.delete(row["id"], row["version"])
    with pytest.raises(accounts.AccountError):accounts.provision(private_env, CSV)
    assert store.get(row["id"]) is None


def test_apply_stdin_returns_only_counts_and_booleans(private_env, monkeypatch, capsys):
    value = accounts.new_inventory(UNITS)
    monkeypatch.setattr(accounts.sys, "stdin", io.StringIO(json.dumps(value)))
    assert accounts.main(["apply", "--credentials-stdin"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {"accounts": 8, "created_users": 8, "ready": True}
    assert not captured.err and not private_env.exists()
    assert all(entry["password"] not in captured.out for entry in value["accounts"])


@pytest.mark.parametrize("change", ["extra_account", "missing_account", "duplicate_id", "duplicate_username", "extra_secret_field"])
def test_invalid_inventories_are_rejected_before_any_registry_creation(private_env, change):
    value = accounts.new_inventory(UNITS)
    if change == "extra_account":value["accounts"].append(copy.deepcopy(value["accounts"][0]))
    elif change == "missing_account":value["accounts"].pop()
    elif change == "duplicate_id":value["accounts"][1]["tenant_id"] = value["accounts"][0]["tenant_id"]
    elif change == "duplicate_username":value["accounts"][1]["username"] = value["accounts"][0]["username"]
    else:value["accounts"][0]["extra"] = "fictional-secret-value"
    with pytest.raises(accounts.AccountError):accounts.apply_inventory(value)
    assert store.get("registry") is None


def test_reset_preserves_identity_revokes_sessions_and_only_changes_selected_password(private_env):
    accounts.provision(private_env, CSV)
    before = inventory(private_env)
    browser = signed_in(before)
    row = store.get("user:unit-1a")
    result = accounts.reset(private_env, "unit-1a")
    after, current = inventory(private_env), store.get("user:unit-1a")
    assert result["reset_complete"] and current["tenant_id"] == row["tenant_id"]
    assert current["credential_version"] == row["credential_version"] + 1
    assert after["accounts"][1:] == before["accounts"][1:]
    assert after["accounts"][0]["password"] != before["accounts"][0]["password"]
    assert auth.verify_password(current["password_hash"], after["accounts"][0]["password"])
    assert browser.get("/api/tenant/session").status_code == 401
    assert not accounts._pending_path(private_env).exists()


def test_reset_recovers_pending_password_when_database_write_was_interrupted(private_env, monkeypatch):
    accounts.provision(private_env, CSV)
    original = inventory(private_env)
    actual = store.put_if_version
    def broken(record_id, *args, **kwargs):
        if record_id == "user:unit-1a":raise store.Unavailable("fixed safe failure")
        return actual(record_id, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(store, "put_if_version", broken)
        with pytest.raises(store.Unavailable):accounts.reset(private_env, "unit-1a")
    pending = accounts._read_private(accounts._pending_path(private_env))
    assert inventory(private_env) == original
    assert pending["inventory"]["accounts"][0]["password"] != original["accounts"][0]["password"]
    accounts.reset(private_env, "unit-1a")
    assert inventory(private_env) == pending["inventory"]
    assert store.get("user:unit-1a")["credential_version"] == 2


def test_reset_recovers_after_database_commit_without_incrementing_version_twice(private_env, monkeypatch):
    accounts.provision(private_env, CSV)
    actual = accounts._write_private
    def interrupted(path, value, **kwargs):
        if Path(path) == private_env:raise OSError("fixed safe interruption")
        return actual(path, value, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(accounts, "_write_private", interrupted)
        with pytest.raises(OSError):accounts.reset(private_env, "unit-1a")
    pending = accounts._read_private(accounts._pending_path(private_env))
    before = store.get("user:unit-1a")
    assert before["credential_version"] == 2
    result = accounts.reset(private_env, "unit-1a")
    assert result["changed"] is False and result["reset_complete"]
    assert store.get("user:unit-1a") == before
    assert inventory(private_env) == pending["inventory"]


def test_reset_pending_conflict_preserves_current_database_and_private_files(private_env, monkeypatch):
    accounts.provision(private_env, CSV)
    actual = store.put_if_version
    def interrupted(record_id, *args, **kwargs):
        if record_id == "user:unit-1a":raise store.Unavailable("fixed safe failure")
        return actual(record_id, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(store, "put_if_version", interrupted)
        with pytest.raises(store.Unavailable):accounts.reset(private_env, "unit-1a")
    row = store.get("user:unit-1a")
    changed = store.put_if_version(row["id"], {**row, "active": False, "credential_version": 2}, row["version"])
    private_before = private_env.read_bytes()
    with pytest.raises(accounts.AccountError):accounts.reset(private_env, "unit-1a")
    assert store.get(row["id"]) == changed and private_env.read_bytes() == private_before
    assert accounts._pending_path(private_env).exists()


def test_disable_enable_never_revives_the_original_cookie(private_env):
    accounts.provision(private_env, CSV)
    value = inventory(private_env)
    browser = signed_in(value)
    initial = store.get("user:unit-1a")
    accounts.set_active(private_env, "unit-1a", False)
    assert browser.get("/api/tenant/session").status_code == 401
    assert accounts.set_active(private_env, "unit-1a", False)["changed"] is False
    accounts.set_active(private_env, "unit-1a", True)
    current = store.get("user:unit-1a")
    assert current["tenant_id"] == initial["tenant_id"] and current["credential_version"] == 3
    assert current["password_hash"] == initial["password_hash"]
    assert browser.get("/api/tenant/session").status_code == 401
    assert signed_in(value).get("/api/tenant/session").status_code == 200


def test_private_file_cannot_be_generated_inside_public_source_directories(private_env, monkeypatch, tmp_path):
    source = tmp_path / "source-tree"
    monkeypatch.setattr(accounts, "ROOT", source)
    public = source / "docs" / "tenant-credentials.json"
    with pytest.raises(accounts.AccountError):accounts.generate(public, CSV)
    assert not public.exists()


def test_invalid_cli_arguments_do_not_echo_accidentally_supplied_secrets(private_env, capsys):
    with pytest.raises(SystemExit):accounts.main(["reset", "--password", "FICTIONAL-RAW-SECRET"])
    captured = capsys.readouterr()
    assert "FICTIONAL-RAW-SECRET" not in captured.out + captured.err


def test_private_file_lock_is_released_if_holder_exits_without_cleanup(private_env):
    import subprocess, sys
    package_path = str(Path(accounts.__file__).parent)
    code = "import os,sys,ticketpilot;ticketpilot.__path__.insert(0,sys.argv[1]);from ticketpilot import tenant_accounts as a; a.ROOT=__import__('pathlib').Path(sys.argv[2]);ctx=a._file_lock(sys.argv[3]);ctx.__enter__();os._exit(0)"
    subprocess.run([sys.executable, "-c", code, package_path, str(accounts.ROOT), str(private_env)], check=True)
    assert private_env.with_name(private_env.name + ".lock").exists()
    with accounts._file_lock(private_env):pass


def test_corrupt_pending_reset_cannot_overwrite_other_local_credentials(private_env, monkeypatch):
    accounts.provision(private_env, CSV)
    actual = store.put_if_version
    def interrupted(record_id, *args, **kwargs):
        if record_id == "user:unit-1a":raise store.Unavailable("fixed safe interruption")
        return actual(record_id, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(store, "put_if_version", interrupted)
        with pytest.raises(store.Unavailable):accounts.reset(private_env, "unit-1a")
    pending_path = accounts._pending_path(private_env)
    pending = accounts._read_private(pending_path)
    pending["inventory"]["accounts"][1]["password"] = "Corrupt unrelated fictional password 987!"
    accounts._write_private(pending_path, pending)
    before, row = private_env.read_bytes(), store.get("user:unit-1a")
    with pytest.raises(accounts.AccountError):accounts.reset(private_env, "unit-1a")
    assert private_env.read_bytes() == before and store.get(row["id"]) == row


@pytest.mark.parametrize("folder", [".secrets", ".tools"])
def test_ignored_private_fixture_directories_are_supported(private_env, monkeypatch, tmp_path, folder):
    source = tmp_path / "source-tree"
    monkeypatch.setattr(accounts, "ROOT", source)
    path = source / folder / "fictional-tenant-accounts.json"
    assert accounts.generate(path, CSV)["created_file"] is True
    assert len(inventory(path)["accounts"]) == 8
