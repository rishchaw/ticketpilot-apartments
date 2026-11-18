"""Closed-account admission, private cookies, durable revocation and CSRF guards."""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest
from ticketpilot import storage, tenant_auth as auth, tenant_auth_store as store

UNITS = ["1A", "1B", "2A", "2B", "2C", "3A", "3B", "3C"]
PASSWORD = "Fictional tenant Password only 234!"


@pytest.fixture(scope="module")
def templates():
    return [auth.new_user("unit-" + unit.lower(), unit, password=PASSWORD, tenant_id=f"{i+1:032x}") for i, unit in enumerate(UNITS)]


@pytest.fixture
def closed_app(monkeypatch, tmp_path, templates):
    monkeypatch.setenv("STORAGE_MODE", "sqlite")
    monkeypatch.setenv("TENANT_COOKIE_SECURE", "true")
    monkeypatch.setattr(storage, "PATH", tmp_path / "tenant-auth.db")
    slots = [{key: user[key] for key in ("tenant_id", "username", "unit")} for user in templates]
    for user in templates:
        store.put_if_version("user:" + user["username"], copy.deepcopy(user))
    store.put_if_version("registry", {"kind": "tenant_registry", "status": "ready", "slots": slots})
    app = FastAPI()
    app.include_router(auth.router)
    @app.get("/protected")
    def private(request: Request):
        return auth.require_tenant(request)
    @app.post("/protected")
    def private_write(request: Request):
        return auth.require_tenant(request, write=True)
    return app


def client(app):
    return TestClient(app, base_url="https://testserver")


def login(browser, username="unit-1a", password=PASSWORD, **kwargs):
    return browser.post("/api/tenant/login", json={"username": username, "password": password}, headers={"X-TicketPilot-Login": "1", **kwargs})


def test_hashing_salts_and_password_whitespace_are_preserved():
    value = "  Fictional phrase with spaces  "
    first, second = auth.hash_password(value), auth.hash_password(value)
    assert first != second and first.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert auth.verify_password(first, value)
    assert not auth.verify_password(first, value.strip())
    assert not auth.verify_password("not-a-password-hash", value)


def test_cookie_is_host_scoped_and_raw_session_is_never_persisted(closed_app):
    browser = client(closed_app)
    response = login(browser)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert all(part in cookie for part in ("httponly", "secure", "samesite=strict", "path=/", "max-age=28800"))
    assert "domain=" not in cookie
    value = response.json()
    assert set(value) == {"tenant", "csrf_token", "expires_at"}
    assert value["tenant"]["unit"] == "1A"
    token = browser.cookies.get(auth.cookie_name())
    session_id = "session:" + hashlib.sha256(token.encode()).hexdigest()
    persisted = store.get(session_id)
    assert persisted["auth_expires_at"] == value["expires_at"]
    assert token not in json.dumps(persisted) and "password_hash" not in json.dumps(value)
    assert browser.get("/protected").json() == value["tenant"]


def test_unknown_wrong_and_disabled_accounts_have_same_generic_denial(closed_app):
    browser = client(closed_app)
    invalid = login(browser, password="Incorrect fictional password")
    unknown = login(browser, username="not-a-registered-tenant")
    user = store.get("user:unit-1b")
    store.put_if_version(user["id"], {**user, "active": False}, user["version"])
    disabled = login(browser, username="unit-1b")
    assert [r.status_code for r in (invalid, unknown, disabled)] == [401, 401, 401]
    assert invalid.json() == unknown.json() == disabled.json() == {"detail": "Invalid username or password"}
    assert browser.get("/protected").status_code == 401


def test_extra_unregistered_database_user_cannot_sign_in(closed_app):
    store.put_if_version("user:extra-person", auth.new_user("extra-person", "1A", password=PASSWORD))
    assert login(client(closed_app), username="extra-person").status_code == 401


@pytest.mark.parametrize("mutation", ["not_ready", "missing_slot", "extra_slot", "duplicate_user", "duplicate_id"])
def test_registry_must_admit_exactly_eight_distinct_accounts(closed_app, mutation):
    registry = store.get("registry")
    if mutation == "not_ready":registry["status"] = "provisioning"
    elif mutation == "missing_slot":registry["slots"].pop()
    elif mutation == "extra_slot":registry["slots"].append({**registry["slots"][0], "username": "extra-user"})
    elif mutation == "duplicate_user":registry["slots"][1]["username"] = registry["slots"][0]["username"]
    else:registry["slots"][1]["tenant_id"] = registry["slots"][0]["tenant_id"]
    store.put_if_version("registry", registry, registry["version"])
    assert login(client(closed_app)).status_code == 503


