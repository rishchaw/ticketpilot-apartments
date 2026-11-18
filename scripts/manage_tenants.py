"""Select the verified cloud backend for explicit private account administration.

No password is passed as a command argument or printed. Routine cloud updates
never run this script or reset tenant credentials.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import cloud, deploy_aws
from scripts.tenant_settings import units_csv


class AccountOperationError(Exception): pass


def runtime_values(service):
    containers = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if len(containers) != 1: raise AccountOperationError("Expected the existing single-container Cloud Run application")
    return containers[0], {item.get("name"): item.get("value") for item in containers[0].get("env", []) if isinstance(item, dict)}


def selected_environment(args, context, runner):
    if type(context.get("tenant_auth_release")) is not int or context["tenant_auth_release"] != 1:
        raise AccountOperationError("Prepare the validated tenant-login deployment before administering accounts")
    if args.provider == "aws":
        identity = runner.aws(args, "sts", "get-caller-identity")
        if not context.get("account_id") or identity.get("Account") != context["account_id"]:
            raise AccountOperationError("The AWS profile differs from this deployment's recorded account")
        function = runner.aws(args, "lambda", "get-function", "--function-name", deploy_aws.FUNCTION)
        if function.get("Code", {}).get("ResolvedImageUri") != context.get("image_uri"):
            raise AccountOperationError("The live AWS image differs from the validated deployment")
        values = function.get("Configuration", {}).get("Environment", {}).get("Variables", {})
        table = values.get("DYNAMODB_TABLE")
        if values.get("STORAGE_MODE") != "dynamodb" or table != "ticketpilot-aws-tickets":
            raise AccountOperationError("The selected Lambda does not use the expected protected table")
        metadata = runner.aws(args, "dynamodb", "describe-table", "--table-name", table)["Table"]
        expected = "arn:aws:dynamodb:ap-southeast-1:" + identity["Account"] + ":table/" + table
        if metadata.get("TableArn") != expected:
            raise AccountOperationError("The account, region and DynamoDB table do not match")
        env = deploy_aws.scoped_environment(os.environ, args.profile)
        env.update(STORAGE_MODE="dynamodb", DYNAMODB_TABLE=table)
    else:
        if args.project and args.project != context.get("project"):
            raise AccountOperationError("The selected GCP project differs from the deployment record")
        if os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
            raise AccountOperationError("Cloud administration requires browser ADC without emulator or credential-file overrides")
        service = runner.gcp(context)
        container, values = runtime_values(service)
        if service.get("metadata", {}).get("name") != "ticketpilot-apartments" or container.get("image") != context.get("image"):
            raise AccountOperationError("The live GCP application differs from the validated deployment")
        if values.get("STORAGE_MODE") != "firestore" or values.get("GOOGLE_CLOUD_PROJECT") != context.get("project"):
            raise AccountOperationError("The Cloud Run project and Firestore configuration do not match")
        env = os.environ.copy()
        env.update(STORAGE_MODE="firestore", GOOGLE_CLOUD_PROJECT=context["project"], GOOGLE_CLOUD_QUOTA_PROJECT=context["project"],
                   FIRESTORE_DATABASE=values.get("FIRESTORE_DATABASE") or "(default)")
    units = units_csv(values.get("APARTMENT_UNITS"))
    if args.units is not None and units_csv(args.units) != units:
        raise AccountOperationError("The requested units differ from the deployed apartment configuration")
    return env, units


class PrivateArguments(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Invalid tenant administration arguments; use --help.\n")


def main(argv=None):
    parser = PrivateArguments(description=__doc__)
    parser.add_argument("provider", choices=("aws", "gcp"))
    parser.add_argument("action", choices=("provision", "reset", "disable", "enable"))
    parser.add_argument("--profile", default="ticketpilot")
    parser.add_argument("--project")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--units", help="Optional eight-unit check against the deployed configuration")
    parser.add_argument("--username")
    args = parser.parse_args(argv)
    if args.action != "provision" and not args.username: parser.error("Select the account username explicitly")
    try:
        context = cloud.context_for(ROOT, args.provider, required=True)
        runner = cloud.Runner(ROOT)
        env, units = selected_environment(args, context, runner)
        path = args.credentials_file or ROOT / ".secrets" / ("tenant-credentials.json" if args.provider == "aws" else "gcp-tenant-credentials.json")
        command = [sys.executable, "-m", "ticketpilot.tenant_accounts", args.action, "--credentials-file", str(path)]
        command += ["--units", units] if args.action == "provision" else ["--username", args.username]
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        return result.returncode
    except (AccountOperationError, cloud.CloudError, ValueError, KeyError) as error:
        print("Tenant administration stopped: " + str(error), file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError) as error:
        print("Tenant administration stopped: " + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__": sys.exit(main())
