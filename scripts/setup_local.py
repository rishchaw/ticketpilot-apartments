"""Generate local credentials once, without putting values in console output."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
env = ROOT / ".env"
secret_dir = ROOT / ".secrets"
secret_dir.mkdir(exist_ok=True)
if not env.exists():
    values = {
        "ADMIN_TOKEN": secrets.token_hex(24),
        "METRICS_TOKEN": secrets.token_hex(24),
        "GRAFANA_ADMIN_PASSWORD": secrets.token_hex(24),
        "LLM_PROVIDER": "none",
        "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0",
        "BEDROCK_REGION": "ap-southeast-2",
        "LLM_MAX_CALLS_PER_MINUTE": "3",
    }
    env.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
else:
    values = dict(line.split("=", 1) for line in env.read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
if not values.get("METRICS_TOKEN"):
    raise SystemExit("Set METRICS_TOKEN in .env first")
(secret_dir / "metrics-token").write_text(values["METRICS_TOKEN"], encoding="utf-8")
print("Local credentials ready in .env; do not commit this file.")
