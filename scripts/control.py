"""TicketPilot operator controls: resume, pause, monitoring and native consoles.

Launch without arguments for a menu. Opening the menu contacts no cloud and
starts no services. Start resumes existing infrastructure; Update/Prepare are
separate explicit deployment actions. --check inspects local prerequisites only.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
AWS_PROFILE = "ticketpilot"
GCP_CONFIG = "ticketpilot-gcp"
APARTMENT_UNITS = "1A,1B,2A,2B,2C,3A,3B,3C"
OTHER_AUTH_FAILURE = "Cannot authenticate the other provider's pause state"
LOCAL_URLS = {"grafana": "http://127.0.0.1:3000", "prometheus": "http://127.0.0.1:9090",
              "k8s-app": "http://127.0.0.1:18080", "k8s-prometheus": "http://127.0.0.1:19090", "k8s-grafana": "http://127.0.0.1:13000"}
AWS_URLS = {
    "aws-console": "https://ap-southeast-1.console.aws.amazon.com/console/home?region=ap-southeast-1",
    "aws-lambda": "https://ap-southeast-1.console.aws.amazon.com/lambda/home?region=ap-southeast-1#/functions/ticketpilot-aws?tab=monitoring",
    "aws-cloudwatch": "https://ap-southeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-southeast-1",
    "aws-ecr": "https://ap-southeast-1.console.aws.amazon.com/ecr/repositories?region=ap-southeast-1",
    "aws-dynamodb": "https://ap-southeast-1.console.aws.amazon.com/dynamodbv2/home?region=ap-southeast-1#tables",
    "aws-ssm": "https://ap-southeast-1.console.aws.amazon.com/systems-manager/parameters/?region=ap-southeast-1",
    "aws-billing": "https://console.aws.amazon.com/billing/home",
    "aws-credits": "https://console.aws.amazon.com/billing/home#/credits",
    "aws-budgets": "https://console.aws.amazon.com/cost-management/",
}
GCP_PATHS = {"gcp-console": "/home/dashboard", "gcp-cloud-run": "/run/detail/asia-southeast1/ticketpilot-apartments/metrics",
             "gcp-firestore": "/firestore", "gcp-artifact-registry": "/artifacts", "gcp-logs": "/logs/query", "gcp-billing": "/billing"}
CLOUD_ACTIONS = ("start", "stop", "status", "monitor-start", "monitor-stop", "login", "portal", "update")
LOCAL_ACTIONS = ("docker-open", "docker-status", "stop-local", "k8s-start", "k8s-status", "k8s-stop", "k8s-forward-app", "k8s-forward-prometheus", "k8s-forward-grafana")


class ControlError(Exception):
    """A safe, actionable operator message."""


def project_python(root):
    paths = [root / ".venv/Scripts/python.exe", root / ".venv/bin/python"] if os.name == "nt" else [root / ".venv/bin/python", root / ".venv/Scripts/python.exe"]
    for path in paths:
        if path.is_file():return str(path)
    raise ControlError("Project Python environment is missing. Follow the fresh-clone setup in docs/STACK_GUIDE.md.")


def gcloud_path(root):
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    pointer = root / ".tools/gcloud-path.txt"
    if not found and pointer.is_file():found = pointer.read_text(encoding="utf-8-sig").strip()
    if not found or not Path(found).is_file():
        raise ControlError("Google Cloud CLI is missing. Follow docs/GCP_DEPLOYMENT.md before signing in.")
    return str(found)


def desktop_command():
    if os.name == "nt":
        candidates = []
        if os.getenv("LOCALAPPDATA"):
            base = Path(os.environ["LOCALAPPDATA"])
            candidates += [base / "Programs/DockerDesktop/Docker Desktop.exe", base / "Programs/Docker/Docker/Docker Desktop.exe"]
        if os.getenv("PROGRAMFILES"):
            candidates.append(Path(os.environ["PROGRAMFILES"]) / "Docker/Docker/Docker Desktop.exe")
        docker = shutil.which("docker")
        if docker:candidates.append(Path(docker).parent.parent.parent / "Docker Desktop.exe")
        for path in candidates:
            if path.is_file():return [str(path)]
    elif sys.platform == "darwin":return ["open", "-a", "Docker"]
    elif shutil.which("docker-desktop"):return [shutil.which("docker-desktop")]
    raise ControlError("Docker Desktop was not found. Open your installed Docker controls to start the Linux engine.")


class Controller:
    def __init__(self, root=ROOT, *, runner=None, opener=None, starter=None, input_fn=None, output=None):
        self.root = Path(root).resolve()
        self.runner = runner or subprocess.run
        self.opener = opener or webbrowser.open
        self.starter = starter or subprocess.Popen
        self.input = input_fn or input
        self.print = output or print

    def helper(self, name, *arguments):
        script = self.root / "scripts" / name
        if not script.is_file():raise ControlError("Required project helper is missing. Update the project source before retrying.")
        return [project_python(self.root), str(script), *map(str, arguments)]

    def run(self, command, *, stream=False, env=None, forwarding=False):
        try:
            result = self.runner(command, cwd=self.root, env=env, capture_output=not stream,
                                 text=True, encoding="utf-8", errors="replace", check=False)
        except KeyboardInterrupt:
            if forwarding:
                self.print("Port forwarding stopped. Returning to the controls.")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            raise ControlError("Action interrupted. Check the provider status before retrying.") from None
        except (OSError, subprocess.SubprocessError):
            raise ControlError("The selected tool could not run. Check --check and the setup guide.") from None
        if not stream:
            for value in (getattr(result, "stdout", ""), getattr(result, "stderr", "")):
                if value:self.print(value.rstrip())
        return result

    def record(self, provider):
        found = []
        for name in (provider + "-deployment.json", provider + "-service-state.json"):
            path = self.root / ".tools" / name
            if not path.exists():continue
            if path.is_symlink():raise ControlError("Restore the original private deployment record; symlinked records are not accepted.")
            try:
                if path.stat().st_size > 65536:raise ValueError
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(value, dict):raise ValueError
                expected_region = "ap-southeast-1" if provider == "aws" else "asia-southeast1"
                if value.get("region",expected_region) != expected_region:raise ValueError
                if "project_id" in value:
                    if value.get("project",value["project_id"]) != value["project_id"]:raise ValueError
                    value["project"] = value["project_id"]
            except (OSError, ValueError):
                raise ControlError("The private deployment record is unreadable. Restore it before controlling this provider.") from None
            found.append((path.stat().st_mtime_ns, value))
        if not found:raise ControlError("No local deployment record was found. Follow the provider deployment guide before using Start.")
        result = {}
        for _, value in sorted(found, key=lambda item:item[0]):
            for key in ("project", "account_id"):
                if key in result and key in value and result[key] != value[key]:
                    raise ControlError("Private deployment records disagree. Review them before controlling this provider.")
            result.update(value)
        return result

    def project(self):
        value = self.record("gcp")
        project = value.get("project", value.get("project_id"))
        if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
            raise ControlError("The private GCP record has no valid project ID. Restore the correct project record.")
        return project

    def open(self, target):
        if target in LOCAL_URLS:url = LOCAL_URLS[target]
        elif target in AWS_URLS:url = AWS_URLS[target]
        elif target in GCP_PATHS:
            url = "https://console.cloud.google.com" + GCP_PATHS[target] + "?" + urlencode({"project":self.project()})
        else:raise ControlError("Choose one of the listed dashboards.")
        self.opener(url)
        return 0

    def portal(self, provider):
        value = self.record(provider).get("url")
        try:
            parsed = urlsplit(value) if isinstance(value,str) else None
            suffix = r"[a-z0-9]+\.lambda-url\.ap-southeast-1\.on\.aws" if provider == "aws" else r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app"
            valid = parsed and parsed.scheme == "https" and re.fullmatch(suffix,parsed.hostname or "") and not parsed.username and not parsed.password and not parsed.port and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
        except ValueError:
            valid = False
        if not valid:
            raise ControlError("The saved service URL is invalid. Check provider Status before opening the portal.")
        self.opener(value.rstrip("/") + "/tenant")
        return 0

    def cloud(self, provider, action, *, attest=False, interactive=False):
        stage = {"start":"resume", "stop":"pause", "update":"deploy"}.get(action, action)
        arguments = [provider, stage]
        if provider == "aws":arguments += ["--profile", AWS_PROFILE]
        command = self.helper("cloud.py", *arguments)
        self.print({"start":"Starting the existing portal; the image is not rebuilt.", "stop":"Pausing the portal and stopping local cloud scrapes; data remains stored.", "update":"Updating the image and Terraform configuration while preserving the saved pause state."}.get(action, "Running the selected provider action."))
        result = self.run(command)
        output = (getattr(result,"stdout","") or "") + (getattr(result,"stderr","") or "")
        if result.returncode and action in {"start", "update"} and OTHER_AUTH_FAILURE in output:
            allowed = attest
            if interactive and not allowed:
                self.print("The other provider's login could not be checked. Only confirm if you independently know it is paused. The native guard will still require a saved pause and fresh unavailable URLs.")
                allowed = self.input("Type PAUSED to confirm, or press Enter to cancel: ").strip() == "PAUSED"
            if allowed:result = self.run([*command, "--confirm-other-offline"])
        if result.returncode and provider == "gcp" and action == "start":
            self.print("First GCP start needs the tenant-login image and eight accounts. Use GCP Prepare if that upgrade is outstanding; renew GCP sign-in when requested. Start never performs that upgrade.")
        return result.returncode

    def login(self, provider):
        if provider == "aws":
            executable = shutil.which("aws")
            if not executable:raise ControlError("Install AWS CLI v2 before signing in.")
            version = self.run([executable,"--version"])
            match = re.search(r"aws-cli/(\d+)\.(\d+)\.(\d+)", getattr(version,"stdout","") or "")
            if version.returncode or not match or tuple(map(int,match.groups())) < (2,32,0):
                raise ControlError("AWS CLI 2.32.0 or later is required for browser login. Follow docs/AWS_DEPLOYMENT.md.")
            self.print("Your selected Sign In action opens the AWS browser login for profile ticketpilot.")
            result = self.run([executable,"login","--profile",AWS_PROFILE],stream=True)
            return result.returncode if result.returncode else self.cloud("aws","status")
        project = self.project()
        executable = gcloud_path(self.root)
        env = os.environ.copy()
        env.update(CLOUDSDK_PYTHON=project_python(self.root), CLOUDSDK_ACTIVE_CONFIG_NAME=GCP_CONFIG,
                   CLOUDSDK_CORE_DISABLE_USAGE_REPORTING="true", CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK="true")
        self.print("Finish both selected Google browser sign-ins: CLI access, then application default credentials. This does not start GCP.")
        for arguments in (["auth","login"], ["auth","application-default","login"], ["auth","application-default","set-quota-project",project]):
            result = self.run([executable,"--configuration="+GCP_CONFIG,*arguments],stream=True,env=env)
            if result.returncode:return result.returncode
        return 0

    def prepare_gcp(self, *, attest=False, interactive=False):
        if self.record("gcp").get("paused") is not True:
            raise ControlError("Stop the existing GCP service first. Prepare upgrades its image and accounts while preserving the stopped state.")
        self.print("Preparing the GCP tenant-login deployment while keeping it stopped. Docker and renewed Google CLI/ADC access are required.")
        command = self.helper("cloud.py","gcp","deploy","--leave-paused","--apartment-units",APARTMENT_UNITS)
        result = self.run(command)
        output = (getattr(result,"stdout","") or "")+(getattr(result,"stderr","") or "")
        if result.returncode and OTHER_AUTH_FAILURE in output:
            allowed = attest
            if interactive and not allowed:
                self.print("The other provider's login could not be checked. The native pause/HTTP guard still applies.")
                allowed = self.input("Type PAUSED only if you independently know the other provider is paused: ").strip() == "PAUSED"
            if allowed:result = self.run([*command,"--confirm-other-offline"])
        if result.returncode:return result.returncode
        result = self.run(self.helper("manage_tenants.py","gcp","provision"))
        if not result.returncode:self.print("GCP prepared and still stopped. Tenant logins are private in .secrets/gcp-tenant-credentials.json. Use Start only when you want it available.")
        return result.returncode

    def local(self, action):
        if action == "docker-status":
            executable = shutil.which("docker")
            if not executable: raise ControlError("Docker CLI is missing; open Docker Desktop and check its installation")
            return self.run([executable, "ps", "-a", "--filter", "label=com.docker.compose.project=ticketpilot-aws", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"], stream=True).returncode
        if action == "stop-local":
            self.print("Stopping local TicketPilot containers and the owned disposable kind demo; cloud state is unchanged.")
            return self.run(self.helper("stop_services.py", "--local-only"), stream=True).returncode
        if action == "docker-open":
            self.starter(desktop_command(),cwd=self.root)
            self.print("Docker Desktop opened. Wait for its Linux engine before builds or local monitoring.")
            return 0
        if action.startswith("k8s-forward-"):
            service = action.removeprefix("k8s-forward-")
            self.print("Forwarding " + service + ". Keep this console open; Ctrl+C returns to the controls.")
            return self.run(self.helper("kubernetes_local.py","forward",service),stream=True,forwarding=True).returncode
        stage = {"k8s-start":"start","k8s-status":"status","k8s-stop":"stop"}.get(action)
        if not stage:raise ControlError("Choose one of the listed local tools.")
        if stage == "stop":self.print("Stopping only the owned Kubernetes demo; its fictional PVC data is disposable.")
        result = self.run(self.helper("kubernetes_local.py",stage),stream=True)
        if result.returncode or stage != "start": return result.returncode
        self.print("Preparing and validating eight fictional demo accounts; no real cloud credentials are used.")
        result = self.run(self.helper("validate_kubernetes_local.py"),stream=True)
        if not result.returncode:self.print("Fictional tenant logins are private in .tools/kubernetes/tenant-accounts.json. Use a Forward action to open the app or dashboards.")
        return result.returncode

    def check(self):
        try:python = bool(project_python(self.root))
        except ControlError:python = False
        try:google = bool(gcloud_path(self.root))
        except ControlError:google = False
        return {"project_python":python,"cloud_controls":(self.root/"scripts/cloud.py").is_file(),
                "tenant_operator":(self.root/"scripts/manage_tenants.py").is_file(),
                "kubernetes_helper":(self.root/"scripts/kubernetes_local.py").is_file(),
                "aws_cli":bool(shutil.which("aws")),"gcloud_cli":google,"docker_cli":bool(shutil.which("docker")),
                "terraform":bool(shutil.which("terraform") or (self.root/".tools/terraform.exe").is_file() or (self.root/".tools/terraform").is_file()),
                "cloud_contacted":False,"docker_engine_contacted":False}

    def explain(self):
        self.print("Terraform creates and changes infrastructure; there is no Terraform server to keep running. Start/Stop apply reviewed scaling changes to the existing deployment. Update rebuilds/tests an image and applies infrastructure changes explicitly.")
        self.print("Docker builds images and runs optional local containers. Kubernetes is a separate local kind demo with fictional data. Prometheus scrapes the selected app; Grafana displays those local metrics. Native cloud consoles show service-wide metrics and retained resources.")
        self.print("Pausing retains databases, images and secrets, so storage charges can remain. Budget alerts are not spending caps. Cost links open provider consoles; this tool makes no Cost Explorer API queries.")
        self.print("See docs/OPERATIONS_QUICKSTART.md and docs/STACK_GUIDE.md. Closing these controls leaves service state unchanged.")
        return 0

    def perform(self, group, action=None, *, attest=False, interactive=False):
        if attest and (group not in {"aws","gcp"} or action not in {"start","update","prepare"}):
            raise ControlError("Offline attestation is available only for Start, Update or GCP Prepare.")
        if group in {"aws","gcp"}:
            if action == "login":return self.login(group)
            if action == "portal":return self.portal(group)
            if action == "prepare":return self.prepare_gcp(attest=attest,interactive=interactive)
            return self.cloud(group,action,attest=attest,interactive=interactive)
        if group == "local":return self.local(action)
        if group == "open":return self.open(action)
        if group == "stop-all":return self.run(self.helper("stop_services.py","--profile",AWS_PROFILE),stream=True).returncode
        if group == "guide":return self.explain()
        raise ControlError("Choose one of the listed control actions.")

    def choose(self,title,entries,*,exit_label="Back"):
        self.print("\n"+title)
        for index,(_,label) in enumerate(entries,1):self.print(str(index)+". "+label)
        self.print("0. "+exit_label)
        try:value=self.input("Choose a number: ").strip()
        except (EOFError,KeyboardInterrupt):return None
        if value == "0":return None
        if value.isdigit() and 1 <= int(value) <= len(entries):return entries[int(value)-1][0]
        self.print("Choose one of the displayed numbers.")
        return "invalid"

    def menu_action(self,group,action=None):
        try:
            result=self.perform(group,action,interactive=True)
            if result:self.print("Action did not complete. Check its message and provider Status before retrying.")
        except ControlError as error:self.print(str(error))

    def menu(self):
        self.print("TicketPilot controls - AWS Singapore / GCP Singapore")
        self.print("Opening this menu starts no services. Start resumes; Update is separate. Exit leaves service state unchanged.")
        while True:
            choice=self.choose("Main menu",[("aws","AWS controls"),("gcp","GCP controls"),("local","Local Docker and Kubernetes"),("dashboards","Dashboards, services and costs"),("guide","Terraform and stack guide"),("stop-all","Stop all known cloud and local services")],exit_label="Exit controls")
            if choice is None:return 0
            if choice == "invalid":continue
            if choice in {"guide","stop-all"}:self.menu_action(choice);continue
            if choice in {"aws","gcp"}:
                entries=[("start","Start existing portal"),("stop","Stop portal and cloud scrapes"),("status","Check status"),("monitor-start","Start local Prometheus/Grafana for this provider"),("monitor-stop","Stop local Prometheus/Grafana"),("login","Sign in through browser"),("portal","Open tenant portal"),("update","Update code/infrastructure (build and Terraform)")]
                if choice == "gcp":entries.append(("prepare","Prepare first tenant-login deployment (keeps GCP stopped)"))
            elif choice == "local":
                entries=[("docker-open","Open Docker Desktop"),("docker-status","Show TicketPilot Docker containers"),("stop-local","Stop all local tools (cloud unchanged; demo data disposable)"),("k8s-start","Start and validate isolated Kubernetes demo"),("k8s-status","Check Kubernetes demo"),("k8s-stop","Stop Kubernetes demo (removes fictional data)"),("k8s-forward-app","Forward Kubernetes app: localhost:18080"),("k8s-forward-prometheus","Forward Kubernetes Prometheus: localhost:19090"),("k8s-forward-grafana","Forward Kubernetes Grafana: localhost:13000")]
            else:
                entries=[("grafana","Open local Grafana"),("prometheus","Open local Prometheus"),("aws-console","AWS console"),("aws-lambda","AWS Lambda monitoring"),("aws-cloudwatch","AWS CloudWatch logs/metrics"),("aws-ecr","AWS ECR images"),("aws-dynamodb","AWS DynamoDB tables"),("aws-ssm","AWS SSM parameters"),("aws-billing","AWS billing"),("aws-credits","AWS credits"),("aws-budgets","AWS budgets"),("gcp-console","GCP console"),("gcp-cloud-run","GCP Cloud Run monitoring"),("gcp-firestore","GCP Firestore"),("gcp-artifact-registry","GCP container images"),("gcp-logs","GCP logs"),("gcp-billing","GCP billing/budgets/credits"),("k8s-app","Kubernetes app: localhost:18080"),("k8s-prometheus","Kubernetes Prometheus: localhost:19090"),("k8s-grafana","Kubernetes Grafana: localhost:13000")]
            while True:
                action=self.choose(choice.upper()+" controls",entries)
                if action is None:break
                if action == "invalid":continue
                self.menu_action("open" if choice == "dashboards" else choice,action)


class Arguments(argparse.ArgumentParser):
    def error(self,message):
        self.print_usage(sys.stderr)
        self.exit(2,"Invalid control arguments; use --help.\n")


def parser():
    result=Arguments(description=__doc__)
    result.add_argument("--check",action="store_true",help="Inspect local tool/helper availability only; no cloud or Docker calls")
    groups=result.add_subparsers(dest="group")
    for provider in ("aws","gcp"):
        group=groups.add_parser(provider)
        group.add_argument("action",choices=CLOUD_ACTIONS+(("prepare",) if provider == "gcp" else ()))
        group.add_argument("--confirm-other-offline",action="store_true",help="Permit one guarded attestation retry only after other-provider authentication failed")
    groups.add_parser("local").add_argument("action",choices=LOCAL_ACTIONS)
    groups.add_parser("open").add_argument("action",choices=tuple(LOCAL_URLS)+tuple(AWS_URLS)+tuple(GCP_PATHS))
    groups.add_parser("stop-all")
    groups.add_parser("guide")
    return result


def main(argv=None,controller=None):
    options=parser().parse_args(argv)
    selected=controller or Controller()
    try:
        if options.check:
            if options.group:raise ControlError("Use --check by itself.")
            report=selected.check();selected.print(json.dumps(report,indent=2))
            return 0 if report["project_python"] and report["cloud_controls"] else 1
        if not options.group:return selected.menu()
        return selected.perform(options.group,getattr(options,"action",None),attest=getattr(options,"confirm_other_offline",False))
    except ControlError as error:
        selected.print(str(error));return 1
    except KeyboardInterrupt:
        selected.print("Controls closed. Check service Status if an action was interrupted.");return 130


if __name__ == "__main__":
    sys.exit(main())
