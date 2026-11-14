"""ASGI adapter for Lambda Function URL HTTP API v2 events."""
from mangum import Mangum
from ticketpilot.aws_secrets import load_secrets

load_secrets()

from ticketpilot.api import app  # noqa: E402

handler = Mangum(app, lifespan="off")
