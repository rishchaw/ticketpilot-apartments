TicketPilot Apartments - GCP deployment guide
============================================

Run every command below from the standalone repository root, ticketpilot-aws,
in PowerShell. This file documents the recorded deployment; it does not perform
or claim a fresh live-service check.

Documentation updated: November 17, 2026 (Asia/Manila)
Recorded status: November 16, 2026
---------------------------------
Cloud Run in Singapore was deployed with Terraform and verified with fictional
records. Tenant intake, private tracking, manager notes/replies, concurrent
updates and independent Firestore SDK persistence passed. Hosted GitHub CI also
passed all four jobs. See docs/DEPLOYMENT_STATUS.md for the evidence and dates.

Retained deployment URLs (unavailable while intentionally paused):
Tenant:  https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/tenant
Manager: https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/manager

The manager access code is the private ADMIN_TOKEN in local .env. Do not share
it with tenants. Report-specific tracking links must remain private.

When enabled, Cloud Run uses request-based billing, automatic scaling minimum
0/maximum 1 instances, 1 CPU,
512 MiB, concurrency 4 and a 30-second timeout. Firestore stores durable records;
Cloud Run's temporary filesystem must not be used for a live SQLite database.
Manager refresh is manual, the queue limit is 20, and paid AI calls are disabled.
The CPU classifier and local retrieval remain available. AWS is a separate path
and remains pending account activation; changing providers does not migrate data.

Requirements and authentication
-------------------------------
Use Python 3.11, Docker Desktop with Linux containers running, Terraform and the
Google Cloud CLI. An existing project needs linked trial billing and permissions
for required APIs, Cloud Run, Firestore, Artifact Registry, Secret Manager,
service accounts/IAM and the alert budget. Do not upgrade the plan automatically.
Replace YOUR-PROJECT-ID and any billing placeholder with your own local values;
do not commit project/billing IDs, account emails or credentials.

For a new local environment only:

  py -3.11 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-gcp.txt
  .\.venv\Scripts\python.exe scripts/setup_local.py

Preserve an existing .env. Secret values are not documented here. ADMIN_TOKEN and
METRICS_TOKEN map to Secret Manager names ticketpilot-apartments-admin and
ticketpilot-apartments-metrics. The helper preserves existing cloud secret
versions and creates only initial values outside Terraform state. Retain the
matching private local configuration when managing the existing deployment.

Use the named CLI configuration ticketpilot-gcp (not the AWS ticketpilot profile)
and region asia-southeast1. Skip configuration creation if it already exists:

  gcloud config configurations create ticketpilot-gcp
  gcloud config configurations activate ticketpilot-gcp
  gcloud auth login
  gcloud config set project YOUR-PROJECT-ID
  gcloud config set run/region asia-southeast1
  gcloud auth application-default login
  gcloud auth application-default set-quota-project YOUR-PROJECT-ID

CLI login and Application Default Credentials (ADC) are separate. Terraform and
the Python client use ADC; Cloud Run uses its attached runtime service account.
No GCP MCP connection or long-lived service-account JSON key is configured.

Local build and credential-free validation
-----------------------------------------

  .\.venv\Scripts\python.exe -m pytest -q
  terraform fmt -check -recursive infra
  terraform -chdir=infra/gcp/bootstrap init -backend=false -input=false -lockfile=readonly
  terraform -chdir=infra/gcp/bootstrap validate
  terraform -chdir=infra/gcp/app init -backend=false -input=false -lockfile=readonly
  terraform -chdir=infra/gcp/app validate
  docker buildx build --platform linux/amd64 --load -f Dockerfile.gcp -t ticketpilot-gcp:local .
  docker pull gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators
  .\.venv\Scripts\python.exe scripts/validate_firestore_local.py --image ticketpilot-gcp:local

The validator uses isolated, labeled Docker objects and fictional data, mounts no
cloud credentials, enforces 512 MiB/1 CPU/read-only app filesystem, and checks
privacy, version conflicts and persistence after app restart. It removes only
its own containers/networks. Docker Desktop uses an internal emulator network
plus a separate app bridge for localhost access. Reports are under ignored
.tools/. Passing local checks does not establish live IAM or billing access.

Staged cloud deployment
-----------------------
Preserve the existing Terraform state before running against an already deployed
project. Never start with empty state and recreate resources that already exist.

First run help and read-only cloud preflight:

  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --help
  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --budget-usd 10 --stage preflight

The next two stages CHANGE CLOUD RESOURCES. Bootstrap manages APIs, the regional
image repository, secret metadata and budget. Deploy inspects Firestore, uploads
initial secrets if absent, pushes the already-built local image, applies the app
by immutable digest and runs live synthetic acceptance/guarded cleanup:

  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --budget-usd 10 --stage bootstrap
  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --budget-usd 10 --stage deploy --local-image ticketpilot-gcp:local

Each changing stage creates a saved plan, prints a summary, rejects unexpected
resource types/deletes/replacements and applies without another interactive
approval prompt. For a separate review pause, run Terraform plan and apply
separately with the same local variable files; see docs/GCP_DEPLOYMENT.md for
configuration details. Do not use the Lambda Dockerfile for this GCP image.

