"""The public smoke check must exercise apartments without creating tenant records."""
import httpx
import pytest
from scripts.smoke_aws import check_endpoint


def transport(allow_manager=False, storage="dynamodb", allow_tenant_config=False, allow_tenant_portal=False):
    def respond(request):
        path = request.url.path
        assert request.method == "GET" or (request.method == "POST" and path == "/api/analyze")
        if path == "/health": return httpx.Response(200, json={"storage_mode": storage})
        if path in {"/", "/tenant"}:
            return httpx.Response(200) if allow_tenant_portal else httpx.Response(303, headers={"location": "/tenant/login"})
        if path == "/api/apartments/config": return httpx.Response(200 if allow_tenant_config else 401)
        if path == "/api/tenant/session": return httpx.Response(401)
        if path == "/api/apartments/manage/concerns": return httpx.Response(200 if allow_manager else 401)
        if path.startswith("/api/apartments/concerns/"): return httpx.Response(401)
        if path in {"/api/tickets", "/metrics"}: return httpx.Response(401)
        if path == "/api/analyze": return httpx.Response(200, json={"answer_mode": "retrieval", "sources": [{"id": "KB-007"}]})
        return httpx.Response(200, text="Public asset")
    return httpx.MockTransport(respond)


def test_public_smoke_is_read_only_and_includes_apartments():
    with httpx.Client(base_url="https://example.test", transport=transport()) as client:
        assert check_endpoint(client)["tracking_without_key"] == "denied"


def test_smoke_rejects_accidentally_public_manager_queue():
    with httpx.Client(base_url="https://example.test", transport=transport(True)) as client:
        with pytest.raises(AssertionError): check_endpoint(client)


def test_cloud_smoke_checks_the_selected_durable_backend():
    with httpx.Client(base_url="https://example.test", transport=transport(storage="firestore")) as client:
        assert check_endpoint(client, expected_storage="firestore")["health"] == "ok"
        with pytest.raises(AssertionError, match="storage backend"):
            check_endpoint(client, expected_storage="dynamodb")


def test_smoke_rejects_anonymous_tenant_configuration():
    with httpx.Client(base_url="https://example.test", transport=transport(allow_tenant_config=True)) as client:
        with pytest.raises(AssertionError, match="configuration"):
            check_endpoint(client)


def test_smoke_rejects_unguarded_tenant_page():
    with httpx.Client(base_url="https://example.test", transport=transport(allow_tenant_portal=True)) as client:
        with pytest.raises(AssertionError, match="Tenant page"):
            check_endpoint(client)
