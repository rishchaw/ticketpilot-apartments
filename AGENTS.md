# Operator controls and validation - November 19, 2026

Use TICKETPILOT.cmd and docs/OPERATIONS_QUICKSTART.md for explicit provider Start/Stop/Status/Update and local tools. Menu startup and --check must not contact providers or Docker. Keep both clouds and real local services paused under the current stop request. GCP still needs its explicit authenticated-image Prepare workflow with --leave-paused and separate native account provisioning before Start is permitted. Do not bypass release/account guards or reset tenant passwords during lifecycle operations.

Local regression passed435tests. First tenant-auth hosted run44317754504 passed4jobs but failed its single-environment Lambda emulator invocation; the harness correction and actual image acceptance passed locally. New hosted verification remains pending; read the current Actions result before claiming it green. See docs/DEPLOYMENT_STATUS.md. The RAG guide documents IT-demo retrieval/optional generation versus the apartment portal's fixed bilingual guidance; do not claim building-document RAG or enable paid AI automatically.

# Tenant login rollout and AWS pause - November 18, 2026

The latest request authorizes exactly eight tenant accounts for units1A,1B,2A,2B,2C,3A,3B,3C. Authenticated AWS image sha256:722722a0310ebf824b0740f58d21092f643c213b9132f4c23fe3661e92ca1106 is applied while paused. Eight native DynamoDB accounts and private handouts are provisioned. Local full/browser/Lambda-emulator acceptance passed; no external hosted sign-in acceptance was run because the cloud remains paused. AWS has been paused with reserved concurrency0/HTTP429 following the user stop attempt. Keep AWS, GCP and local services stopped after this work. Isolated fictional local validation may run temporarily and must clean up. Do not resume cloud services merely to test.

