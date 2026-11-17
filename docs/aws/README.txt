TICKETPILOT APARTMENTS - AWS DEPLOYMENT
=====================================

Documentation updated: November 17, 2026 (Asia/Manila)
Status: PREPARED; CLOUD DEPLOYMENT BLOCKED BY ACCOUNT ACTIVATION.

This guide belongs to the standalone ticketpilot-aws project. Run all commands
below from its repository root, not from this docs/aws directory.

CURRENT STATUS
--------------
AWS account/phone verification is unresolved. The last recorded service checks
rejected Lambda and DynamoDB with SubscriptionRequiredException:
"The AWS Access Key Id needs a subscription for the service."

Earlier successful sign-in/STS checks do not establish account activation or
deployment permission. No working AWS application URL or successful AWS
tenant/manager acceptance check has been recorded. Local Docker/Lambda emulation
and credential-free CI have passed; those results do not prove cloud deployment.
This documentation change does not retry AWS access or provision resources.

Configuration to retain:
  AWS CLI profile: ticketpilot
  Deployment region: ap-southeast-1 (Singapore)
  Optional Bedrock: disabled
  AWS_DEPLOY_ENABLED repository variable: false
  Separate GCP deployment/pause status: see docs/gcp/README.txt

AWS MCP configuration was restored previously, but live tool access must be
verified in the active client after activation. MCP and local CLI/Terraform
authentication are separate checks.

PREPARED ARCHITECTURE AND FILES
------------------------------
The same FastAPI apartment portal is packaged for Lambda with DynamoDB storage.
The existing Terraform configuration defines the following planned resources:
  infra/bootstrap/       Private ECR image repository.
  infra/aws/             Lambda HTTPS Function URL, DynamoDB, runtime IAM and logs.
  Dockerfile.lambda      Linux/amd64 Lambda container.
  scripts/deploy_aws.ps1  Initial deployment helper.
  scripts/preflight_aws.py
                         Read-only account/service checks; fails closed.

ADMIN_TOKEN and METRICS_TOKEN are local private configuration names. The helper
uploads their values outside Terraform to SSM SecureString parameters. Never
paste their values, credentials or Terraform state into this README or GitHub.

AFTER AWS SUPPORT CONFIRMS ACTIVATION
------------------------------------
1. Confirm the actual plan, remaining credits, expiry and required service access
   in the AWS console. Keep the existing plan; do not upgrade it automatically.

2. Have AWS CLI v2, Docker Desktop, Terraform and Python available. Use the
   existing .venv with requirements-dev.txt installed; do not recreate a working
   environment. Start Docker Desktop.

3. Renew browser login and check identity and required service read access:

     aws login --profile ticketpilot
     aws sts get-caller-identity --profile ticketpilot --region ap-southeast-1
     .\.venv\Scripts\python.exe scripts/preflight_aws.py --profile ticketpilot --region ap-southeast-1

   Stop if activation/subscription/authentication checks fail. Successful read
   checks do not prove create permissions. See docs/AWS_CONNECTION.md for expired
   sessions, the credential-process bridge and optional MCP verification.

4. Review the deployment script and Terraform configuration. Once activation,
   service access, permissions and costs are confirmed, run:

     .\scripts\deploy_aws.ps1 -Profile ticketpilot -Region ap-southeast-1

   This command changes cloud resources. It uploads app tokens, applies the ECR
   bootstrap, builds/pushes the Lambda image, then applies the application using
   an immutable digest. Review both Terraform plans before approving them.
   Keep enable_bedrock=false during the initial deployment.

5. Read the HTTPS URL after a successful apply:

     terraform -chdir=infra/aws output -raw service_url

   Open /tenant and /manager on that URL. The manager access code is the private
   ADMIN_TOKEN from local .env. Tenant tracking links are private per concern.

