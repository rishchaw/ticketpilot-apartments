TICKETPILOT APARTMENTS - AWS DEPLOYMENT
====================================

Run commands from the repository root containing TICKETPILOT.cmd.
The AWS path deploys the shared FastAPI application to Lambda in Singapore
(ap-southeast-1), with native persistence, identity, secrets and monitoring.

Architecture and deployment details are in docs/ARCHITECTURE_AWS.md and
docs/AWS_DEPLOYMENT.md. Verified images, checks and recorded service state are
summarized in docs/DEPLOYMENT_STATUS.md.

REQUIREMENTS
------------
Install Python 3.11, AWS CLI v2, Terraform and Docker Desktop with a Linux engine.
Use requirements-dev.txt for local validation. Fresh-clone environment setup is
documented in docs/STACK_GUIDE.md. Retained deployments also require their existing
private Terraform state, settings, deployment records and matching secrets.

  aws login --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/preflight_aws.py --profile ticketpilot --region ap-southeast-1

Browser sign-in supplies short-lived CLI credentials. Resource creation and
role-passing permissions are checked during deployment. Keep private credentials
and Terraform profiles outside version control.

DEPLOYMENT
----------
For launcher controls, run .\TICKETPILOT.cmd and choose AWS controls. The central
CLI provides the same provider lifecycle.

  .\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot

Deploy runs the bootstrap and application stages. It builds Dockerfile.lambda
for Linux/amd64, validates the image through the Lambda runtime emulator, pushes
to ECR and applies an immutable image digest. --skip-build --local-image can reuse
an already built image, which must still satisfy the validation requirements.

Terraform roots have independent state.
  infra/bootstrap    ECR and optional budget configuration
  infra/aws          Lambda/Function URL, DynamoDB, execution role and logs

ADMIN_TOKEN and METRICS_TOKEN use Standard SSM SecureString parameters. Secret
values are uploaded outside Terraform state. Password hashes and persisted
sessions use private records in the existing DynamoDB table. Account provisioning
and reset operations are described in docs/TENANT_ACCESS.md.

START AND STOP
--------------
Start resumes the retained image. Redeploy publishes changed code. Deployment
preserves the saved paused setting.

  .\TICKETPILOT.cmd aws start
  .\TICKETPILOT.cmd aws status
  .\TICKETPILOT.cmd aws stop

Pause sets reserved concurrency to zero and verifies Function URL HTTP 429.
Resume restores the reviewed enabled setting. A reported value of -1 uses the
regional shared/unreserved pool and supplies no dedicated per-function ceiling.
Data, accounts, images, parameters, identity and Terraform state are retained.

The central guard checks the other configured provider before deploy/resume.
Its narrow --confirm-other-offline exception requires explicit attestation,
recorded paused state and fresh expected unavailable HTTP at every known URL.
An authenticated active provider remains blocked. See docs/PROVIDER_OPERATIONS.md.

VALIDATION
----------
CI covers application/browser behavior, container monitoring, the Lambda runtime
emulator and Terraform configuration. Live acceptance separately verifies public
access restrictions and selected synthetic tenant/manager workflows, with exact-ID
DynamoDB persistence reads and guarded cleanup.

Routine lifecycle checks use health and anonymous-access checks. Full tenant
workflow acceptance requires --validate-tenant-workflow and current authorized
credentials. The recorded authenticated AWS image passed local/browser/emulator
checks. Hosted sign-in acceptance for that image remains pending.

MONITORING AND COST CONTROLS
---------------------------
CloudWatch provides native invocation, error, throttle, duration and execution-log
views. Optional local Prometheus/Grafana monitor only the selected serving cloud.

  .\.venv\Scripts\python.exe scripts/cloud.py aws monitor-start --profile ticketpilot
  .\.venv\Scripts\python.exe scripts/cloud.py aws monitor-stop --profile ticketpilot

The 300-second authenticated scrape invokes the cloud endpoint. Pause stops local
cloud monitoring and retains its volumes. Process counters reset per execution
environment. Local kind Kubernetes validation is documented in docs/KUBERNETES.md.

Paid AI is disabled by default. The separate IT demo retains CPU classification,
runbook retrieval and an optional Bedrock adapter. See docs/RAG_IMPLEMENTATION.md.

The optional USD 10 email budget requires an explicit recipient through
--budget-alert-email. Alerts warn about spend. Monitor gross cost, account
credits and retained-resource charges independently. Database/image storage,
logs and API usage can incur charges while the application is paused.

STOP_SERVICES.cmd stops local workloads and attempts independent pauses of both
recorded clouds. --provider aws selects AWS, and --local-only skips cloud calls.
Inspect the result for each attempted operation. Teardown requires a separate
review of data retention, resource protection and the matching Terraform states.

Related documentation
  docs/OPERATIONS_QUICKSTART.md
  docs/PROVIDER_OPERATIONS.md
  docs/ARCHITECTURE_AWS.md
  docs/CLOUD_PORTABILITY.md
  docs/TENANT_ACCESS.md
  docs/CI_CD.md
