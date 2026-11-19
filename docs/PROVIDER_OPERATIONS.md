# Provider operations runbook

Open `TICKETPILOT.cmd` for daily operations. **Check all service statuses (live)** queries each provider independently, plus Compose and kind. On November 19 GCP was enabled after Prepare, eight-account provisioning and live Firestore acceptance. AWS remains paused. [Beginner guide](OPERATIONS_QUICKSTART.md) · [Deployment evidence](DEPLOYMENT_STATUS.md) · [Benchmark baseline](CLOUD_BENCHMARKS.md)

## Shared interface

The central command is provider first, action second:

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py --help
.\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py gcp status --project YOUR-GCP-PROJECT-ID
```

Actions are deploy, pause, resume, status, monitor-start and monitor-stop. AWS defaults to profile ticketpilot/Singapore ap-southeast-1. GCP uses named configuration ticketpilot-gcp, ADC and asia-southeast1. Keep account/project/billing IDs, recipients, credentials and reports private. Script help controls supported flags.

Authenticated status checks the configured runtime/pause setting; URL checks provide additional availability evidence. Source code and old reports do not establish fresh control-plane state. Missing state is not an absent deployment; restore private state rather than recreating resources to silence errors.

## Authenticate without enabling services

Use AWS browser sign-in, then read-only service checks:

```powershell
aws login --profile ticketpilot
.\.venv\Scripts\python.exe scripts/preflight_aws.py --profile ticketpilot --region ap-southeast-1
```

Identity success alone does not establish Lambda/DynamoDB activation or create permissions. Keep the existing plan and check remaining credits/expiry. Do not create static keys.

Renew existing GCP CLI and ADC sessions separately:

```powershell
gcloud config configurations activate ticketpilot-gcp
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID
```

Authentication must not resume the application or start monitoring. No GCP MCP server or long-lived service-account JSON key is configured. Remaining offline does not require renewing credentials immediately.

## One serving provider at a time

The default exclusive guard blocks target deploy/resume if another configured provider is active or its state cannot be confirmed. Do not erase a deployment record, change a global profile or bypass a failed pause to satisfy the guard.

When authenticated status of an otherwise recorded-paused provider is unavailable, --confirm-other-offline is a narrow explicit operator attestation. It still requires the saved paused state and fresh expected public HTTP results at every known URL (AWS: 404/429; GCP: 404/503). It cannot override authenticated active or traffic-tagged state, a recorded-active provider or a reachable endpoint. This is an exception with availability evidence, not a claim that expired authentication succeeded. Review the printed guard result before proceeding.

1. Read both statuses and restore correct private settings/state if missing.
2. Pause the serving provider; verify disabled behavior.
3. Resolve errors, or deliberately use the narrow attestation only when its prerequisites hold.
4. Deploy or resume the target; keep AI off, verify the digest/runtime and run synthetic acceptance.
5. Record actual results, including any attestation and concurrency fallback.

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py gcp pause --project YOUR-GCP-PROJECT-ID
.\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot
```

Only for a genuinely recorded-paused provider with expired authentication may an explicit operator invoke the guarded exception. The active GCP deployment must be paused before switching to AWS.

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot --confirm-other-offline
```

GCP Prepare and account provisioning completed on November 19. A subsequent switch to that prepared release uses the existing accounts and image.

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws pause --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py gcp resume --project YOUR-GCP-PROJECT-ID
```

These are deliberate alternative operations, not an instruction to enable both. A normal image deployment preserves the saved paused flag; resume is explicit. Guarded switching does not migrate data or repair links tied to the other dataset.

| Control | AWS | GCP |
| --- | --- | --- |
| Enabled | On-demand Lambda; supported small reservation or documented account-unreserved fallback | Request-based automatic min0/max1 |
| Pause | Reserved concurrency0; Function URL HTTP429 | MANUAL instances0; normal URL unavailable, typically503 |
| Resume | Restore reviewed enabled concurrency | AUTOMATIC min0/max1; clear manual-zero override |
| Retain | Table/index, parameters, image, role/logs, state | Firestore, secrets, image, identity, URL/budget, state |