POST-DEPLOYMENT ACCEPTANCE
-------------------------
Run the public smoke check, replacing the example URL with the Terraform output:

  .\.venv\Scripts\python.exe scripts/smoke_aws.py https://YOUR-SERVICE.lambda-url.ap-southeast-1.on.aws/

Then follow docs/AWS_DEPLOYMENT.md for the authorized apartment acceptance:
fictional concern submission, manager updates, cross-key denial, private-note
isolation, reopening and DynamoDB persistence. The public smoke check does not
replace these write/persistence checks. Preserve real records and notices.

COSTS, MONITORING AND CI/CD
-------------------------
The source retains optional Bedrock RAG for the original IT demo at /demo.
Tenant concerns do not invoke Bedrock. Keep paid generation disabled until its
account access and costs are deliberately reviewed.

Prometheus and Grafana remain local Docker services. Optional CloudWatch exporter
setup follows deployment and may consume API allowances. Local app counters are
not a fleet-wide cloud concern queue or lifetime totals.

GitHub CI tests the application, local containers and Terraform without cloud
credentials. GHCR container release and manual AWS promotion are separate.
Promotion stays disabled until activation, initial deployment, OIDC and remote
Terraform state are configured. See docs/CI_CD.md.

Preserve both Terraform states privately. Costs depend on actual account
allowances and usage; this project does not promise perpetual free hosting.
Review docs/AWS_DEPLOYMENT.md before any cleanup: deleting the app stack can
delete tenant data after protection is explicitly disabled.

LOCAL OFFLINE OPERATION AND KUBERNETES
--------------------------------------
For a combined stop from the repository root:

  .\.venv\Scripts\python.exe scripts/stop_services.py

This stops Compose while preserving volumes, removes only an owned disposable
kind demo when Docker is available, and pauses existing GCP through Terraform.
The project comes from the private local deployment record; use --project
YOUR-PROJECT-ID if needed. --local-only skips GCP. An already-off Docker engine
stays off and cluster deletion is skipped; cloud pause is still attempted.
Check the summary for errors/skipped cloud work. Real cloud data/images/secrets
and Compose volumes remain; only kind's fictional demo data is disposable.

AWS provisioning remains blocked; the Kubernetes demonstration does not activate
AWS or create EKS resources. It runs in a separate local kind cluster with
private demo-only credentials and fictional data. Read docs/KUBERNETES.md for
start/status/forward/stop commands and current validation evidence. The helper's
stop operation deletes only its owned disposable cluster and demo data, keeping
real Compose volumes, GCP records and AWS configuration intact.

For the existing local Compose app/Prometheus/Grafana, retain data while stopping:

  docker compose --profile local stop

To resume that local stack when wanted:

  docker compose --profile local up -d

Neither command changes a cloud deployment. Use the GCP pause/resume stages in
docs/gcp/README.txt for the separate Cloud Run service; retained storage/secrets
can still cost credits, and its USD 10 alert budget is not a spending cap. Keep
AWS deployment disabled until account activation and service checks succeed.

UPDATE THIS README WHEN AWS BECOMES AVAILABLE
--------------------------------------------
Record the activation/verification date, identity/profile and service checks
without credential values; deployed URL, region and image digest; actual
Terraform results; apartment acceptance/persistence evidence; installed cost
controls; and the verified MCP/CI/CD status. Update docs/DEPLOYMENT_STATUS.md too.
Replace the blocked status only after deployment and cloud checks succeed.

RELATED PROJECT FILES (PATHS FROM REPOSITORY ROOT)
------------------------------------------------
README.md
docs/DEPLOYMENT_STATUS.md
docs/AWS_CONNECTION.md
docs/AWS_DEPLOYMENT.md
docs/CI_CD.md
docs/gcp/README.txt
docs/KUBERNETES.md

Windows shortcut: double-click STOP_SERVICES.cmd in the repository root to run the same stop helper. If Google authentication has expired, renew CLI and ADC browser sign-in before future cloud changes. The already paused site stays paused; local Kubernetes does not require Google login.
