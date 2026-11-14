"""Load SecureString parameters once per Lambda execution environment."""
import os


def load_secrets():
    mapping = {key: os.environ[key + "_PARAMETER"] for key in ("ADMIN_TOKEN", "METRICS_TOKEN") if os.getenv(key + "_PARAMETER")}
    if not mapping:
        return
    import boto3
    response = boto3.client("ssm").get_parameters(Names=list(mapping.values()), WithDecryption=True)
    parameters = {entry["Name"]: entry["Value"] for entry in response["Parameters"]}
    if response.get("InvalidParameters") or any(name not in parameters for name in mapping.values()):
        raise RuntimeError("Required AWS runtime parameters are missing")
    for key, name in mapping.items():
        os.environ[key] = parameters[name]
