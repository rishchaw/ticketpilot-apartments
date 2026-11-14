# Deploy TicketPilot AWS

## Account and region

Use your existing AWS Free plan account. Confirm that Lambda, ECR, DynamoDB, Systems Manager Parameter Store, IAM and CloudWatch are available, and inspect credit balance/expiry in AWS Billing. AWS's current Free Tier FAQ says most new customers can sign up without a payment method, but identity checks and plan-specific service restrictions can still apply. A console session by itself does not establish deployment permission.

Keep Lambda, its ECR image, DynamoDB, SSM parameters and logs in Singapore (`ap-southeast-1`). Lambda requires the ECR image in the same region. Optional Nova Micro generation is configured in Sydney, which supports direct regional inference. Singapore model access requires a cross-region profile, which this simple regional-model IAM configuration does not configure automatically.

## First deployment from Windows

The Lambda container uses Python 3.12 on Amazon Linux 2023 with binary wheels to support the current NumPy/scikit-learn dependencies. The local development environment can continue using Python 3.11. Live local checks are documented in [VALIDATION.md](VALIDATION.md).


1. Follow [AWS_CONNECTION.md](AWS_CONNECTION.md) to sign in and configure a local profile.
2. Install Terraform 1.6+ and Docker Desktop. Start Docker Desktop. Python 3.11 is recommended.
3. From the standalone `ticketpilot-aws` folder:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   $env:AWS_PROFILE = 'ticketpilot'
   $env:AWS_REGION = 'ap-southeast-1'
   .\.venv\Scripts\python.exe -m pytest -q
   .\scripts\deploy_aws.ps1
   ```

The script validates local credentials, generates local tokens once, uploads them using Boto3 to `/ticketpilot-aws/admin-token` and `/ticketpilot-aws/metrics-token` as Standard SecureString parameters, and presents two Terraform apply plans. Parameters use the default AWS-managed SSM encryption key. Their values never enter Terraform state, console output or Docker build arguments. SSM parameters are intentionally managed by the upload script, so Terraform destroy does not remove them.

The first stack creates a private ECR repository with immutable tags. The script builds `Dockerfile.lambda` for Linux/amd64 with OCI attestations disabled, pushes a unique timestamp tag, resolves its digest, and passes that digest to the second stack. The app stack creates the Lambda function, public URL and both required URL invoke permissions, a protected provisioned-capacity DynamoDB table/index, a seven-day log group, and a scoped Lambda execution role.

The default does not reserve Lambda concurrency: new Free plan accounts may have a regional limit too low to reserve capacity. If your account quota permits it, set `reserved_concurrency = 1` or `2` in `infra/aws/terraform.tfvars`. This reduces concurrency; it is not a spending cap. No provisioned concurrency, NAT gateway, load balancer, RDS, EKS, or hosted Grafana workspace is created.

Retain both Terraform state files and lock files. State contains infrastructure identifiers and policies, but no token values. Back it up privately. If you later use a shared remote backend, configure access controls and encryption before migrating state.

## Check a completed deployment

These are post-deployment checks, not evidence that deployment has occurred. Check [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for the current account/service-access result. Run them only after both Terraform stacks apply successfully and `service_url` is available.

Use fictional units and concerns for the first cloud verification:

1. Open `service_url` and `/tenant` on the deployed HTTPS address. Check `/health` for `storage_mode: dynamodb`; confirm `/api/apartments/config` has the expected unit labels. The current Terraform configuration uses the application's default building name and units 1-8 unless apartment environment settings are added explicitly.
2. Select English or Filipino, submit a synthetic concern, and save its reference and private tracking link. Confirm the initial status is received. A saved report does not confirm a manager has read it or received a notification.
3. Open `/manager` and use the existing `ADMIN_TOKEN` from your local `.env` as the manager access code. Confirm an unauthenticated request to `/api/apartments/manage/concerns` is denied. Never give tenants the manager access code.
4. Find the concern, acknowledge or resolve it, add a tenant-visible update and a separate fictional private manager note. Reload the tenant's tracking page and confirm that its status and public update persist while the private note does not appear in the tenant response.
5. Confirm that requesting `/api/apartments/concerns/{ticket_id}` without its `X-Ticket-Key` header returns 404. Create a second fictional concern and confirm its key cannot read or reply to the first concern. A unit number or ticket reference alone must not provide access.
6. Reply or reopen the resolved concern from its private tracking page, then refresh the manager queue. Publish a fictional building-wide notice and confirm it appears when a tenant refreshes. Check that the notice includes no private concern details. DynamoDB queue-index updates are eventually consistent; refresh again if a new report or status takes a moment to appear.

The public URL serves the tenant and manager page shells without IAM authentication. Manager API routes still enforce their access code, and tenant tracking requires its per-concern key. Keep tracking links private and out of the Messenger group chat. Prometheus `/metrics` independently requires its metrics Bearer token. Limit initial cloud validation to fictional records; tenant identity verification and live-tenant onboarding remain separate pilot decisions.

The original IT classification/RAG example remains explicitly available at `/demo`. `scripts/smoke_aws.py` checks health, the homepage, that legacy public analysis, and anonymous access denial without owner writes or paid model calls:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_aws.py 'https://YOUR-ID.lambda-url.ap-southeast-1.on.aws/'
```

