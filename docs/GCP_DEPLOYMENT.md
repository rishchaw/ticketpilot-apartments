# Deploy TicketPilot to Google Cloud

For this existing project use **GCP controls → Sign in through browser → Prepare first tenant-login deployment**. Wait for account provisioning to finish before Start. Subsequent releases use **Redeploy current code**. See the [beginner redeploy and monitoring guide](OPERATIONS_QUICKSTART.md). The lower-level commands below are for operators inspecting the individual stages.

The GCP path runs the same apartment application on Cloud Run in Singapore (`asia-southeast1`) with Firestore for durable records. The service can be intentionally paused while its URL and stored data are retained; check the latest deployment status before treating a retained URL as an available website. Terraform keeps GCP infrastructure separate from the existing AWS roots. See [deployment status](DEPLOYMENT_STATUS.md) for observed results: preparation and authentication do not establish a successful cloud deployment.

## Shared lifecycle entry point

For streamlined deployment, use `python scripts/cloud.py gcp deploy --project YOUR-GCP-PROJECT-ID` from the repository root. It builds `Dockerfile.gcp`, runs the pinned real Firestore emulator validation and promotes the same validated local image ID before native `all`. No separate prebuild is required by default. `--skip-build --local-image YOUR-LOCAL-IMAGE-TAG` explicitly reuses a prevalidated image and skips that local emulator check. Use the launcher for day-to-day changes. The native stages below explain what it calls internally. Calling them directly bypasses the central check that the other provider is offline.

See [provider operations](PROVIDER_OPERATIONS.md), [GCP architecture](ARCHITECTURE_GCP.md), [AWS architecture](ARCHITECTURE_AWS.md) and [portability](CLOUD_PORTABILITY.md) for exclusive pause/resume, native monitoring and data/state boundaries. The stop wrapper now stops local workloads and independently pauses both recorded providers by default. Use --provider aws or --provider gcp for one cloud, or --local-only to contact neither. Inspect each result; one provider failure does not block the other attempt.

## Architecture and cost controls

| Component | Configuration | Purpose |
| --- | --- | --- |
| Cloud Run | Enabled: request-based billing, automatic scaling minimum 0/maximum 1; paused: manual count 0. 1 vCPU, 512 MiB, concurrency 4, 30-second timeout | Public HTTPS apartment portal when enabled; reversible offline state when paused |
| Firestore | Standard edition, Native mode, existing eligible `(default)` database or a deliberately created one | Concerns, replies, manager notes, notices and legacy demo records survive container replacement |
| Artifact Registry | Regional Docker repository, digest deployments, keep current deployment and newest two images | Stores the independently deployable container; paid automatic vulnerability scanning disabled |
| Secret Manager | Two secrets; runtime identity can access only those secrets | Manager and metrics access codes; values stay outside Terraform state |
| Optional billing budget | USD 10/month, project-wide, alerts at 50%, 90% and 100%, credits excluded | Warns about gross consumption; this configuration does not enforce a spending cap |

The Cloud Run filesystem is disposable and memory-backed, so SQLite must not hold live cloud records. The Firestore backend is selected by `STORAGE_MODE=firestore`. Local SQLite and AWS DynamoDB remain available; switching backends does not migrate existing data. See the [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract).

