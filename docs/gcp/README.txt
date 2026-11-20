TICKETPILOT APARTMENTS - GCP DEPLOYMENT
====================================

Run commands from the repository root containing TICKETPILOT.cmd.
The GCP path deploys the shared FastAPI application to Cloud Run in Singapore
(asia-southeast1), with Firestore persistence and native runtime identity.

Architecture and deployment details are in docs/ARCHITECTURE_GCP.md and
docs/GCP_DEPLOYMENT.md. Verified images, checks and recorded service state are
summarized in docs/DEPLOYMENT_STATUS.md.

REQUIREMENTS AND AUTHENTICATION
------------------------------
Install Python 3.11, Google Cloud CLI, Terraform and Docker Desktop with a Linux
engine. Local validation uses requirements-dev.txt and requirements-gcp.txt.
Fresh-clone setup is documented in docs/STACK_GUIDE.md. Retained deployments also
require matching private state, settings, deployment records and secrets.

Use the named ticketpilot-gcp CLI configuration. Create and select it as described
in docs/GCP_DEPLOYMENT.md if it does not yet exist.

  gcloud config configurations activate ticketpilot-gcp
  gcloud auth login
  gcloud auth application-default login
  gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID

The CLI and Application Default Credentials are separate sign-ins. Terraform and
the independent Firestore validator use ADC. Cloud Run uses its attached runtime
service account. Credential files stay outside version control.

DEPLOYMENT
----------
The central lifecycle command builds Dockerfile.gcp and runs the pinned isolated
Firestore emulator before image promotion.

  .\.venv\Scripts\python.exe scripts/cloud.py gcp status --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp deploy --project YOUR-GCP-PROJECT-ID

The image that passes validation is pushed to regional Artifact Registry and
applied by immutable digest. --skip-build --local-image explicitly selects an
already built and validated image. The helper rejects destructive or unrelated
Terraform plan changes and applies its saved reviewed plan.

Terraform roots have independent state.
  infra/gcp/bootstrap    APIs, registry, secret metadata and optional alert budget
  infra/gcp/app          Runtime identity, permissions, Firestore and Cloud Run

ADMIN_TOKEN and METRICS_TOKEN are uploaded as Secret Manager versions outside
Terraform state. Their metadata and scoped runtime access are managed by Terraform.

For an initial tenant-login rollout of a configured installation, choose Prepare
first tenant-login deployment in the launcher. It deploys while paused and
provisions a separate eight-account GCP registry. The private inventory is
.secrets/gcp-tenant-credentials.json. Subsequent lifecycle operations reuse it.
See docs/TENANT_ACCESS.md for account administration.

START AND STOP
--------------
Start resumes the retained image. Redeploy publishes changed code and preserves
the saved pause state.

  .\TICKETPILOT.cmd gcp start
  .\TICKETPILOT.cmd gcp status
  .\TICKETPILOT.cmd gcp stop

Enabled scaling uses request-based billing, minimum zero and maximum one instance.
Pause selects manual scaling with zero instances and verifies the expected
unavailable responses at both recorded service URLs. Database records, accounts,
images, secrets, runtime identity and Terraform state are retained.

The central guard checks the other configured provider before deploy/resume.
The narrow --confirm-other-offline exception requires explicit attestation,
recorded paused state and fresh expected unavailable HTTP at every known URL.
An authenticated active provider remains blocked. See docs/PROVIDER_OPERATIONS.md.

VALIDATION
----------
CI validates the GCP container against a real isolated Firestore emulator and
checks both Terraform roots without cloud credentials. Live acceptance separately
verifies tenant sign-in, unit ownership, CSRF, private tracking, manager notes,
replies/reopening and conflicting updates.

Independent Firestore reads confirm only the validator's exact synthetic documents.
Guarded cleanup removes those records. The authenticated GCP release passed this
live acceptance. Evidence and the measured latency baseline are documented in
docs/DEPLOYMENT_STATUS.md and docs/CLOUD_BENCHMARKS.md.

MONITORING AND COST CONTROLS
---------------------------
Cloud Run, Cloud Monitoring and Cloud Logging provide native service health,
request and execution-log views. Optional Prometheus/Grafana run locally.

  .\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-start --project YOUR-GCP-PROJECT-ID
  .\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-stop --project YOUR-GCP-PROJECT-ID

The 300-second authenticated scrape invokes the cloud endpoint. Pause stops local
cloud monitoring and retains its volumes. Process counters reset per container.
Local kind Kubernetes validation is documented in docs/KUBERNETES.md.

The default 1-vCPU/512-MiB runtime uses concurrency four, a 30-second timeout,
manual manager refresh and a 20-record queue. Paid AI is disabled. The installed
USD 10 gross-cost budget sends alerts. Confirm recipients and monitor retained
database/image/secret storage, logs and request usage as well as account credits.

STOP_SERVICES.cmd stops local workloads and attempts independent pauses of both
recorded clouds. --provider gcp selects GCP, and --local-only skips cloud calls.
Inspect every operation result. Protected teardown and retained Firestore data
are described in docs/GCP_DEPLOYMENT.md.

Related documentation
  docs/OPERATIONS_QUICKSTART.md
  docs/PROVIDER_OPERATIONS.md
  docs/ARCHITECTURE_GCP.md
  docs/CLOUD_PORTABILITY.md
  docs/TENANT_ACCESS.md
  docs/CI_CD.md
