TICKETPILOT APARTMENTS - AWS
===========================
Checkpoint: November 18, 2026 (Asia/Manila).
Run commands from the standalone ticketpilot-aws repository root.

STATUS
------
The authenticated tenant release (digest prefix 722722a0) is deployed in AWS
Singapore and intentionally paused: Function URL HTTP429. Eight approved unit
accounts and individual private handouts are ready. The 312 local tests, real
browser acceptance and Lambda emulator passed. No hosted tenant login test was
run while the user's stop was maintained. No plan upgrade or paid AI enablement.

Retained tenant URL: https://f76rtnytvzpyuw53oueg5il2by0gbpzc.lambda-url.ap-southeast-1.on.aws/tenant
It remains unavailable until an explicit verified resume. The login page is
public after resume; the portal/configuration/concern APIs require authorization.

Account units: 1A,1B,2A,2B,2C,3A,3B,3C. Operator inventory is privately stored at
.secrets/tenant-credentials.json; per-unit handouts are under .secrets/tenant-logins/.
Share each handout privately with its assigned resident; never publish passwords
or the whole inventory. See docs/TENANT_ACCESS.md for onboarding and revocation,
and docs/DEPLOYMENT_STATUS.md for final image/runtime evidence.

ARCHITECTURE AND RATIONALE
--------------------------
Lambda container/Function URL; DynamoDB PAY_PER_REQUEST table/recent-record index;
Standard SSM SecureString tokens; ECR digest images; scoped execution role;
CloudWatch native metrics/logs. Eight-account admission, password hashes, durable
sessions and revocation use private rows in the existing DynamoDB table. No
additional hosted identity service is added. Terraform: infra/bootstrap and infra/aws.
One modular FastAPI domain/UI is shared with GCP; its Lambda runtime wrapper,
SDK adapters, identities and Terraform remain native to AWS. AI stays off;
optional Bedrock code is preserved for a deliberate later experiment.
Diagrams/rationale: docs/ARCHITECTURE_AWS.md and docs/CLOUD_PORTABILITY.md.

PREPARE AUTHENTICATION AND TOOLS
--------------------------------
Use AWS CLI v2, Terraform, the existing Python environment and Docker Desktop
for local image builds. Keep the working .venv; requirements-dev.txt supplies
local validation dependencies. Profile ticketpilot; region ap-southeast-1.

  aws login --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/preflight_aws.py --profile ticketpilot --region ap-southeast-1

Identity login alone does not prove every create permission. No AWS MCP tools
are exposed in the current session, so deployment uses the CLI fallback. Stop on
service/authentication errors; do not upgrade the plan automatically. No static
keys need to be pasted into chat or stored in source. MCP is optional/separate.
ADMIN_TOKEN and METRICS_TOKEN stay private; SSM names are
/ticketpilot-aws/admin-token and /ticketpilot-aws/metrics-token. Values upload
outside Terraform state. Preserve matching cloud tokens unless rotating deliberately.

CENTRAL DEPLOYMENT AND OPERATIONS
---------------------------------
The final interface is provider first, action second:

  .\.venv\Scripts\python.exe scripts/cloud.py --help
  .\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws pause --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws resume --profile ticketpilot

Deploy builds unless --skip-build is supplied, then runs native bootstrap/deploy
and apartment acceptance. Native helper: scripts/deploy_aws.py, stages preflight,
bootstrap, deploy, pause, resume, status. The old PowerShell entry remains legacy;
use the central/native Python paths for the streamlined lifecycle.

Deploy/resume CHANGE CLOUD RESOURCES. The exclusive guard blocks another active
or unknown configured provider. A narrow --confirm-other-offline exception needs
explicit operator attestation, recorded paused=true and fresh expected unavailable
HTTP results at every known URL when authenticated reads fail. It cannot override
an authenticated active or traffic-tagged deployment. An auth failure is not
successful authenticated verification. See docs/PROVIDER_OPERATIONS.md.

The tenant-authenticated image and eight-account readiness must be verified
before resume; do not enable an older image that lacks login protection.
Pause sets reserved concurrency 0 and verifies Function URL HTTP 429; resume restores
the reviewed enabled setting. Normal deploy preserves the saved pause state.
Data/index, parameters, images, identity and state remain. The initial regional concurrency quota is 10,
so reserved_concurrency=-1 uses the shared/unreserved pool instead of a dedicated
reservation. It is not a one-request or billing ceiling. Provider-specific Terraform and private generated
settings remain separate; never apply empty state over existing resources.

VALIDATION, MONITORING AND COST
-------------------------------
Before promotion, run application tests, Terraform validation and Lambda emulator
checks for the exact image. After apply, record URL/digest and validate independent
DynamoDB persistence, tracking privacy, manager-note isolation, replies/reopening
and version conflicts with fictional records plus guarded cleanup. CI does not
prove current cloud IAM/account access. See docs/AWS_DEPLOYMENT.md for details.

Use Lambda/CloudWatch for deployed metrics/logs. Monitoring is optional/local:

  .\.venv\Scripts\python.exe scripts/cloud.py aws monitor-start --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws monitor-stop --profile ticketpilot

It starts only local Prometheus/Grafana with authenticated 300-second scraping of
the selected active cloud; pause stops it and retains local volumes. Deploy/resume
does not start monitoring automatically. No hosted AWS Grafana/Prometheus tier is
created. Scrapes/API polling still consume usage; process counters are not global
queue totals. Kubernetes remains an isolated local kind exercise, not EKS.

USD 10/month is an alert target, not a cap. Check actual credits, allowances and
expiry in the console. On-demand DynamoDB request billing differs from provisioned
free capacity. Retained ECR/database/logs and KMS/API use can still consume credit.
Optional budget email requires an explicitly supplied local recipient, for example
--budget-alert-email YOUR-EMAIL-ADDRESS; never guess one or claim installed alerts
before checking. No paid-plan upgrade or capacity purchase is automatic.

Double-click STOP_SERVICES.cmd or run scripts/stop_services.py to stop local
workloads and independently pause both recorded providers. --provider aws or
--provider gcp selects one; --local-only contacts neither. Inspect each result:
expired login is a failure, not a verified pause. Real data remains retained.

Pause is not destruction. Review protection/data retention separately before
teardown. Preserve both AWS states, generated .tfvars, accepted digests and private
backups outside Git. Do not delete a URL, database, billing link or state to stop
idle compute. Provider switching does not migrate tenant records or tracking links.

Related: docs/PROVIDER_OPERATIONS.md, docs/ARCHITECTURE_AWS.md,
docs/ARCHITECTURE_GCP.md, docs/CLOUD_PORTABILITY.md, docs/gcp/README.txt,
docs/KUBERNETES.md, docs/CI_CD.md.
