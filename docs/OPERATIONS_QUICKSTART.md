# Start, stop and monitor TicketPilot

Use the launcher for everyday operation. Opening its menu does not start a cloud service, open Docker, log in, deploy an image or incur application requests. Choose an action explicitly.

Current preparation: AWS has the authenticated release, eight accounts and private per-unit handouts, and remains paused. GCP is also paused, retaining an older image that predates tenant login; complete its upgrade below before starting it. Read [deployment status](DEPLOYMENT_STATUS.md) for the last verified state.

## Open the control menu

Double-click **TICKETPILOT.cmd** in the standalone project folder. From PowerShell, these two lines work regardless of the starting directory:

```powershell
Set-Location -LiteralPath 'C:\Users\rish\Documents\DLSU College - New PC\Job Application\!RESUMES\Beyond Application\ticketpilot-ai\ticketpilot-aws'
.\TICKETPILOT.cmd
```

The menu groups AWS, GCP, local tools, console/dashboard links and Stop all. Start means resume the existing deployment. Update/deploy is a separate deliberate operation; a Start selection does not build or replace the application.

| What you want | Choose | What happens |
| --- | --- | --- |
| Turn the AWS site on | AWS ? Start | Verify the protected release/accounts and other provider's pause, then restore enabled Lambda concurrency. |
| Turn the AWS site off | AWS ? Stop | Set reserved concurrency0. The same URL returns HTTP429; stored concerns, accounts and images remain. |
| Turn the prepared GCP site on | GCP ? Start | Verify the authenticated release/accounts and other provider's pause, then restore automatic min0/max1 scaling. |
| Turn GCP off | GCP ? Stop | Select manual0 instances. The retained service URL normally returns HTTP503. |
| Check a provider | AWS/GCP ? Status | Read its service state; authentication errors mean unverified state. |
| Show local cloud metrics | AWS/GCP ? Start monitoring | Start local Prometheus/Grafana for that selected active cloud only. |
| Finish a monitoring session | AWS/GCP ? Stop monitoring | Stop the local monitoring containers; keep their volumes. |
| Stop the project services | Stop all | Stop local workloads and independently pause both recorded cloud providers. Inspect each result. |

Lambda may still show **Active** in AWS while paused: that describes a ready function configuration. Concurrency0/HTTP429 is the stop control. Cloud Run automatic min0 means it can wake for a request; manual0 is the explicit pause.

The command-line version is useful for shortcuts and scripts:

```powershell
.\.venv\Scripts\python.exe scripts/control.py aws start
.\.venv\Scripts\python.exe scripts/control.py aws stop
.\.venv\Scripts\python.exe scripts/control.py --help
```

The prefix is `.\.venv` with one backslash after the dot. If Python is not found, verify that you are inside `ticketpilot-aws`; do not create a new environment over the existing one just to fix the working directory. `STOP_SERVICES.cmd` remains a direct one-click stop alternative.

## Sign in and prepare each provider

**AWS:** use profile `ticketpilot`, region `ap-southeast-1`. Choose AWS Login when browser authentication has expired. Signing in does not resume the function. The eight tenant credentials are separate from AWS operator login and the manager access code. Give residents only their own private handout from `.secrets/tenant-logins/`; follow [tenant access](TENANT_ACCESS.md).

**GCP:** use the existing `ticketpilot-gcp` configuration, region `asia-southeast1`, and its CLI plus application-default credentials (ADC). Renew both sign-ins for that existing project; do not create service-account key files. Authentication alone does not resume Cloud Run.

GCP needs a one-time authenticated-release preparation before Start can succeed. Keep it paused throughout this preparation:

```powershell
gcloud config configurations activate ticketpilot-gcp
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR-GCP-PROJECT-ID
.\.venv\Scripts\python.exe scripts/cloud.py gcp deploy --project YOUR-GCP-PROJECT-ID --leave-paused --apartment-units '1A,1B,2A,2B,2C,3A,3B,3C'
.\.venv\Scripts\python.exe scripts/manage_tenants.py gcp provision
```

Replace the project placeholder with the existing private project ID. Deploy preserves its saved pause. Provision uses the selected GCP deployment metadata and a separate private GCP inventory, not AWS passwords. Then inspect GCP Status and choose Start explicitly when you want it available. Do not bypass an old-image, missing-account or failed-authentication guard. No GCP preparation or resume is implied by reading this guide.

Only one serving provider is intended. Stop the current provider before starting the other. If the other login expired, the normal guard blocks Start instead of guessing. Its narrow explicit operator-attestation option still requires recorded paused state and fresh unavailable known URLs; use it only after independently confirming the pause. The [full operations guide](PROVIDER_OPERATIONS.md) explains that exception and the data boundary.

## Where Terraform fits

The menu calls the existing native scripts. Those use Terraform init, a saved plan, plan checks and apply for infrastructure changes. You do not need to type Terraform commands for every Start/Stop. Docker builds the application image during an explicit update/deploy; Terraform points the native runtime to its accepted digest.