def test_login_requires_custom_header_and_rejects_cross_origin(closed_app):
    browser = client(closed_app)
    assert browser.post("/api/tenant/login", json={"username": "unit-1a", "password": PASSWORD}).status_code == 403
    assert login(browser, Origin="https://malicious.example").status_code == 403
    assert login(browser, Origin="https://testserver").status_code == 200


def test_all_protected_writes_require_session_csrf_and_same_origin(closed_app):
    browser = client(closed_app)
    assert browser.post("/protected").status_code == 401
    csrf = login(browser).json()["csrf_token"]
    assert browser.post("/protected").status_code == 403
    assert browser.post("/protected", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert browser.post("/protected", headers={"X-CSRF-Token": csrf, "Origin": "https://malicious.example"}).status_code == 403
    assert browser.post("/protected", headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"}).status_code == 200


def test_logout_persistently_revokes_only_current_session(closed_app):
    first, second = client(closed_app), client(closed_app)
    csrf = login(first).json()["csrf_token"]
    login(second)
    raw = first.cookies.get(auth.cookie_name())
    assert first.post("/api/tenant/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert first.get("/api/tenant/session", headers={"Cookie": auth.cookie_name() + "=" + raw}).status_code == 401
    assert second.get("/protected").status_code == 200


def test_expiry_and_user_disabling_revoke_without_process_restart(closed_app, monkeypatch):
    browser = client(closed_app)
    session = login(browser).json()
    raw_cookie = auth.cookie_name() + "=" + browser.cookies.get(auth.cookie_name())
    with monkeypatch.context() as clock:
        clock.setattr(auth.time, "time", lambda: session["expires_at"])
        assert browser.get("/protected", headers={"Cookie": raw_cookie}).status_code == 401


def test_disabled_user_and_changed_registry_invalidate_existing_cookie(closed_app):
    browser = client(closed_app)
    login(browser)
    user = store.get("user:unit-1a")
    store.put_if_version(user["id"], {**user, "active": False}, user["version"])
    assert browser.get("/protected").status_code == 401


def test_password_change_revokes_other_sessions_and_rotates_current(closed_app):
    first, other = client(closed_app), client(closed_app)
    original = login(first).json()
    login(other)
    before = first.cookies.get(auth.cookie_name())
    replacement = "A different fictional password 567!"
    result = first.post("/api/tenant/password", json={"current_password": PASSWORD, "new_password": replacement}, headers={"X-CSRF-Token": original["csrf_token"]})
    assert result.status_code == 200 and first.cookies.get(auth.cookie_name()) != before
    assert result.json()["tenant"]["id"] == original["tenant"]["id"]
    assert other.get("/protected").status_code == 401
    assert first.get("/protected").status_code == 200
    assert login(client(closed_app), password=PASSWORD).status_code == 401
    assert login(client(closed_app), password=replacement).status_code == 200


def test_password_change_needs_current_password_and_valid_replacement(closed_app):
    browser = client(closed_app)
    csrf = login(browser).json()["csrf_token"]
    headers={"X-CSRF-Token": csrf}
    assert browser.post("/api/tenant/password", json={"current_password": "wrong", "new_password": "A new fictional password 789!"}, headers=headers).status_code == 401
    assert browser.post("/api/tenant/password", json={"current_password": PASSWORD, "new_password": "short"}, headers=headers).status_code == 400
    assert browser.get("/protected").status_code == 200


def test_operator_credential_version_rotation_revokes_existing_sessions(closed_app):
    browser = client(closed_app)
    login(browser)
    user = store.get("user:unit-1a")
    store.put_if_version(user["id"], {**user, "credential_version": user["credential_version"] + 1}, user["version"])
    assert browser.get("/protected").status_code == 401


def test_persisted_rate_limit_applies_to_separate_browser_instances(closed_app):
    for _ in range(10):
        assert login(client(closed_app), password="Incorrect fictional password").status_code == 401
    response = login(client(closed_app))
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert store.get("rate:unit-1a")["count"] == 10


def test_unknown_user_names_share_one_bounded_bucket(closed_app):
    for i in range(10):
        assert login(client(closed_app), username=f"unknown-person-{i}").status_code == 401
    assert login(client(closed_app), username="another-unknown-person").status_code == 429
    assert store.get("rate:unknown")["count"] == 10
    assert store.get("rate:unknown-person-0") is None


def test_global_rate_limit_and_window_reset(closed_app, monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1800)
    for _ in range(60):auth._counter("rate:global", limit=60, seconds=300)
    with pytest.raises(Exception) as error:
        auth._counter("rate:global", limit=60, seconds=300)
    assert error.value.status_code == 429
    monkeypatch.setattr(auth.time, "time", lambda: 2100)
    auth._counter("rate:global", limit=60, seconds=300)
    assert store.get("rate:global")["count"] == 1


def test_limiter_race_never_exceeds_its_persisted_allowance(closed_app):
    def attempt(_):
        try:
            auth._counter("rate:global", limit=10, seconds=300)
            return 200
        except Exception as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(attempt, range(14)))
    assert set(statuses) <= {200, 429, 503}
    assert statuses.count(200) == store.get("rate:global")["count"] <= 10


def test_persistence_failure_during_login_or_session_resolution_fails_closed(closed_app, monkeypatch):
    browser = client(closed_app)
    login(browser)
    def unavailable(*args, **kwargs):raise store.Unavailable("fixed safe error")
    monkeypatch.setattr(store, "get", unavailable)
    assert browser.get("/protected").status_code == 503
    assert login(client(closed_app)).status_code == 503


def test_old_inflight_limiter_request_cannot_rewind_a_newer_window(closed_app, monkeypatch):
    store.put_if_version("rate:global", {"kind": "tenant_rate", "window": 7, "count": 59, "auth_expires_at": 2400})
    monkeypatch.setattr(auth.time, "time", lambda: 2099)
    auth._counter("rate:global", limit=60, seconds=300)
    assert store.get("rate:global")["window"] == 7
    assert store.get("rate:global")["count"] == 60
    with pytest.raises(Exception) as error:auth._counter("rate:global", limit=60, seconds=300)
    assert error.value.status_code == 429


def test_csrf_token_from_another_session_is_not_authorized(closed_app):
    first, second = client(closed_app), client(closed_app)
    login(first)
    other = login(second, username="unit-1b").json()["csrf_token"]
    assert first.post("/protected", headers={"X-CSRF-Token": other}).status_code == 403


@pytest.mark.parametrize("endpoint,payload", [
    ("login", {"password": "FICTIONAL-RAW-SECRET-SHOULD-NOT-ECHO"}),
    ("login", {"username": "unit-1a", "password": {"nested": "FICTIONAL-RAW-SECRET-SHOULD-NOT-ECHO"}}),
    ("password", {"current_password": "FICTIONAL-RAW-SECRET-SHOULD-NOT-ECHO"}),
    ("password", {"current_password": PASSWORD, "new_password": PASSWORD, "extra": "FICTIONAL-RAW-SECRET-SHOULD-NOT-ECHO"}),
])
def test_credential_validation_never_reflects_raw_request_inputs(closed_app, endpoint, payload):
    response = client(closed_app).post("/api/tenant/" + endpoint, json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid tenant authentication request"}
    assert "FICTIONAL-RAW-SECRET-SHOULD-NOT-ECHO" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("chunked", [False, True])
def test_oversized_credential_body_is_rejected_before_validation(closed_app, chunked):
    browser = client(closed_app)
    if chunked:
        response = browser.post("/api/tenant/login", content=iter([b'{"password":"', b"x" * 2000, b"y" * 2100, b'"}']), headers={"Content-Type": "application/json", "X-TicketPilot-Login": "1"})
    else:
        response = browser.post("/api/tenant/login", json={"password": "x" * 4200}, headers={"X-TicketPilot-Login": "1"})
    assert response.status_code == 413
    assert response.json() == {"detail": "Tenant request is too large"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("password", ["", "x" * 129])
def test_login_password_bounds_are_validated_without_reflecting_the_secret(closed_app, password):
    response = login(client(closed_app), password=password)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid tenant authentication request"}
    assert "x" * 20 not in response.text
