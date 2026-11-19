TICKETPILOT APARTMENTS - GCP
===========================
Checkpoint: November 19, 2026 (Asia/Manila).
Run commands from the standalone ticketpilot-aws repository root.

BEGINNER REDEPLOY
1. In ticketpilot-aws double-click TICKETPILOT.cmd. Open Docker Desktop from Local.
2. Under GCP controls choose Sign in through browser. Complete both Google
   sign-ins. Keep AWS paused when switching to GCP.
3. Prepare and eight-account provisioning completed on November 19. For normal
   code updates choose Redeploy current code. Start resumes the existing image.
4. For later code changes use Redeploy current code. Check status. Choose Start
   existing portal when ready to serve and verify HTTP 200. Open the tenant portal.
5. Choose Start local Prometheus/Grafana to scrape this provider. Finish with Stop
   portal and cloud scrapes. The retained paused Cloud Run URLs normally return 503.

Full walkthrough: docs/OPERATIONS_QUICKSTART.md. Code map: docs/CODEBASE_USAGE.md.

RECORDED STATUS AND RETAINED URLS
--------------------------------
The authenticated Cloud Run release was prepared and started on November 19.
Both recorded health URLs returned HTTP 200 with Firestore storage and paid AI off.
Eight separate tenant accounts were provisioned. Live sign-in, privacy and workflow
acceptance passed. Independent Firestore reads confirmed two synthetic concerns,
and both were cleaned up. AWS remained paused with HTTP 429.

Tenant:  https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/tenant
Manager: https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/manager
URLs remain unavailable while paused. See docs/DEPLOYMENT_STATUS.md for actual
evidence and docs/TENANT_ACCESS.md for accounts and separate provider inventories.
The deployed source uses a private Firestore auth collection for password/session
hashes and revocation. No additional hosted identity service is added. Keep the
GCP credentials file separate from the private AWS inventory; switching providers
does not migrate accounts, sessions, concerns or tracking links.

ARCHITECTURE
------------
Cloud Run HTTP container; request-based automatic min0/max1 enabled, MANUAL 0 paused;
Firestore Standard Native durable records and private authentication collection; Secret Manager; Artifact Registry
immutable digest; attached runtime service account; Cloud Monitoring/Logging.
Enabled runtime:1 CPU/512 MiB, concurrency4, timeout30s, manual refresh/queue20, AI off.
Terraform roots: infra/gcp/bootstrap and infra/gcp/app. Shared domain/UI, provider
adapters and rationale: docs/ARCHITECTURE_GCP.md, docs/CLOUD_PORTABILITY.md.

TOOLS AND BROWSER SIGN-IN
-------------------------
Use Google Cloud CLI, Terraform, the existing Python environment and Docker Desktop
for local builds. Named configuration ticketpilot-gcp; region asia-southeast1.
Keep real project/billing IDs/emails in ignored local configuration. Renew CLI
and ADC separately for the existing configuration without resuming the app:

  gcloud config configurations activate ticketpilot-gcp
  gcloud auth login
  gcloud auth application-default login
  gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID

No long-lived service-account JSON key or GCP MCP connection is configured.
ADMIN_TOKEN/METRICS_TOKEN remain private and map to Secret Manager names
ticketpilot-apartments-admin and ticketpilot-apartments-metrics. Upload values
outside Terraform state; preserve existing versions unless deliberately rotating.
Authentication alone does not start the site or local monitoring.

OPTIONAL MANUAL LOCAL BUILD AND VALIDATION
------------------------------------------
Keep the existing environment. New environments need requirements-dev.txt and
requirements-gcp.txt plus scripts/setup_local.py. Checks/build below do not
provision a cloud project. Docker must be running for containers:

  .\.venv\Scripts\python.exe -m pytest -q
  terraform fmt -check -recursive infra
  terraform -chdir=infra/gcp/bootstrap init -backend=false -input=false -lockfile=readonly
  terraform -chdir=infra/gcp/bootstrap validate
  terraform -chdir=infra/gcp/app init -backend=false -input=false -lockfile=readonly
  terraform -chdir=infra/gcp/app validate
  docker buildx build --platform linux/amd64 --load -f Dockerfile.gcp -t ticketpilot-gcp:local .
  docker pull gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators
  .\.venv\Scripts\python.exe scripts/validate_firestore_local.py --image ticketpilot-gcp:local

