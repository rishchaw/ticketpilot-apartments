import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("cloudwatch_exporter", Path(__file__).resolve().parents[1] / "monitoring/cloudwatch_exporter.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_cloudwatch_poll_uses_bounded_delayed_window_and_converts_milliseconds():
    client = Mock()
    client.get_metric_data.return_value = {"MetricDataResults": [{"Id": key, "StatusCode": "Complete", "Values": [150] if key == "duration" else []} for key in exporter.SPECS]}
    gauges = {key: Mock() for key in exporter.SPECS}
    exporter.poll(client, "ticketpilot-aws", gauges, datetime(2026, 11, 9, 12, 13, tzinfo=timezone.utc))
    request = client.get_metric_data.call_args.kwargs
    assert request["StartTime"].minute == 0
    assert request["EndTime"].minute == 5
    assert len(request["MetricDataQueries"]) == 4
    gauges["duration"].set.assert_called_once_with(0.15)
    gauges["invocations"].set.assert_called_once_with(0)


def test_cloudwatch_partial_result_is_not_reported_as_zero():
    client = Mock()
    client.get_metric_data.return_value = {"MetricDataResults": []}
    with pytest.raises(RuntimeError):
        exporter.poll(client, "ticketpilot-aws", {key: Mock() for key in exporter.SPECS})
