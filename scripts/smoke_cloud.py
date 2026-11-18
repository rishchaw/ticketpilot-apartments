"""Read-only apartment/legacy endpoint checks; no owner writes or paid generation."""
import argparse
import json
from urllib.parse import urlparse
import httpx


def check_endpoint(client, expected_storage="dynamodb"):
    health = client.get("/health")
    health.raise_for_status()
    assert health.json()["storage_mode"] == expected_storage, "Unexpected deployed storage backend"
    for path in ("/", "/tenant"):
        response = client.get(path, headers={"Cookie": ""})
        assert response.status_code in {302, 303, 307, 308}, "Tenant page must require login"
        assert response.headers.get("location") == "/tenant/login", "Unexpected tenant login redirect"
    for path in ("/tenant/login", "/manager", "/assets/apartments.js", "/assets/apartments.css", "/assets/tenant-login.js"):
        client.get(path).raise_for_status()
    assert client.get("/api/tenant/session", headers={"Cookie": ""}).status_code == 401
    assert client.get("/api/apartments/config", headers={"Cookie": ""}).status_code == 401, "Tenant configuration must require login"
    assert client.get("/api/apartments/manage/concerns", headers={"Cookie": ""}).status_code == 401
    assert client.get("/api/apartments/concerns/apt_" + "0" * 32, headers={"Cookie": ""}).status_code == 401
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/metrics").status_code == 401
    result = client.post("/api/analyze", json={"title": "Production API outage", "text": "Production API down with HTTP 503 errors for every customer."})
    result.raise_for_status()
    assert result.json()["answer_mode"] == "retrieval" and result.json()["sources"]
    return {"health": "ok", "apartment_pages": "ok", "apartment_intake_configuration": "requires authenticated tenant or manager", "anonymous_manager_access": "denied", "tracking_without_key": "denied", "legacy_retrieval": "ok", "scope": "Anonymous/read-only checks; private tenant/manager acceptance and persistence require a separate authorized workflow"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--expected-storage", choices=["dynamodb", "firestore"], default="dynamodb")
    args = parser.parse_args(argv)
    url = urlparse(args.url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        parser.error("Provide the HTTPS service base URL")
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=45, follow_redirects=False) as client:
        print(json.dumps(check_endpoint(client, args.expected_storage), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