The observed AWS regional concurrency quota is 10 and initial reserved_concurrency=-1 uses that shared pool; it is not a dedicated one-request or spending limit. Review traffic-tag-only GCP URLs before claiming every endpoint offline. Use separate protected teardown for deletion; never delete a URL/database or disable billing just to pause. [AWS deactivation](https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html), [Cloud Run manual scaling](https://docs.cloud.google.com/run/docs/configuring/services/manual-scaling).

## Deploy and validate

AWS central deploy runs native bootstrap/deploy stages followed by read-only smoke checks when enabled. A full tenant workflow requires an explicit selection and current credentials. Native AWS stages are preflight, bootstrap, deploy, pause, resume and status. GCP central deploy builds Dockerfile.gcp, runs pinned Firestore emulator acceptance and binds validation/promotion to the same local image ID before native all. --skip-build --local-image explicitly uses an already-built/prevalidated image and skips that local emulator check. Provider scripts and Terraform roots remain independent.

Run application tests, Terraform validation and the provider's image/emulator checks before promotion. Docker must be running for local builds. Lambda and Cloud Run use distinct runtime Dockerfiles. CI does not establish account/service/IAM access.

After enabling, check public pages, denied manager access, fictional intake/tracking, cross-key denial, private-note isolation, replies/reopening and a concurrent version conflict. Verify persistence independently through the selected native SDK. Cleanup must target only exact matching synthetic IDs with appropriate preconditions. Do not enumerate real records to demonstrate a rollout.

## Monitor and stop

Use native Lambda/CloudWatch for AWS, and Cloud Run/Cloud Monitoring/Logging for GCP. For the optional local Prometheus/Grafana integration:

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-start --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-stop --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-start --project YOUR-GCP-PROJECT-ID
.\.venv\Scripts\python.exe scripts/cloud.py gcp monitor-stop --project YOUR-GCP-PROJECT-ID
```

Start only the selected active provider's local monitoring. It scrapes on a 300-second interval; requests still consume cloud usage. Pause stops local cloud monitoring. No cloud Prometheus/Grafana servers are provisioned. Process counters are not a durable global concern queue.

Local kind uses isolated credentials/context and fictional SQLite data. Its stop deletes only the verified owned cluster/PVC; Compose stop retains real data volumes. Neither requires starting a cloud provider. See [Kubernetes](KUBERNETES.md).

Double-click STOP_SERVICES.cmd or run scripts/stop_services.py to stop local workloads and independently pause both recorded cloud deployments. Use --provider aws --profile ticketpilot for AWS only, --provider gcp for GCP only, or --local-only to contact neither cloud. An expired login is reported as a failure; it does not block the independent other-provider attempt. Inspect each result; retained data/storage can still incur costs. An already-off Docker engine stays off.

## Costs, state and rollback

USD 10/month is an alert target; AWS's reported USD 100 credits and GCP's remaining trial balance are separate. Confirm gross spend, credit expiry, retained storage and log retention. Alerts may lag and do not cap spending. AWS budget email is explicit local opt-in; never guess a recipient or mark it installed before checking. Do not upgrade plans or buy commitments automatically.

Preserve all four states: infra/bootstrap, infra/aws, infra/gcp/bootstrap, infra/gcp/app. State/generated variables/plans, backups, credentials and detailed reports remain private/ignored. State is not interchangeable. Retain the accepted image digest before changes; rollback needs its compatible infrastructure/settings and fresh synthetic acceptance.

If public behavior fails, pause the target first, preserve records and review logs/digest/settings. Dataset migration, tenant onboarding and notification delivery remain separate authorized work. See [portability](CLOUD_PORTABILITY.md), [AWS](ARCHITECTURE_AWS.md) and [GCP](ARCHITECTURE_GCP.md).

## Inspect Terraform directly

The shared scripts run init, save a plan, inspect its JSON for permitted resources/actions, then apply that exact plan. They reject deletion/replacement and paid AI. Terraform manages infrastructure; Docker builds application images. Secret values are uploaded outside state.

After one scripted deployment, inspect each native root using its existing private settings/state (Terraform must be on PATH, or use .tools/terraform.exe on this PC). Use the Terraform-compatible profile reported by scripts/deploy_aws.py --stage preflight, including its account-identity check; the helper prefers an existing ticketpilot-terraform bridge instead of assuming the browser-login profile works directly with the Terraform provider:

```powershell
$env:AWS_PROFILE = "ticketpilot-terraform" # use the validated Terraform profile reported by native preflight
terraform -chdir=infra/bootstrap init -lockfile=readonly
terraform -chdir=infra/bootstrap plan -var-file=terraform.tfvars
terraform -chdir=infra/aws init -lockfile=readonly
terraform -chdir=infra/aws plan -var-file=terraform.tfvars
terraform -chdir=infra/gcp/bootstrap init -lockfile=readonly
terraform -chdir=infra/gcp/bootstrap plan -var-file=ticketpilot.generated.tfvars
terraform -chdir=infra/gcp/app init -lockfile=readonly
terraform -chdir=infra/gcp/app plan -var-file=ticketpilot.generated.tfvars
```

GCP uses ADC and requires renewed login before those plans can refresh. Check the generated file name in each root; do not substitute empty values or recreate state. Use central pause/resume for the reviewed single-purpose changes. Private local states are appropriate for this single-operator demo; a team deployment needs separately secured, locked remote state per provider before enabling hosted Terraform promotion.
