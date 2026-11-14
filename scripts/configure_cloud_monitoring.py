"""Optional diagnostic scrape of a Lambda URL; metrics are process-local."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("url", help="Lambda Function URL")
args = parser.parse_args()
url = urlparse(args.url)
if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in (None, 443) or url.path not in ("", "/") or url.query or url.fragment:
    parser.error("Provide an HTTPS base URL without path, credentials or query")
root = Path(__file__).resolve().parents[1]
config = {
    "global": {"scrape_interval": "60s", "scrape_timeout": "25s"},
    "rule_files": ["/etc/prometheus/alerts.yml"],
    "scrape_configs": [{
        "job_name": "ticketpilot", "scheme": "https", "metrics_path": "/metrics",
        "authorization": {"type": "Bearer", "credentials_file": "/run/secrets/metrics-token"},
        "static_configs": [{"targets": [url.hostname + ":443"]}],
    }],
}
# JSON is also valid YAML; avoid adding a dependency to this setup script.
(root / "monitoring/prometheus/cloud.yml").write_text(json.dumps(config, indent=2), encoding="utf-8")
print("Created monitoring/prometheus/cloud.yml. Set PROMETHEUS_CONFIG=./monitoring/prometheus/cloud.yml before docker compose up -d.")
