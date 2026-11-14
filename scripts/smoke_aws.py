"""Read-only apartment/legacy endpoint checks; no owner writes or paid generation."""
import argparse
import json
from urllib.parse import urlparse
import httpx


def check_endpoint(client):
    health = client.get("/health")
    health.raise_for_status()
    assert health.json()["storage_mode"] == "dynamodb", "Expected deployed DynamoDB storage"
    for path in ("/", "/tenant", "/manager", "/assets/apartments.js", "/assets/apartments.css"):
        client.get(path).raise_for_status()
    config = client.get("/api/apartments/config")
    config.raise_for_status()
    settings = config.json()
    assert settings["intake_available"] is True, "Apartment intake is not enabled"
    assert settings["units"] and {c["id"] for c in settings["categories"]} >= {"water", "maintenance", "electrical", "billing", "renewal", "other"}
    assert client.get("/api/apartments/manage/concerns").status_code == 401
    assert client.get("/api/apartments/concerns/apt_" + "0" * 32).status_code == 404
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/metrics").status_code == 401
    result = client.post("/api/analyze", json={"title": "Production API outage", "text": "Production API down with HTTP 503 errors for every customer."})
    result.raise_for_status()
    assert result.json()["answer_mode"] == "retrieval" and result.json()["sources"]
    return {"health": "ok", "apartment_pages": "ok", "apartment_intake_configuration": "enabled", "anonymous_manager_access": "denied", "tracking_without_key": "denied", "legacy_retrieval": "ok", "scope": "Public/read-only checks; manager acceptance and persistence require a separate authorized workflow"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    args = parser.parse_args(argv)
    url = urlparse(args.url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        parser.error("Provide the HTTPS service base URL")
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=45, follow_redirects=False) as client:
        print(json.dumps(check_endpoint(client), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