Use private .secrets/tenant-credentials.json and individual .secrets/tenant-logins/*.txt handouts; never publish passwords/hashes/cookies/CSRF, put them in Terraform, or send tenant messages. Accounts are native backend records with Argon2id and persisted opaque sessions. No public signup. Existing unowned concerns remain manager-only; never auto-assign by unit. Keep tenant_id stable for password resets; a new occupant needs a deliberate new identity policy. See docs/TENANT_ACCESS.md.

# AWS deployed and verified - November 17, 2026

Final readback November18: AWS public health200 (DynamoDB, paid AI off), GCP503. Source commit30cd12a passed all five hosted CI jobs in run44088138007. Optional local AWS Prometheus/Grafana acceptance passed and monitoring was stopped. Preserve AWS active/GCP paused under the latest request; credential expiry does not stop the deployed runtime.


The user's new request authorizes a cost-conscious AWS deployment using the verified existing account and profile `ticketpilot` in Singapore (`ap-southeast-1`). This supersedes historical AWS activation-blocked guidance below. Browser authentication/account checks succeeded: Free plan `ACTIVE`, USD 100 in credits, recorded expiration `2027-05-17`. Completed Terraform apply, HTTPS health, live apartment acceptance and independent exact-ID DynamoDB reads passed. AWS pause429/resume200 passed; leave AWS active under the new request. The accepted image digest is recorded privately and in deployment status. No AWS MCP tools are exposed here, so use the documented CLI fallback and official/local skills. Never upgrade the plan automatically or enable paid AI by default.

The initial regional Lambda concurrency quota is 10. Enabled `reserved_concurrency=-1` uses the shared/unreserved pool and supplies no dedicated per-function cap; pause uses zero. Preserve native PAY_PER_REQUEST DynamoDB, Standard SSM, ECR, CloudWatch and separate AWS states. Budget email is explicit local opt-in; never guess a recipient. Keep real account/project/billing IDs, emails, values, state/plans and detailed reports out of tracked examples.

Keep GCP paused and retained; its recorded CLI/ADC session is expired. The central `scripts/cloud.py` guard prevents enabling another configured active/unknown provider. Its narrow `--confirm-other-offline` exception requires explicit operator attestation, recorded paused state and fresh expected unavailable responses at all known URLs, and cannot override authenticated active/tagged state. Renewing credentials does not authorize resuming GCP. Default central GCP deploy builds and emulator-validates its image; `--skip-build` is an explicit prevalidated-image path. Do not infer data migration from provider switching.

`STOP_SERVICES.cmd`/`scripts/stop_services.py` now independently pauses both recorded providers; --provider selects one, --local-only neither. Report expired-login failures independently. Prometheus/Grafana are optional local tooling; monitoring starts only on request and stops on pause. Real records and state remain protected. Local kind stays isolated/fictional and is cleaned up after validation. Read `docs/PROVIDER_OPERATIONS.md`, `docs/CLOUD_PORTABILITY.md` and provider architecture guides before changing operations.

# User-requested operational pause - November 17, 2026

The user requested that TicketPilot be taken offline temporarily to save costs. Cloud Run is paused with Terraform-managed paused=true (manual scaling, zero instances), and both known service URLs returned HTTP 503. Local Compose app/Prometheus/Grafana containers are stopped with their volumes preserved. Keep the GCP site and local services stopped until the user requests a restart. Local validation may temporarily start an isolated fictional-data Kubernetes demonstration, but clean it up and leave it stopped afterward.

Use scripts/deploy_gcp.py --stage pause or --stage resume with the existing project, region, state and private generated variables. Deploy/all preserve the saved pause state. Do not recreate state, delete real data, disable billing or upgrade plans to stop the site. Retained Firestore, images and secrets may still incur storage costs. AWS remains separately blocked by account activation.

Kubernetes work belongs to a local kind portfolio demo only: cluster ticketpilot-portfolio, namespace ticketpilot-demo, isolated .tools/kubernetes/kubeconfig and .secrets/kubernetes-demo.json. Never use a global kubectl context or mount real tenant data/cloud credentials. Its stop command deletes only the verified owned demo cluster and fictional PVC data. Kubernetes acceptance and cleanup passed in hosted CI run 44023034882 for source commit 4401872. Do not claim the interrupted PC attempt completed. Google CLI/ADC reauthentication is now needed before cloud changes (invalid_rapt); both public URLs still returned HTTP 503. Do not resume services merely to renew login. See docs/KUBERNETES.md.

# GCP proof of concept deployed - November 16, 2026

The user authorized a separate GCP deployment path in Singapore (`asia-southeast1`) with Terraform and a USD 10/month target using the existing free trial. Use named Google Cloud CLI configuration `ticketpilot-gcp` plus ADC; no GCP MCP connection is configured. Use browser sign-in and attached runtime identities, never generate long-lived service-account keys. Keep actual project/billing IDs and account emails out of tracked defaults/examples. Do not upgrade the billing plan automatically.

Read `docs/DEPLOYMENT_STATUS.md` and `docs/GCP_DEPLOYMENT.md` before GCP changes. Cloud Run deployment and synthetic tenant/manager acceptance are verified, with independent Firestore SDK persistence checks. Use the recorded live revision/digest and current reports when assessing deployed behavior; a source change alone is not a new deployment. Hosted CI run 43913020484 passed all four jobs for commit 866742c; the GCP artifact includes only approved credential-free reports. Read current Actions results before assuming later commits have passed. Keep AWS roots and local data intact. AWS activation restrictions below apply to AWS provisioning, not the separately authorized GCP work.

Use separate `infra/gcp/bootstrap` and `infra/gcp/app` states. Cloud Run uses request-based billing, minimum 0/maximum 1, Firestore for durable records, manual manager refresh and a small queue. Inspect existing Firestore database metadata before creation; do not replace an existing database. Keep secrets out of Terraform values/state, use digest images, preserve the active image from cleanup, and leave hosted AI disabled. The installed USD 10 gross-cost alert budget is not a spending cap. Prometheus/Grafana remain local. Use only fictional concerns for automated checks, verify exact synthetic IDs before cleanup, and preserve existing tenant records/notices.

# AWS MCP reconnection authorized - November 11, 2026

The user explicitly requested restoration of the AWS MCP connection. Client configuration is restored using AWS profile `ticketpilot`; AWS operations should target Singapore (`ap-southeast-1`). The user approved a fresh browser login, which completed successfully. STS verified the expected account identity using profile `ticketpilot`. AWS MCP configuration is restored, but tools are not yet exposed in this chat; reload the client before checking live MCP access.

AWS deployment remains paused because account activation/phone verification is unresolved. Do not provision AWS resources, upgrade the AWS plan, or enable Bedrock until activation is confirmed and the deployment prerequisites are checked. Local Docker, Prometheus, Grafana, and retrieval-only development may continue.

# Project purpose

TicketPilot is now an apartment concern tracker for the family's eight units. Tenants submit through a mobile link in English/Filipino; the user's mother manages the queue instead of searching Messenger chats. Read `docs/APARTMENT_USE_CASE.md` before changing tenant workflows. `/` and `/tenant` are the apartment portal, `/manager` is manager-only, and `/demo` preserves the old IT example. Do not use the old classifier's scores as apartment-domain evidence. Keep tenant/private manager data separate, preserve existing records, and never invent building policies or send messages to tenants without explicit authorization.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions â€” it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- For any AWS task or question â€” building, configuring, migrating, debugging,
  or operating a service, writing SDK code, authoring CDK/CloudFormation, or
  answering how a service works â€” first call `aws___search_documentation` with
  topic `agent_skills` and load the matching skill with `aws___retrieve_skill`.
  Do this even when you believe you know the answer: skills carry current
  service behavior that your training may not. Prefer the skill's guidance over
  general knowledge. Skip it only for work that does not involve AWS.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- Before reporting a count, a total, or that something does not exist, read
  every page of the results and search every Region and scope where it could
  be. If you could not, say the result is partial and name what you checked.
- To say what a system currently does, read what the runtime uses: the
  completed deployment, the alias or version that is invoked, the template the
  stack is running. A newer stored version, a draft, or a description field is
  not evidence of live behavior.
- Present a cause as confirmed only if data, configuration, or logs you read
  show it. Label anything else as unverified, and say what you would check
  next.
- Before you interpret the records that show a failure, such as error log
  lines, failed executions, or table items, read one of them whole, with
  every field. Don't truncate messages or select fields in your own code
  until you have.
- When an error says a value was undefined, null, empty, or missing, find
  the input, query result, or item that supplied that value. If the account
  shows why it was empty, such as no item matching the key, read that
  before you call the cause unverified.
- When a field in a record you read explains the result, such as an error
  counter, an empty array, a null, or a state value, name the field and its
  exact value in the answer, and say which record it came from.
- When the user asks a specific question or names a suspected cause, confirm
  or rule out each cause they raised, and do not offer alternatives your evidence
  does not support.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Before you conclude

- Before deciding the AWS account can't hold what the request asks for,
  look. List the places it could live, such as S3 buckets, databases, and
  log groups, and read what is there.
- Don't conclude that records are missing from metadata, such as a
  creation date or a stored-bytes count, or from one query that failed or
  came back empty. Read the records another way, across the full time
  range, before reporting them absent.
- A tool's own error is evidence. If a call the answer depends on fails
  with expired or missing credentials or AccessDenied, report that error
  and what it blocks, and don't overrule it with another check. Searching
  other Regions is for finding resources, not for retrying an auth error.
  Retry throttling with backoff before you report it.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->
