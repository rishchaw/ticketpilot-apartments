# Deploy TicketPilot to AWS

For the existing installation use **AWS controls → Redeploy current code**. The last recorded AWS release includes tenant login and eight provisioned accounts. It was paused after the image update. Live tenant sign-in on this release still needs an explicit resume and acceptance check. See the [beginner redeploy and monitoring guide](OPERATIONS_QUICKSTART.md) and [deployment evidence](DEPLOYMENT_STATUS.md).

## Architecture and prerequisites

Use AWS Singapore (ap-southeast-1) for Lambda, ECR, DynamoDB, SSM parameters and logs. The application is one modular FastAPI deployment with a Lambda/Mangum runtime wrapper, DynamoDB on-demand persistence and provider-native identity/secrets/monitoring. Keep paid AI disabled. See [AWS architecture and rationale](ARCHITECTURE_AWS.md), [portability](CLOUD_PORTABILITY.md) and [provider operations](PROVIDER_OPERATIONS.md).

Have AWS CLI v2, Terraform, Docker Desktop with Linux containers and the existing Python environment/requirements-dev.txt available. Keep a working environment and private .env instead of regenerating credentials. New local setup uses scripts/setup_local.py, which must preserve existing local configuration. Docker must run for builds; renewing AWS login alone must not start GCP or monitoring.

```powershell
aws login --profile ticketpilot
.\.venv\Scripts\python.exe scripts/preflight_aws.py --profile ticketpilot --region ap-southeast-1
```

Read-only identity/service success does not establish every create/pass-role permission. Inspect exact failures rather than widening permissions or upgrading the plan automatically. Use browser credentials, not long-lived keys pasted into chat/source. If a separate Terraform-compatible local profile is needed, configure it privately and supply --terraform-profile; do not publish exported credentials.

## Shared lifecycle entry point

Run from the standalone repository root:

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py --help
.\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot
```

Central deploy builds the Lambda image unless explicitly reusing an accepted image with --skip-build/--local-image, then runs native bootstrap/deploy and apartment acceptance. The native implementation is scripts/deploy_aws.py with preflight, bootstrap, deploy, pause, resume and status stages. The old deploy_aws.ps1 is a legacy path; use the central/native Python lifecycle for the new guards/settings. Check current --help for options.

Deploy/resume changes cloud resources and requires the exclusive-provider guard. GCP was enabled on November 19. Pause it and verify its state before enabling AWS. For the narrow recorded-paused case, --confirm-other-offline is explicit operator attestation plus fresh expected unavailable HTTP results at every known URL. It cannot override authenticated active/traffic-tagged state or a reachable endpoint. Do not delete a record or bypass a failed pause to satisfy this guard. [Operations](PROVIDER_OPERATIONS.md) explains switching and its data boundary.

The two AWS Terraform roots have independent state:

- infra/bootstrap: ECR repository/retention and optional budget metadata where configured.
- infra/aws: Lambda/Function URL, DynamoDB table/index, execution role and short-retention logs.

Images use Dockerfile.lambda, Linux/amd64 and Lambda-compatible manifest settings. The helper pushes to same-region ECR and deploys an immutable digest. It preserves matching existing secrets and uploads initial values outside Terraform state. ADMIN_TOKEN and METRICS_TOKEN resolve through Standard SecureString names /ticketpilot-aws/admin-token and /ticketpilot-aws/metrics-token. Do not put their values in Terraform variables, build arguments, public reports or screenshots.

The reviewed table/index mode is PAY_PER_REQUEST. Versioned conditional writes reject stale manager/tenant updates; bounded queue queries use the recent-tickets GSI. Existing records and building notices must be preserved. An absent credential/API permission is not evidence that a table is absent. Do not apply new empty state over existing infrastructure.

## Concurrency, pause and cost controls

The observed account concurrency quota is 10, so enabled reserved_concurrency=-1 uses the shared/unreserved regional pool. This is not a dedicated per-function limit of one. A small reservation is selected only if the quota permits it; the deployment report must record the actual fallback. Reserved concurrency is different from paid provisioned concurrency, which is not enabled here. Any configured DynamoDB request maxima are best-effort throttling controls, not billing caps.

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws pause --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws resume --profile ticketpilot
```

