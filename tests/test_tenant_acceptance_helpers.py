"""Acceptance tooling must keep identities/cookies isolated and diagnostics private."""
import base64
import json
from unittest.mock import Mock
import httpx
import pytest
from scripts import validate_gcp_deployment as checks
from scripts import validate_aws_deployment as aws_checks
from scripts.validate_lambda_image import LambdaRuntimeTransport


def test_inventory_requires_exact_eight_distinct_private_identities(tmp_path):
    inventory = checks.synthetic_inventory()
    assert len(inventory["accounts"]) == 8
    assert len({a["username"] for a in inventory["accounts"]}) == 8
    assert len({a["password"] for a in inventory["accounts"]}) == 8
    assert checks.validate_inventory(inventory) is inventory
    inventory["accounts"].pop()
    with pytest.raises(checks.ValidationError, match="eight-account"):
        checks.validate_inventory(inventory)
    path = tmp_path / "missing-private.json"
    with pytest.raises(checks.ValidationError, match="Restore the private"):
        checks.load_tenant_inventory(path)
    assert not path.exists()  # A read check must never provision/reset an account.


def test_invalid_inventory_diagnostic_does_not_echo_password_or_username():
    inventory = checks.synthetic_inventory()
    private_value = "private-credential-that-must-not-appear"
    inventory["accounts"][0]["username"] = private_value + "@invalid"
    with pytest.raises(checks.ValidationError) as error:
        checks.validate_inventory(inventory)
    assert private_value not in str(error.value)
    inventory = checks.synthetic_inventory()
    inventory["accounts"][1]["tenant_id"] = inventory["accounts"][0]["tenant_id"]
    with pytest.raises(checks.ValidationError, match="distinct"):
        checks.validate_inventory(inventory)


def test_duplicate_unit_labels_are_allowed_but_principals_remain_distinct():
    inventory = checks.synthetic_inventory()
    inventory["accounts"][1]["unit"] = inventory["accounts"][0]["unit"]
    checks.validate_inventory(inventory)
    assert inventory["accounts"][0]["tenant_id"] != inventory["accounts"][1]["tenant_id"]


def test_tenant_wrapper_overrides_transport_cookie_jar_and_scopes_csrf():
    requests = []
    def receive(request):
        requests.append(request)
        return httpx.Response(200, json={})
    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(receive), cookies={"tenant": "other-person-session"}) as client:
        actor = checks.TenantHTTP(client, {"id": "owner"}, {"tenant": "own-session"}, "own-csrf")
        actor.get("/read")
        actor.post("/write", json={})
        actor.post("/missing-csrf", csrf=False, json={})
    assert all(r.headers["cookie"] == "tenant=own-session" for r in requests)
    assert "x-csrf-token" not in requests[0].headers
    assert requests[1].headers["x-csrf-token"] == "own-csrf"
    assert "x-csrf-token" not in requests[2].headers


def login_transport(account, *, cookie_attributes="HttpOnly; Secure; SameSite=Strict; Path=/"):
    def receive(request):
        if request.url.path == "/api/tenant/login":
            assert request.headers["x-ticketpilot-login"] == "1"
            assert request.headers["cookie"] == ""
            return httpx.Response(200, json={"tenant": {"id": account["tenant_id"], "username": account["username"], "unit": account["unit"]},
                "csrf_token": "synthetic-csrf-token-value-123456789", "expires_at": 9999999999},
                headers={"set-cookie": "tenant=synthetic-opaque-session; " + cookie_attributes})
        raise AssertionError("Unexpected endpoint")
    return httpx.MockTransport(receive)


def test_login_accepts_protected_cookie_without_putting_password_in_session_repr():
    account = checks.synthetic_inventory()["accounts"][0]
    with httpx.Client(base_url="https://example.test", transport=login_transport(account)) as client:
        actor = checks.tenant_login(client, account)
        assert actor.principal["id"] == account["tenant_id"]
        assert checks.capture_sessions(client)[account["username"]] is actor
        assert account["password"] not in repr(actor)


@pytest.mark.parametrize("attributes", ["Secure; SameSite=Strict; Path=/", "HttpOnly; SameSite=Strict; Path=/", "HttpOnly; Secure; SameSite=Lax; Path=/"])
def test_login_rejects_missing_cookie_security(attributes):
    account = checks.synthetic_inventory()["accounts"][0]
    with httpx.Client(base_url="https://example.test", transport=login_transport(account, cookie_attributes=attributes)) as client:
        with pytest.raises(checks.ValidationError, match="cookie"):
            checks.tenant_login(client, account)


def test_restart_restores_same_opaque_cookie_and_never_calls_login():
    identity = {"id": "synthetic-owner", "username": "unit-1", "unit": "1"}
    seen = []
    def receive(request):
        seen.append(request)
        assert request.url.path == "/api/tenant/session"
        assert request.headers["cookie"] == "tenant=previous-cookie"
        return httpx.Response(200, json={"tenant": identity, "csrf_token": "restored-csrf"})
    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(receive)) as client:
        prior = checks.TenantHTTP(None, identity, {"tenant": "previous-cookie"}, "old-csrf")
        restored = checks.restore_sessions(client, {"unit-1": prior})
        assert restored["unit-1"].csrf_token == "restored-csrf"
        assert len(seen) == 1


def test_lambda_transport_serializes_and_preserves_http_api_v2_cookies():
    seen = []
    def runtime(request):
        event = json.loads(request.content)
        seen.append(event)
        return httpx.Response(200, json={"statusCode": 200, "headers": {"content-type": "application/json"},
            "cookies": ["tenant=rotated-cookie; Secure; HttpOnly; SameSite=Strict; Path=/", "extra=fixture; Path=/"],
            "body": base64.b64encode(b'{"ok":true}').decode(), "isBase64Encoded": True})
    with httpx.Client(transport=httpx.MockTransport(runtime)) as gateway:
        with httpx.Client(base_url="https://localhost", transport=LambdaRuntimeTransport(gateway, "http://runtime.test/invoke")) as client:
            response = client.post("/api/tenant/logout", headers={"cookie": "tenant=old-cookie; extra=fixture", "x-csrf-token": "fixture-csrf"}, json={})
            assert response.json() == {"ok": True}
            assert len(response.headers.get_list("set-cookie")) == 2
    assert seen[0]["cookies"] == ["tenant=old-cookie", "extra=fixture"]
    assert seen[0]["headers"]["x-csrf-token"] == "fixture-csrf"
    assert seen[0]["headers"]["x-forwarded-proto"] == "https"


def test_lambda_runtime_error_does_not_echo_payload_details():
    private = "must-never-appear-in-runtime-error"
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"errorMessage": private}))) as gateway:
        with httpx.Client(base_url="https://localhost", transport=LambdaRuntimeTransport(gateway, "http://runtime.test/invoke")) as client:
            with pytest.raises(checks.ValidationError) as error:
                client.get("/health")
            assert private not in str(error.value)


def test_cleanup_will_not_remove_record_reassigned_to_another_tenant():
    marker = "Synthetic AWS check test: "
    receipt = checks.ConcernReceipt("apt_" + "a" * 32, marker + "water", key="synthetic-key", tenant_id="first-owner")
    table = Mock()
    table.get_item.return_value = {"Item": {"id": receipt.record_id, "title": receipt.title, "queue": "apartment_tickets",
        "kind": "apartment_ticket", "tenant_id": "different-owner", "version": 1, "updated_at": "now"}}
    report = aws_checks.cleanup_owned(table, [receipt], marker)
    assert report["skipped"] == 1
    table.delete_item.assert_not_called()