The isolated emulator checker uses fictional data,512 MiB/1 CPU/read-only app root,
no host cloud credentials and cleanup of only its own Docker resources. Use the
GCP Dockerfile; the Lambda image has a different runtime entry point.

CENTRAL PROVIDER OPERATIONS
---------------------------
Read scripts/cloud.py --help and docs/PROVIDER_OPERATIONS.md before changes:

  .\.venv\Scripts\python.exe scripts/cloud.py gcp status --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp deploy --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp pause --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp resume --project YOUR-GCP-PROJECT-ID

Central deploy builds Dockerfile.gcp as ticketpilot-gcp:local, runs the pinned
real Firestore emulator check and confirms the same local image ID is promoted
before native scripts/deploy_gcp.py --stage all. No separate prebuild is needed.
--skip-build --local-image YOUR-LOCAL-IMAGE-TAG explicitly reuses a prevalidated
image and skips the local emulator check. Native stages remain
preflight/bootstrap/deploy/all/pause/resume. Deploy preserves saved pause state
and skips online acceptance while paused. The authenticated release and account registry were accepted on November 19.
Reuse the existing accounts and private inventory when resuming. Resume explicitly restores automatic
min0/max1. Changing stages alter cloud resources; they retain records, secrets,
images, identity and state. Preserve matching private states/generated settings.

Before enabling a provider, the central guard checks the other configured cloud.
It cannot ignore active/unknown state. The narrow --confirm-other-offline option
requires explicit attestation, recorded paused=true and fresh expected unavailable
HTTP at every known URL when authenticated reads fail; it cannot override an
authenticated active/tagged deployment. Review the guard result; expired login
is not successful authenticated verification.

Native bootstrap needs budget permission. --billing-account supplies an existing
account; omitting it does not disable budget creation. Inspect existing Firestore
mode/location before creation; permission errors do not establish absence. See
docs/GCP_DEPLOYMENT.md for provider-specific configuration/manual fallback.

After authenticated-release deployment and authorized resume, explicitly requested
live acceptance uses current authorized tenant credentials, fictional concerns and independent
exact-ID Firestore reads with ADC; guarded cleanup preserves existing data and
building notices. Never publish private reports, tokens or tenant screenshots.

MONITORING, COSTS AND STOP
-------------------------
Native deployed views are Cloud Run/Cloud Monitoring/Cloud Logging. Optional local
Prometheus/Grafana use only the selected active provider:

  .\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-start --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-stop --project YOUR-GCP-PROJECT-ID

Local monitoring uses authenticated 300-second scraping;pause stops it and retains volumes.
Deploy/resume does not start monitoring automatically. Requests can still consume
cloud usage. No hosted Grafana/Prometheus, GKE or paid AI endpoint is added. Kind is
an isolated fictional-data exercise;CI evidence is separate from cloud deployment.

The installed USD 10 gross-cost alert is NOT a spending cap. Check recipients,
remaining trial credit and expiry. Retained storage/images/secret versions, logs
and requests can consume allowances/credits. No automatic plan upgrade occurs.

Double-click STOP_SERVICES.cmd or run scripts/stop_services.py to stop local
workloads and independently pause both recorded providers. --provider aws or
--provider gcp selects one; --local-only contacts neither. Inspect each result:
expired login is a failure, not a verified pause. Real data remains retained.

Preserve both GCP states, private generated .tfvars, backups and accepted digests.
Never apply empty state over existing resources. Destruction is separate and
requires explicit protection/data review;Firestore ABANDON/delete protection
retains the database. Do not delete data, billing or state merely to pause.

Related: docs/PROVIDER_OPERATIONS.md, docs/ARCHITECTURE_GCP.md,
docs/ARCHITECTURE_AWS.md, docs/CLOUD_PORTABILITY.md, docs/aws/README.txt,
docs/KUBERNETES.md, docs/CI_CD.md.
