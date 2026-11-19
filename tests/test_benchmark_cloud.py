import httpx
from scripts.benchmark_cloud import request_sample, summarize, benchmark


def test_summary_keeps_errors_and_uses_nearest_rank():
    samples = [{"ms": i, "status": 200, "valid": True} for i in range(1, 21)]
    samples.append({"ms": 1000, "status": 503, "valid": False})
    result = summarize(samples)
    assert result["p50_ms"] == 10.5
    assert result["p95_ms"] == 19
    assert result["failures"] == 1
    assert result["http_statuses"] == {"200": 20, "503": 1}
    assert summarize([samples[-1]])["p95_ms"] is None


def test_sample_rejects_wrong_retrieval_and_records_transport_failure():
    def handler(request):
        if request.url.path == "/api/analyze":
            return httpx.Response(200, json={"answer_mode": "generated", "sources": ["KB-1"]})
        raise httpx.ConnectError("fixture network failure", request=request)

    with httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler)) as client:
        assert not request_sample(client, "POST", "/api/analyze", {"text": "fixture"})["valid"]
        failed = request_sample(client, "GET", "/health", None)
        assert failed["status"] is None
        assert failed["error_type"] == "ConnectError"
        assert not failed["valid"]


def test_benchmark_only_uses_public_read_only_routes(monkeypatch):
    requests = []
    monkeypatch.setattr("scripts.benchmark_cloud.time.sleep", lambda _: None)

    def handler(request):
        requests.append((request.method, request.url.path))
        value = {"answer_mode": "retrieval", "sources": ["KB-1"]}
        return httpx.Response(200, json=value)

    with httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler)) as client:
        result = benchmark(client, samples=5, interval=0.25)
    assert len(requests) == 27
    assert set(requests) == {("GET", "/health"), ("GET", "/tenant/login"), ("POST", "/api/analyze")}
    assert all(item["measured"]["successes"] == 5 for item in result.values())