Cloud Run free usage is shared across a billing account and applied as a discount at Tier 1 prices. Singapore pricing differs from the cheaper US regions. This setup is intended for light apartment/demo traffic, and does not promise a zero bill. Artifact storage, database operations, secret versions/accesses, logs and network traffic also matter. See [Cloud Run pricing](https://cloud.google.com/run/pricing), [Firestore quotas](https://docs.cloud.google.com/firestore/quotas), [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) and [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing).

The GCP profile uses manual manager refresh (`APARTMENT_REFRESH_SECONDS=0`) and a 20-record queue to avoid unattended polling and repeated database reads. It disables model-provider calls with `LLM_PROVIDER=none`. The IT demo can run the packaged CPU classifier and local TF-IDF retrieval; this does not add Vertex AI, Gemini, Bedrock, an embedding endpoint or a hosted vector database.

Prometheus and Grafana remain in the local Docker stack. They are not deployed as always-running cloud containers. Do not point a frequent health check or Prometheus scrape at Cloud Run merely to keep it warm: each request can start an instance and consume compute. Cloud Run's built-in service metrics are separate from local Prometheus counters.

The optional Terraform budget sends alerts to default billing-account recipients; it does not stop this application. Confirm the intended recipient can receive them. Cost data and alerts can lag usage. Google also offers service-specific spend-cap budgets; this project does not configure one. Read [budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) before treating an alert target as enforcement.

## Prerequisites and sign-in

Use an existing dedicated project with trial billing already linked. Confirm remaining trial credit, trial expiry, account permissions and any organization policies in the Cloud Console. Do not automatically upgrade the billing plan. See [Google Cloud trial terms](https://docs.cloud.google.com/free/docs/free-cloud-features).

Install Python 3.11, Docker Desktop, Terraform and the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install). Start Docker, then work from this standalone repository root. Install `requirements-dev.txt` for application validation and `requirements-gcp.txt` for the optional Firestore client. `Dockerfile.gcp` installs the GCP requirements independently of the AWS Lambda image.

Use a named CLI configuration and browser sign-in. These examples contain placeholders; keep real account identifiers in local configuration rather than tracked defaults:

```powershell
gcloud config configurations create ticketpilot-gcp
gcloud config configurations activate ticketpilot-gcp
gcloud auth login
gcloud config set project YOUR-PROJECT-ID
gcloud config set run/region asia-southeast1
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR-PROJECT-ID
```

Skip `configurations create` if it already exists. CLI login and Application Default Credentials (ADC) are separate: Terraform and the Python Firestore client use ADC. Cloud Run uses its attached runtime service account. Do not create or download a long-lived service-account JSON key. No GCP MCP server is configured by this project; CLI access does not imply an MCP connection. See [local ADC setup](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

The signed-in user needs permission to enable required APIs, create the repository/secrets/runtime identity, manage the project's scoped IAM bindings and deploy Cloud Run. Creating a database additionally requires Firestore permissions. Creating an alert budget additionally requires billing-account budget permissions; leave `create_budget=false` if those are unavailable. Review existing permissions instead of adding broad permanent administrator credentials to the app.

## Validate locally before provisioning

```powershell
.\.venv\Scripts\python.exe -m pytest -q
terraform -chdir=infra/gcp/bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/gcp/bootstrap validate
terraform -chdir=infra/gcp/app init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/gcp/app validate
terraform fmt -check -recursive infra
docker buildx build --platform linux/amd64 --load -f Dockerfile.gcp -t ticketpilot-gcp:local .
docker pull gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators
.\.venv\Scripts\python.exe scripts/validate_firestore_local.py --image ticketpilot-gcp:local
```

The Firestore validator starts its own isolated Docker network, Firestore emulator and 512 MiB/one-CPU read-only application container. It uses fictional records, tests real HTTP workflows, concurrent version conflicts and restart persistence, then removes only its own labeled containers/network. It uses no host credentials. The default emulator image is `gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators`; `--emulator-image` can explicitly override it. Its report is `.tools/gcp-local-validation.json`. A passing emulator check does not prove live IAM, account service access or billing readiness. A 512 MiB container must pass constrained startup and workflow checks; use the supported Terraform `memory="1Gi"` only if validation shows 512 MiB is insufficient.

## Preflight the existing project

Check the selected CLI project/configuration, linked billing status and the existing Firestore databases before applying anything. Inspect the full default database metadata, including its location, type and edition. Firestore location is not a setting to casually change after creation.

```powershell
gcloud --configuration=ticketpilot-gcp config list
gcloud --configuration=ticketpilot-gcp firestore databases list --project=YOUR-PROJECT-ID
gcloud --configuration=ticketpilot-gcp firestore databases describe --database='(default)' --project=YOUR-PROJECT-ID
```

If the default database does not exist, set `manage_database=true` only after that absence has been confirmed. An API-disabled, permission-denied or authentication error does not establish absence; resolve that error before choosing creation. The application root creates a Standard Native database in the chosen region, with deletion protection, no PITR and Terraform `ABANDON` deletion policy. It creates no scheduled backup. If a suitable default database already exists, leave `manage_database=false` so Terraform leaves it unmodified. If it is in an unexpected location or mode, stop and review compatibility; do not replace it or create an additional paid database just to bypass the check. Firestore free quota applies to only one eligible database per project. See [Firestore quotas](https://docs.cloud.google.com/firestore/quotas).

Do not print access tokens, ADC files, local `.env`, secret values or live tenant data in diagnostics. Avoid committing project/billing IDs or account email addresses to deployment examples.

## Provision and deploy

The two Terraform roots use separate local state by default:

- `infra/gcp/bootstrap`: required APIs, image repository, secret metadata and optional alerts-only budget.
- `infra/gcp/app`: runtime service account/permissions, optional default Firestore database and public Cloud Run service.

For manual Terraform use, copy each `terraform.tfvars.example` to the same directory as `terraform.tfvars` and set the existing project ID locally. The deployment helper preserves these files and writes its derived settings into ignored `ticketpilot.generated.tfvars` files, passed explicitly with `-var-file`. These files, Terraform state/plans, credentials and `.gcloud` caches are ignored by Git. Preserve private copies of state; do not apply against a fresh empty state when resources already exist. No remote state bucket is created by this minimal deployment.

The deployment helper is `scripts/deploy_gcp.py`. Its default stage is read-only preflight; inspect its help and run that check first:

```powershell
.\.venv\Scripts\python.exe scripts/deploy_gcp.py --help
.\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --budget-usd 10 --stage preflight
```

After preflight succeeds, `--stage bootstrap` handles the bootstrap root and `--stage deploy` handles image delivery/application deployment. Build and emulator-test `ticketpilot-gcp:local` first, or supply another already-tested image through `--local-image`. `--stage all` performs preflight, guarded bootstrap plan/apply, secret-version upload outside Terraform, image push, then guarded application plan/apply using the immutable image digest. These stages change cloud resources. The helper prints its plan summary, rejects deletes/replacements or unexpected resource types, and applies its saved plan; it does not provide a separate interactive approval prompt. Use manual Terraform plan/apply instead if a separate human review pause is required. Bootstrap must exist before the image push and the application root. The helper discovers the project's linked billing account and requires permission to create its USD 10 alert budget. `--billing-account YOUR-BILLING-ACCOUNT-ID` explicitly supplies that existing account when needed; omitting it does not disable the budget. If budget permissions are unavailable, stop the helper and use the manual Terraform path with bootstrap `create_budget=false` after reviewing the cost-monitoring tradeoff. Confirm whether the budget was actually created; an alert described in source is not an installed alert.

The repository is `asia-southeast1-docker.pkg.dev/YOUR-PROJECT-ID/ticketpilot-apartments`. This Terraform root accepts only a same-project/same-region image address ending in `@sha256:...`. Deployments keep a mutable `deployed` tag pointing at the current successful image so cleanup retains it. Images older than seven days can be deleted except for that tag and the two most recent versions. Build from `Dockerfile.gcp`, not the Lambda Dockerfile. No Cloud Build job is required.

`ADMIN_TOKEN` and `METRICS_TOKEN` come from local private configuration and are uploaded as Secret Manager versions. Terraform creates secret metadata and access bindings, never token values. The runtime identity receives `roles/datastore.user` and secret access on only those two secrets. It has no AI-provider role. Roll out a new Cloud Run revision after secret rotation because environment variable secrets are resolved at instance startup; do not assume every existing instance immediately picks up a new `latest` version. See [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## Verify the live deployment

A successful Terraform apply is only the infrastructure step. When the service is intentionally paused, the URL is expected to be unavailable and online acceptance is skipped. Resume explicitly before running online checks. Check the deployed revision and digest, runtime settings, public HTTPS URL, configured Firestore database and secret access. Then run:

```powershell
.\.venv\Scripts\python.exe scripts/validate_gcp_deployment.py --url https://SERVICE.run.app --project YOUR-PROJECT-ID --env-file .env --credentials-file .secrets/gcp-tenant-credentials.json
```

The deployed validator reads the manager code from the local private environment file, creates two clearly synthetic concerns, checks private tracking/manager updates/reopening/version conflicts, and independently verifies their exact Firestore documents through ADC. It never lists real manager queues or collections and does not publish a building notice. Cleanup targets only its own matching synthetic IDs with update-time preconditions. Its report is `.tools/gcp-deployment-validation.json`. Separately verify record persistence across a replacement Cloud Run revision. Use fictional records and preserve existing data. Never upload manager codes, private tracking links or real tenant screenshots as portfolio artifacts. Keep a record of which checks actually ran and their results in `DEPLOYMENT_STATUS.md`.

Share `/tenant` or a QR code only after these checks pass. A public link does not verify tenant identity. Keep report-specific tracking links private, review building guidance and decide retention before a real tenant pilot. Prometheus counters reset per process and are not the authoritative concern queue.

## CI/CD and provider portability

GitHub Actions remains the source/test/container-delivery platform. The existing release produces app/Lambda images; it does not publish a Firestore-enabled Cloud Run release. CI also exercises a disposable GCP container/Firestore emulator and validates both GCP Terraform roots without cloud credentials. These checks are separate from deployment and account permissions. No GCP deployment workflow or GitHub-to-GCP credentials are installed by this local setup. See [CI/CD](CI_CD.md) for the actual workflow boundaries.

The same FastAPI routes, manager/tenant UI, NumPy artifacts, retrieval data and domain workflow run across providers. Storage and platform identities differ:

| Environment | Persistence | Runtime and identity | Infrastructure |
| --- | --- | --- | --- |
| Local | SQLite on a Docker volume | Local Compose and private `.env` | Compose; Prometheus/Grafana |
| AWS | DynamoDB | Lambda, execution role, SSM parameters | `infra/bootstrap` and `infra/aws` |
| GCP | Firestore | Cloud Run, attached service account, Secret Manager | `infra/gcp/bootstrap` and `infra/gcp/app` |

These are independently deployable provider paths, not automatic failover or replicated multi-cloud data. Existing SQLite/DynamoDB records are preserved; no implicit data migration occurs. AWS has its own deployed tenant-login release, last recorded paused. Optional AWS Bedrock RAG remains in source and disabled in the GCP profile.

## Temporarily pause and resume

For a combined stop from the repository root, run:

```powershell
.\.venv\Scripts\python.exe scripts/stop_services.py
```

It stops Compose while preserving volumes, removes only an owned disposable kind demo when Docker is available, and attempts to pause both recorded cloud services through Terraform. The project comes from the private local deployment record; use `--project YOUR-PROJECT-ID` if needed. `--local-only` skips both clouds. If Docker is already off, it stays off and cluster deletion is skipped; cloud pause is still attempted. Check the printed summary for errors or skipped cloud work. Real cloud records/images/secrets and Compose volumes are retained; only kind's fictional demo data is disposable.

Use the Terraform-managed `paused` variable through the helper to take the existing service offline without destroying the deployment. These commands change the service scaling configuration and require the existing private application state and generated variable file:

```powershell
.\.venv\Scripts\python.exe scripts/deploy_gcp.py --project YOUR-PROJECT-ID --region asia-southeast1 --stage pause
.\.venv\Scripts\python.exe scripts/cloud.py gcp resume --project YOUR-PROJECT-ID
```

Pause sets `paused=true`, Cloud Run manual scaling and zero instances. The deploy/all stages preserve the existing generated paused state; deploying a new image while paused skips online acceptance rather than silently bringing the site back online. Requests to the normal service URL become unavailable; existing requests can finish. Resume sets `paused=false` and restores automatic request-based scaling with minimum 0/maximum 1. It is a scaling change rather than a new image release. Consult the helper's help and the latest status for the actual observed operation/result. The Terraform default is enabled (`paused=false`), so preserve the local generated settings instead of applying against defaults or a fresh state.

Firestore, Artifact Registry images, Secret Manager values, the runtime identity, service URL, Terraform state and budget are retained. Storage, secret versions, database activity and other retained services can still consume allowances or credits. The USD 10 budget remains an alert, not a cap. No billing-plan upgrade is needed for pause or resume.

Cloud Console scaling changes can drift from Terraform; reconcile them before the next apply. Cloud Run traffic-tag-only revisions are not disabled by service manual zero, so verify that no separate tag URLs remain active if every public endpoint must be offline. See [Cloud Run manual scaling](https://docs.cloud.google.com/run/docs/configuring/services/manual-scaling).

Local Compose is separate. Stop the application, Prometheus and Grafana while retaining their containers and data volumes, then restart only when wanted:

```powershell
docker compose --profile local stop
docker compose --profile local up -d
```

Stopping local Docker does not pause Cloud Run. The optional [local Kubernetes demonstration](KUBERNETES.md) uses kind on this PC and creates no GKE/EKS resources. Its own stop command deletes only its disposable demo cluster/data; it does not remove real Compose volumes or cloud records.

## Stop or remove the demonstration

For a temporary offline period, use pause above rather than destroying the service. Merely closing the browser allows idle scale-down but leaves a public automatically scaled service available to other requests; it does not delete artifacts, secrets or Firestore records. Review the billing report and remove unused old secret versions/images rather than leaving repeated test deployments indefinitely.

To remove compute, first change `protect_service=false` in local application variables, apply that explicit protection change, then review `terraform -chdir=infra/gcp/app destroy`. The Firestore resource uses `ABANDON` and database deletion protection: application destruction leaves database data behind. Preserve the state and review retained data separately.

For bootstrap cleanup, explicitly change `protect_resources=false`, apply the protection change, then review bootstrap destruction. This deletes repository images and secret metadata/versions. Required project APIs remain enabled by design. An existing database outside this root is never destroyed by it. Do not delete a shared project, disable billing, destroy a database or upgrade the trial as an automatic cleanup step.

Windows shortcut: double-click STOP_SERVICES.cmd in the repository root to run the same stop helper. If Google authentication has expired, renew CLI and ADC browser sign-in before future cloud changes. The already paused site stays paused; local Kubernetes does not require Google login.