That script does not exercise apartment submission, private tracking, manager updates or DynamoDB persistence for apartment records. Its success does not replace the apartment checks above.

## Optional generative RAG

First verify your account can invoke Nova Micro through Bedrock in Sydney. Bedrock is usage-priced and may be restricted on your account. Add a local, ignored `infra/aws/terraform.tfvars`:

```hcl
enable_bedrock  = true
bedrock_region = "ap-southeast-2"
bedrock_model_id = "amazon.nova-micro-v1:0"
```

Re-run the deployment script. Terraform adds only `bedrock:InvokeModel` for the configured foundation-model ARN and enables the provider. Then open the legacy `/demo` page, select its AI answer option in Operations and save a synthetic IT ticket. The apartment tenant workflow does not call Bedrock. Inspect `answer_mode` in the ticket response: `bedrock`, `bedrock_cached`, or an explicit retrieval fallback/rate-limit mode. The public playground remains extractive. Requests send the owner-provided ticket and retrieved articles to the selected Bedrock region.

For local generation outside Lambda, run Uvicorn on the signed-in host with `LLM_PROVIDER=bedrock`; the base Compose app intentionally has no AWS credentials mounted. Do not bake credentials into the image.

## Costs and monitoring

Lambda has no provisioned warm capacity. DynamoDB uses one provisioned read/write unit each for the table and index; heavy writes can throttle. There is no external vector database or paid embedding endpoint. Image storage, capacity, requests, logs and optional API use can still consume allowances or credits. AWS's Free plan is time/credit-limited; do not promise perpetual free hosting.

Prometheus, Grafana and the optional CloudWatch exporter stay on the local Windows/Docker host; Terraform does not deploy a monitoring server or hosted Grafana workspace. The AWS monitoring overlay replaces the local app scrape with the CloudWatch exporter. It shows Lambda service metrics, not apartment application counters aggregated across Lambda execution environments.

The separate **TicketPilot Apartment Operations** dashboard measures the locally scraped app's submission/reply/update counters and API performance. Those in-process counters reset on restart and do not provide fleet-wide cloud apartment activity, outstanding concern counts or lifetime totals. The manager dashboard reads the stored concern queue directly, within its displayed recent-record limit.

The CloudWatch exporter uses four `GetMetricData` queries in one request every five minutes. This API can be billed. Stop the exporter when not demonstrating the dashboard. Cloud service metrics are delayed and reflect observed five-minute windows; the Grafana queries do not sum repeated polling samples as lifetime totals. The Windows browser-login profile may require the host-exporter arrangement in [AWS_CONNECTION.md](AWS_CONNECTION.md), because a Linux container cannot execute a Windows credential process. Alert rules evaluate in Prometheus; notifications require an explicitly configured Alertmanager/destination. The apartment portal does not currently send Messenger, SMS or email notifications.

## Troubleshooting

- **NoCredentials / expired token:** repeat the browser `aws login` and check `AWS_PROFILE`.
- **AccessDenied creating IAM/Lambda/ECR:** the deployment identity lacks write/pass-role permissions or the Free plan restricts the service. Inspect the exact denied action before changing permissions.
- **Public URL returns 403:** apply both Lambda URL permissions; AWS requires `InvokeFunctionUrl` and URL-scoped `InvokeFunction` on newly created function URLs.
- **Lambda initialization fails:** inspect the function's CloudWatch log group; check SSM parameter existence and the runtime role's `ssm:GetParameters` access.
- **Image manifest error:** build a single Linux/amd64 image with `--provenance=false`, as the script does.
- **Bedrock validation/access errors:** check account entitlement, regional model availability and the model ARN. The app falls back to retrieved guidance.
- **Grafana cloud panels empty:** generate a request, wait for CloudWatch ingestion and the delayed five-minute window, then check exporter status/profile credentials.
- **Repeated deployments:** each build has a new immutable tag. Remove old unused images periodically; lifecycle cleanup only expires untagged images, preserving tagged deployed versions.

## Cleanup

Deleting the app stack will delete the ticket table once protection is disabled. Export records you want to retain. To intentionally remove the demo resources, first update `protect_ticket_data = false` in `infra/aws/terraform.tfvars` and re-apply. Then run:

```powershell
terraform -chdir=infra/aws destroy
terraform -chdir=infra/bootstrap destroy
aws ssm delete-parameters --region ap-southeast-1 --names /ticketpilot-aws/admin-token /ticketpilot-aws/metrics-token
```

Terraform may ask for `image_uri` on destroy; use the digest from your last deployment or persist it in your local ignored tfvars. Destroying the bootstrap stack removes all images in its dedicated ECR repository. The SSM deletion command is a separate explicit cleanup step. Stop local monitoring with `docker compose -f compose.yaml -f compose.aws.yaml down`; omit the overlay for a host-exporter setup.

## Official references

- [AWS Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/)
- [Lambda Function URL access permissions](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html)
- [Lambda concurrency and reserved capacity](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Nova Micro regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html)
- [AWS provider Lambda permission resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission)

## GitHub CI/CD

See [CI_CD.md](CI_CD.md) for credential-free checks, tested GHCR container delivery and optional OIDC-based promotion after initial deployment and state migration. The deployed smoke script now checks apartment public pages/configuration and access denial as well as the legacy demo; it does not replace full authorized tenant/manager acceptance.