| Terraform root | Resources it owns |
| --- | --- |
| `infra/bootstrap` | AWS ECR image repository/retention and the optional email budget. |
| `infra/aws` | Lambda/Function URL, protected DynamoDB table/index, runtime role and CloudWatch log group. |
| `infra/gcp/bootstrap` | Required APIs, Artifact Registry, secret metadata and the configured project budget. |
| `infra/gcp/app` | Cloud Run, protected Firestore database, runtime service account and scoped access bindings. |

Keep each root's private state and generated settings. Passwords are provisioned into the private authentication store outside Terraform; the local inventories/handouts never belong in Terraform state. Pause preserves records, accounts, images, identities and URLs. Destroying resources or deleting state is a separate operation and is not a cost-saving stop button.

## See what is running and what it costs

| View | Where to look | What it answers |
| --- | --- | --- |
| AWS application | Launcher console link ? Lambda ? ticketpilot-aws ? Monitor; CloudWatch Logs | Invocation/error/throttle/duration metrics and execution logs. Check concurrency0 for pause. |
| AWS cost and credits | [Billing and Cost Management](https://console.aws.amazon.com/costmanagement/) ? Bills; Credits/Free Tier or account-plan overview | Monthly service charges, credits applied, remaining credit and expiry. Expand services/regions for the known deployment. |
| GCP application | Launcher console link ? Cloud Run ? ticketpilot-apartments ? Metrics/Logs | Request errors, latency and instances; inspect manual0 while paused. |
| GCP costs | [Cloud Billing](https://console.cloud.google.com/billing) ? Reports or Cost table; select the existing billing account and project | Costs by service/project, discounts/credits and invoice detail. |
| Local containers | Docker Desktop ? Containers, or a scoped local container check | Which app/monitoring/kind containers are running on this PC. |
| Local Kubernetes | Local ? Kubernetes status | Only the project's isolated kind demo; it is not an AWS/GCP cluster. |

Select the same AWS account or GCP project shown by Status; an account-level bill may include other workloads.

Check **resource usage before credits** as well as the amount payable. A zero balance due can mean credits covered real usage. Billing data can lag. The launcher does not poll paid Cost Explorer APIs or create a monitoring server to show bills. Native consoles remain the source for provider billing and fleet metrics. [AWS bills](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/getting-viewing-bill.html), [AWS plan/credits](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html), [GCP Cost table](https://docs.cloud.google.com/billing/docs/how-to/cost-table).

Stopping compute does not erase stored resources. AWS DynamoDB/ECR/SSM/log data and GCP Firestore/Artifact Registry/secret/log data may continue consuming storage or other service allowances. Monitoring scrapes, log queries and SDK operations can also consume usage. AI generation remains disabled. No plan upgrade or capacity purchase occurs automatically.

The installed GCP budget alerts at the USD 10 monthly target; it is not a spending cap. AWS's USD 10 email budget remains optional and is not installed without an explicitly chosen recipient. Credits, alerts and a paused app are different controls; inspect the actual bill and remaining credit rather than assuming a permanent zero cost.

## Docker, Prometheus, Grafana and Kubernetes

Docker Desktop is a local engine. Turning it off does not pause Lambda or Cloud Run. Pausing a cloud does not automatically turn off Docker Desktop. The launcher offers opening Docker separately; ordinary cloud resume/pause does not require leaving its engine running, while image builds and local tools do.

Prometheus and Grafana are optional local containers. Use the selected cloud's Start monitoring only for a session, then Stop monitoring. They listen on localhost:

- **Grafana:** http://127.0.0.1:3000; username `admin`, password from the private `GRAFANA_ADMIN_PASSWORD` value in local `.env`.
- **Prometheus:** http://127.0.0.1:9090; Targets should show the selected cloud job up after startup and its first scrape. Query `up{job="ticketpilot"}`.

The cloud scrape interval is five minutes. Rate panels need at least two samples and use a 15-minute window. `/metrics` uses the separate private metrics bearer token; a tenant password or manager code is not its credential. App counters reset with runtime processes, so use the provider console for fleet health rather than treating these graphs as durable global totals. The [stack guide](STACK_GUIDE.md) includes useful Prometheus queries and dashboard details.

The kind Kubernetes demo uses fictional accounts/data and an isolated kubeconfig. Local Kubernetes Start/Stop/status and port-forward actions remain separate from cloud hosting. Stop removes only the verified owned demo cluster and its disposable fictional PVC. Real Compose/cloud data volumes and databases are retained. No EKS/GKE cluster or always-running cloud Grafana/Prometheus server is required. See [Kubernetes](KUBERNETES.md) for the isolated demo and forwarding ports.

If a command fails, read its result before trying another action. Wrong-directory errors need the correct folder; expired login needs sign-in; a GCP old-image guard needs authenticated-release preparation. None requires deleting data, resetting tenant passwords, erasing Terraform state or upgrading the cloud plan.

Kubernetes Start now also validates the isolated demo and creates its eight fictional accounts, so the local portal is ready for sign-in. Its private login inventory is .tools/kubernetes/tenant-accounts.json. The local menu also shows scoped Docker container status and can stop all local tools without contacting either cloud.
