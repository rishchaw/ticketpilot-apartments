"""Tenant identity gates pages, intake and private concern capabilities.

Every account, concern and notice is fictional and isolated in one temporary
SQLite database. No credential file, cloud profile or real tenant data is read.
"""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlparse
import pytest
from fastapi.testclient import TestClient
from ticketpilot.api import app
from ticketpilot import apartment_store, apartments, storage, tenant_auth as auth, tenant_auth_store as auth_store

UNITS = [str(i) for i in range(1, 9)]
PASSWORD = "Fictional portal password only 246!"
OWNER = {"X-Admin-Token": "fictional-portal-manager-code"}
BODY = {"unit": "1", "category": "water", "title": "Synthetic private portal concern", "description": "Fictional portal isolation check. No actual repair or tenant data.", "language": "fil"}


@pytest.fixture(scope="module")
def account_templates():
    return [auth.new_user("unit-" + unit, unit, password=PASSWORD, tenant_id=f"{i+1:032x}") for i, unit in enumerate(UNITS)]


def sign_in(browser, username):
    response = browser.post("/api/tenant/login", json={"username": username, "password": PASSWORD}, headers={"X-TicketPilot-Login": "1"})
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def site(monkeypatch, tmp_path, account_templates):
    for key, value in {"STORAGE_MODE": "sqlite", "SQLITE_PATH": str(tmp_path / "tenant-portal.db"), "TENANT_COOKIE_SECURE": "true", "ADMIN_TOKEN": OWNER["X-Admin-Token"], "METRICS_TOKEN": "fictional-portal-metrics", "APARTMENT_UNITS": ",".join(UNITS), "LLM_PROVIDER": "none", "AWS_EC2_METADATA_DISABLED": "true"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(storage, "PATH", tmp_path / "tenant-portal.db")
    apartments._attempts.clear()
    slots = []
    for template in account_templates:
        auth_store.put_if_version("user:" + template["username"], deepcopy(template))
        slots.append({key: template[key] for key in ("tenant_id", "username", "unit")})
    auth_store.put_if_version("registry", {"kind": "tenant_registry", "status": "ready", "slots": slots})
    clients = [TestClient(app, base_url="https://testserver") for _ in range(3)]
    anonymous, first, second = clients
    first_session, second_session = sign_in(first, "unit-1"), sign_in(second, "unit-2")
    yield SimpleNamespace(anonymous=anonymous, first=first, second=second, first_session=first_session, second_session=second_session)
    for client in clients:
        client.close()
    apartments._attempts.clear()


def create(site):
    response = site.first.post("/api/apartments/concerns", json=BODY, headers={"X-CSRF-Token": site.first_session["csrf_token"]})
    assert response.status_code == 201
    return response.json()


def concern_path(receipt):
    return "/api/apartments/concerns/" + receipt["ticket"]["id"]


@pytest.mark.parametrize("path", ["/", "/tenant"])
def test_anonymous_portal_redirects_only_to_login(site, path):
    response = site.anonymous.get(path, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    target = urlparse(response.headers["location"])
    assert target.path == "/tenant/login" and not target.query
    assert target.netloc in ("", "testserver")
    assert "concernForm" not in response.text


def test_login_is_a_minimal_public_shell_and_manager_shell_remains_separate(site):
    login = site.anonymous.get("/tenant/login")
    assert login.status_code == 200
    assert "tenantLoginForm" in login.text
    assert login.headers.get("cache-control") == "no-store"
    assert login.headers.get("referrer-policy") == "no-referrer"
    assert "frame-ancestors 'none'" in login.headers.get("content-security-policy", "")
    assert all(marker not in login.text for marker in ("concernForm", "trackingPanel", "buildingNotice", "managerContent"))
    assert all("unit-" + unit not in login.text for unit in UNITS)
    assert site.anonymous.get("/manager").status_code == 200
    assert site.anonymous.get("/api/apartments/manage/concerns").status_code == 401
    assert site.first.get("/api/apartments/manage/concerns").status_code == 401
    assert site.first.get("/api/apartments/manage/notice").status_code == 401
    assert site.anonymous.get("/api/apartments/config", headers=OWNER).status_code == 200


def test_anonymous_config_does_not_disclose_notice_or_unit_inventory(site):
    stamp = apartments.now()
    apartment_store.save({"id": "apartment_notice", "queue": "apartment_notices", "created_at": stamp, "updated_at": stamp, "title": "FICTIONAL PRIVATE NOTICE", "message": "Only signed-in residents may read this synthetic update.", "active": True})
    response = site.anonymous.get("/api/apartments/config")
    assert response.status_code == 401
    assert {"units", "categories", "guidance", "notice"}.isdisjoint(response.json())
    assert "FICTIONAL PRIVATE NOTICE" not in response.text
    assert "synthetic update" not in response.text
    private = site.first.get("/api/apartments/config")
    assert private.status_code == 200 and private.json()["notice"]["title"] == "FICTIONAL PRIVATE NOTICE"


def test_anonymous_intake_and_capability_reads_require_a_login_cookie(site):
    response = site.anonymous.post("/api/apartments/concerns", json=BODY)
    assert response.status_code == 401
    receipt = create(site)
    headers = {"X-Ticket-Key": receipt["tracking_key"]}
    assert site.anonymous.get(concern_path(receipt), headers=headers).status_code == 401
    assert site.anonymous.post(concern_path(receipt) + "/replies", json={"version": 1, "message": "Synthetic anonymous reply"}, headers=headers).status_code == 401
    site.first.cookies.clear()
    assert site.first.get(concern_path(receipt), headers=headers).status_code == 401


def test_authenticated_creation_is_bound_to_account_and_hides_identity_fields(site):
    receipt = create(site)
    stored = apartment_store.get(receipt["ticket"]["id"])
    assert stored["unit"] == "1"
    assert stored["tenant_id"] == site.first_session["tenant"]["id"]
    assert {"tenant_id", "tracking_hash", "password_hash", "credential_version"}.isdisjoint(receipt["ticket"])
    forged = site.first.post("/api/apartments/concerns", json={**BODY, "unit": "2"}, headers={"X-CSRF-Token": site.first_session["csrf_token"]})
    assert forged.status_code == 403
    injected = site.first.post("/api/apartments/concerns", json={**BODY, "tenant_id": site.second_session["tenant"]["id"]}, headers={"X-CSRF-Token": site.first_session["csrf_token"]})
    assert injected.status_code == 422
    assert apartment_store.get(receipt["ticket"]["id"])["tenant_id"] == site.first_session["tenant"]["id"]


def test_different_tenant_cannot_use_a_stolen_valid_tracking_key(site):
    receipt = create(site)
    path = concern_path(receipt)
    headers = {"X-Ticket-Key": receipt["tracking_key"]}
    assert site.first.get(path, headers=headers).status_code == 200
    other = site.second.get(path, headers=headers)
    assert other.status_code == 404 and BODY["title"] not in other.text
    reply = site.second.post(path + "/replies", json={"version": 1, "message": "Synthetic attempted cross-account reply"}, headers={**headers, "X-CSRF-Token": site.second_session["csrf_token"]})
    assert reply.status_code == 404
    unchanged = apartment_store.get(receipt["ticket"]["id"])
    assert unchanged["version"] == 1 and unchanged["updates"] == []


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Token": "synthetic-wrong-csrf"}])
def test_session_cookie_alone_does_not_allow_mutation(site, headers):
    assert site.first.post("/api/apartments/concerns", json=BODY, headers=headers).status_code == 403
    receipt = create(site)
    assert site.first.post(concern_path(receipt) + "/replies", json={"version": 1, "message": "Synthetic CSRF attempt"}, headers={**headers, "X-Ticket-Key": receipt["tracking_key"]}).status_code == 403
    assert apartment_store.get(receipt["ticket"]["id"])["version"] == 1


def test_unowned_legacy_concern_remains_private_until_explicit_manager_assignment(site):
    receipt = create(site)
    legacy = apartment_store.get(receipt["ticket"]["id"])
    legacy.pop("tenant_id", None)
    apartment_store.save(legacy, legacy["version"])
    key = {"X-Ticket-Key": receipt["tracking_key"]}
    assert site.first.get(concern_path(receipt), headers=key).status_code == 404
    assert site.second.get(concern_path(receipt), headers=key).status_code == 404
    manager = site.anonymous.get("/api/apartments/manage/concerns/" + receipt["ticket"]["id"], headers=OWNER)
    assert manager.status_code == 200 and manager.json()["id"] == receipt["ticket"]["id"]
    assert apartment_store.get(receipt["ticket"]["id"])["tracking_hash"] == legacy["tracking_hash"]


@pytest.mark.parametrize("password", ["SYNTHETIC_DO_NOT_ECHO_PASSWORD_" * 8, {"private": "SYNTHETIC_DO_NOT_ECHO_PASSWORD_MARKER"}])
def test_malformed_login_validation_does_not_echo_password_input(site, password):
    response = site.anonymous.post("/api/tenant/login", json={"username": "unit-1", "password": password}, headers={"X-TicketPilot-Login": "1"})
    assert response.status_code == 422
    assert "SYNTHETIC_DO_NOT_ECHO_PASSWORD" not in response.text
    assert response.headers.get("cache-control") == "no-store"


def test_login_redirect_parameters_cannot_send_a_tenant_to_an_external_site(site):
    response = site.anonymous.get("/tenant?next=https%3A%2F%2Fmalicious.example%2F&key=synthetic-query-key", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    target = urlparse(response.headers["location"])
    assert target.path == "/tenant/login" and target.netloc in ("", "testserver") and not target.query
    login = site.anonymous.get("/tenant/login?next=https%3A%2F%2Fmalicious.example%2F")
    assert login.status_code == 200 and "location" not in login.headers
    result = site.anonymous.post("/api/tenant/login?next=https%3A%2F%2Fmalicious.example%2F", json={"username": "unit-1", "password": PASSWORD}, headers={"X-TicketPilot-Login": "1"})
    assert result.status_code == 200 and "location" not in result.headers
    assert result.json()["tenant"]["unit"] == "1"