Pause sets reserved concurrency zero and verifies the Function URL's expected HTTP429 response; resume restores the reviewed enabled setting after the exclusive guard. The URL, table/index, parameters, image, identity/logs and state remain. Normal deployment preserves a saved paused state. Deleting/recreating a Function URL changes its address, so deletion is not the routine stop mechanism. [AWS deactivation](https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html), [reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html).

USD 10/month is an alert target, not a hard cap. Budget email is optional local input through --budget-alert-email; do not guess a recipient or mark notifications installed before checking. Free-plan credits/expiry and service allowances are account-specific. Check gross cost as well as the credit balance. On-demand requests differ from provisioned free-capacity allowances. ECR/database storage, logs and KMS/API use can still consume credit while compute is idle. No automatic plan upgrade, paid capacity purchase, NAT gateway, VM, load balancer, RDS/EKS or hosted monitoring workspace is required. [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/), [SSM pricing](https://aws.amazon.com/systems-manager/pricing/), [ECR pricing](https://aws.amazon.com/ecr/pricing/).

## Acceptance after a completed apply

A source change, CI run or successful apply alone is not full deployed acceptance. Record the exact image digest, URL, effective concurrency, storage mode and AI-off setting. Check /health, /tenant, /manager and the expected apartment configuration before publishing a link.

The cloud acceptance must use fictional concerns and check manager denial without a token, per-concern tracking/cross-key denial, manager-note isolation, tenant-visible replies/reopening and one-success/one-conflict version updates. Verify persistence independently through DynamoDB by exact synthetic IDs. Cleanup must match only those IDs/content with appropriate preconditions. Do not list real private queues or overwrite a building notice merely to run acceptance.

The public Function URL reaches FastAPI. The tenant router derives the unit from the signed-in account and requires the tracking key for private concern access. Manager operations verify the separate manager code. DynamoDB recent-index updates are eventually consistent; direct key reads verify persistence separately. Keep manager codes/tracking links private.

The older public smoke check covers pages/access denial and legacy retrieval; it does not replace private apartment writes/persistence checks. Local Lambda emulation and credential-free CI also remain separate evidence from live account access. See [CI/CD](CI_CD.md) and [validation](VALIDATION.md).

## Monitoring and optional AI

Use Lambda/CloudWatch for deployed invocation/error/throttle/duration metrics and execution logs. Lambda native invocation metrics are published without an additional metric charge; logs, dashboards and API retrieval may cost. [Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html).

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-start --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-stop --profile ticketpilot
```

Monitoring is opt-in and local: Prometheus/Grafana authenticate a selected-cloud scrape every 300 seconds. Deploy/resume never starts it automatically; pause stops it and retains local volumes. Requests still consume usage. Local counters reset per Lambda environment and are not global queue/lifetime totals. The optional older CloudWatch exporter is another local API-polling integration with possible charges.

Docker/kind provide a separate fictional-data Kubernetes demonstration with no EKS deployment. Its hosted CI acceptance is recorded independently; the interrupted PC attempt is not claimed as passed. [Kubernetes guide](KUBERNETES.md).

Paid AI stays off in the apartment rollout. Optional Bedrock generation remains in the original /demo flow and requires deliberate model/region/access/cost review before enable_bedrock=true. It is not required to deploy the concern tracker. CPU inference and cited local retrieval continue without paid model calls.

## Stop, troubleshoot and protect data

Double-click STOP_SERVICES.cmd or run scripts/stop_services.py to stop local workloads and independently pause both recorded cloud deployments. Use --provider aws --profile ticketpilot for AWS only, --provider gcp for GCP only, or --local-only to contact neither cloud. An expired login is reported as a failure; it does not block the independent other-provider attempt. Inspect each result; retained data/storage can still incur costs. An already-off Docker engine stays off.

For credential expiry, renew browser login and preserve the selected profile/state. For denied writes, inspect the exact action/resource before changing IAM. For image initialization, inspect CloudWatch logs and the required SSM metadata/runtime permissions without printing values. For public URL403, verify both URL invoke permissions; paused429 is expected. For unchanged behavior, compare the deployed digest/settings rather than just source files.

Full destruction is separate from pause and requires explicit protection/data-retention review. Export needed records privately before disabling table protection. Preserve state, generated variables and the last accepted digest; pass the same private variable files when planning cleanup. The ECR bootstrap can delete its images, and SSM parameters managed outside Terraform are a separate explicit cleanup decision. Never delete records, billing, URLs or state merely to stop idle compute. Provider switching does not migrate data.
