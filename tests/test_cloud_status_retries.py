import httpx
import pytest
from scripts import cloud


@pytest.mark.parametrize("failures", [1, 3])
def test_status_retries_transport_errors_and_preserves_offline_guard(monkeypatch, failures):
    calls = []
    client_class = httpx.Client
    monkeypatch.setattr(cloud.time, "sleep", lambda _: None)

    def handler(request):
        calls.append(request)
        if len(calls) <= failures:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_class(
        **kwargs, transport=httpx.MockTransport(handler)))
    url = "https://fixture.run.app"
    if failures == 3:
        with pytest.raises(cloud.CloudError, match="after three attempts"):
            cloud.public_observations("gcp", {url}, offline=True)
    else:
        assert cloud.public_observations("gcp", {url}, offline=True) == [
            {"url": url, "health_http_status": 503}]
    assert len(calls) == min(failures + 1, 3)