The helper discovers the linked billing account and requires budget permission.
Optional --billing-account YOUR-BILLING-ACCOUNT-ID supplies the existing account;
omitting it does not disable the budget. If permission is unavailable, stop and
review the manual Terraform fallback with create_budget=false.

An existing suitable default Firestore database is left unmodified unless already
managed in this state. Creation requires confirmed absence. Permission/API errors
are not evidence of absence; do not replace an incompatible existing database.

After explicitly resuming the site, an online acceptance rerun creates and
cleans two fictional records:

  .\.venv\Scripts\python.exe scripts/validate_gcp_deployment.py --url https://ticketpilot-apartments-xliyw4o22q-as.a.run.app --project YOUR-PROJECT-ID --env-file .env

This uses local ADMIN_TOKEN and ADC in-process, checks only its exact synthetic
IDs and preserves existing tenant records/notices. Do not publish secret values,
private tracking links, real tenant screenshots or full local deployment reports.

Temporary offline operation and local Kubernetes
------------------------------------------------
For a combined stop from the repository root:

  .\.venv\Scripts\python.exe scripts/stop_services.py

This stops Compose while preserving volumes, removes only an owned disposable
kind demo when Docker is available, and pauses existing GCP through Terraform.
The project comes from the private local deployment record; use --project
YOUR-PROJECT-ID if needed. --local-only skips GCP. An already-off Docker engine
stays off and cluster deletion is skipped; cloud pause is still attempted.
Check the summary for errors/skipped cloud work. Real cloud data/images/secrets
and Compose volumes remain; only kind's fictional demo data is disposable.

Read docs/DEPLOYMENT_STATUS.md for the latest verified pause/resume state. Pause
and resume use the existing Terraform state and modify service scaling only:

  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --stage pause
  .\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --stage resume

These commands CHANGE CLOUD CONFIGURATION. Pause sets paused=true, MANUAL
scaling and zero instances; the retained service URL becomes unavailable.
Resume sets paused=false and restores automatic min 0/max 1 scaling. This is
separate from a new image deployment. Deploy/all preserve the generated paused
state and skip online acceptance while paused; they do not implicitly resume.
Preserve generated settings: the Terraform
default paused=false is enabled. Console-only changes can drift from Terraform.

Both operations retain the database/records, images, secrets, budget and state.
Retained storage and other services can still consume allowances/credits; pause
is not a promise of zero total cost and does not upgrade the plan.

For local Compose, stop all services while retaining their volumes:

  docker compose --profile local stop

Restart the local app and Prometheus/Grafana only when wanted:

  docker compose --profile local up -d

Local Docker and cloud scaling are independent. A separate Kubernetes portfolio
demo runs only in local kind; see docs/KUBERNETES.md. It uses private demo-only
credentials and fictional SQLite data, no GKE or EKS cluster. Its stop command
removes only that disposable cluster/data, preserving real Compose/cloud data.

Costs, CI/CD and cleanup
-----------------------
The recorded USD 10/month project budget alerts at 50%, 90% and 100% of gross
cost before credits. It is NOT A SPENDING CAP. Alerts can lag usage. Confirm
recipients, remaining trial credit and expiry. Compute, storage, database reads,
secrets and logs can consume allowances/credits. No automatic plan upgrade occurs.

Prometheus/Grafana stay local in Docker; no always-running monitoring server or
paid AI endpoint is deployed. Frequent cloud scrapes/polling can start Cloud Run
and consume compute, so retain manual refresh for a sporadic demonstration.

GitHub Actions runs credential-free tests, emulator/container checks and Terraform
validation. GCP deployment is the manual local helper path; there is no automatic
GitHub-to-GCP promotion workflow or installed cloud deployment identity. Existing
container releases publish app/Lambda images, not a GCP-ready release. See
docs/CI_CD.md. CI success and live deployment verification are separate evidence.

Keep both infra/gcp/bootstrap and infra/gcp/app state files and private settings.
The helper preserves terraform.tfvars and writes ignored
ticketpilot.generated.tfvars, explicitly passed with -var-file. Backups are
private; never commit .env, .secrets/, credentials, state, plans or tenant data.

Use the pause stage for intentional unavailability. Closing the browser alone
allows idle scale-down but other requests can still start the enabled service.
Neither operation deletes retained storage/secrets.
For deliberate teardown, read docs/GCP_DEPLOYMENT.md, section "Stop or remove the
demonstration". Explicit protection changes are needed before destruction. Supply
the same local variable files when planning cleanup. Firestore uses ABANDON and
delete protection, so app removal retains the database. Bootstrap removal deletes
repository images and secrets; APIs remain enabled. Do not delete the project,
disable billing, destroy tenant data or upgrade the plan as automatic cleanup.

Full references: docs/GCP_DEPLOYMENT.md and docs/DEPLOYMENT_STATUS.md.

Windows shortcut: double-click STOP_SERVICES.cmd in the repository root to run the same stop helper. If Google authentication has expired, renew CLI and ADC browser sign-in before future cloud changes. The already paused site stays paused; local Kubernetes does not require Google login.
