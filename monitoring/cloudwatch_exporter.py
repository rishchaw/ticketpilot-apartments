"""Export delayed CloudWatch Lambda metrics; no keep-alive calls to the app."""
import logging
import os
from datetime import datetime, timedelta, timezone
from time import sleep

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from prometheus_client import Gauge, start_http_server

UP = Gauge("ticketpilot_cloudwatch_exporter_up", "Most recent CloudWatch poll succeeded")
LAST = Gauge("ticketpilot_cloudwatch_last_success_timestamp_seconds", "Last successful CloudWatch poll")
SPECS = {
    "invocations": ("Invocations", "Sum", "ticketpilot_lambda_invocations_window", "Invocations in the last complete five-minute CloudWatch period"),
    "errors": ("Errors", "Sum", "ticketpilot_lambda_errors_window", "Errors in the last complete five-minute CloudWatch period"),
    "throttles": ("Throttles", "Sum", "ticketpilot_lambda_throttles_window", "Throttles in the last complete five-minute CloudWatch period"),
    "duration": ("Duration", "Average", "ticketpilot_lambda_duration_seconds", "Mean duration in the last complete five-minute period"),
}


def queries(function_name):
    return [{
        "Id": key,
        "MetricStat": {
            "Metric": {"Namespace": "AWS/Lambda", "MetricName": spec[0], "Dimensions": [{"Name": "FunctionName", "Value": function_name}]},
            "Period": 300, "Stat": spec[1],
        }, "ReturnData": True,
    } for key, spec in SPECS.items()]


def poll(client, function_name, gauges, now=None):
    now = now or datetime.now(timezone.utc)
    # Query one fixed complete period with a five-minute ingestion delay.
    end = datetime.fromtimestamp((int(now.timestamp()) // 300 - 1) * 300, timezone.utc)
    response = client.get_metric_data(MetricDataQueries=queries(function_name), StartTime=end - timedelta(minutes=5), EndTime=end)
    rows = {row["Id"]: row for row in response["MetricDataResults"]}
    if any(key not in rows or rows[key].get("StatusCode") != "Complete" for key in SPECS):
        raise RuntimeError("Incomplete CloudWatch metric response")
    for key in SPECS:
        values = rows[key].get("Values", [])
        value = float(values[0]) if values else 0.0
        gauges[key].set(value / 1000 if key == "duration" else value)


def main():
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "ticketpilot-aws")
    client = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "ap-southeast-1"), config=Config(connect_timeout=3, read_timeout=15, retries={"total_max_attempts": 2}))
    gauges = {key: Gauge(spec[2], spec[3]) for key, spec in SPECS.items()}
    interval = max(300, int(os.getenv("CLOUDWATCH_POLL_SECONDS", "300")))
    start_http_server(9101)
    while True:
        try:
            poll(client, function_name, gauges)
            UP.set(1)
            LAST.set(datetime.now(timezone.utc).timestamp())
        except (BotoCoreError, ClientError, RuntimeError, ValueError, KeyError):
            UP.set(0)
            logging.warning("CloudWatch poll failed; check AWS login and cloudwatch:GetMetricData permission")
        sleep(interval)


if __name__ == "__main__":
    main()
