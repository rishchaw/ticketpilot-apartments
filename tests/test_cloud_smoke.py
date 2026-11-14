"""The public smoke check must exercise apartments without creating tenant records."""
import httpx
import pytest
from scripts.smoke_aws import check_endpoint


def transport(allow_manager=False):
    def respond(request):
        path = request.url.path
        assert request.method == "GET" or (request.method == "POST" and path == "/api/analyze")
        if path == "/health": return httpx.Response(200, json={"storage_mode": "dynamodb"})
        if path == "/api/apartments/config": return httpx.Response(200, json={"intake_available": True, "units": ["1"], "categories": [{"id": x} for x in ("water", "maintenance", "electrical", "billing", "renewal", "other")]})
        if path == "/api/apartments/manage/concerns": return httpx.Response(200 if allow_manager else 401)
        if path.startswith("/api/apartments/concerns/"): return httpx.Response(404)
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
