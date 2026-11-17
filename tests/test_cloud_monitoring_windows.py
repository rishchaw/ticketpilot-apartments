"""Rate windows must retain multiple observations at a five-minute cloud scrape."""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name,uid,panels", [("ticketpilot.json", "ticketpilot-aws", 10), ("apartments.json", "ticketpilot-apartments", 6)])
def test_provisioned_dashboard_rate_windows_support_300_second_scrapes(name, uid, panels):
    dashboard = json.loads((ROOT / "monitoring/grafana/dashboards" / name).read_text(encoding="utf-8"))
    assert dashboard["uid"] == uid and len(dashboard["panels"]) == panels
    rate_queries = [target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])
                    if "rate(" in target.get("expr", "")]
    assert rate_queries
    assert all("[15m]" in query and "[5m]" not in query for query in rate_queries)


def test_server_error_alert_rate_window_supports_300_second_scrapes():
    import yaml
    document = yaml.safe_load((ROOT / "monitoring/prometheus/alerts.yml").read_text(encoding="utf-8"))
    rules = [rule for group in document["groups"] for rule in group["rules"]]
    alert = next(rule for rule in rules if rule["alert"] == "TicketPilotServerErrors")
    assert alert["expr"].count("[15m]") == 2 and "[5m]" not in alert["expr"]
    assert alert["for"] == "5m"
