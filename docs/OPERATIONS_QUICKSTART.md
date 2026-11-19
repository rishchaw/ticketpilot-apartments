# Start, redeploy and monitor TicketPilot

**Start** brings back the version already deployed. **Redeploy** builds the code in this folder, tests the image and uses Terraform to update the selected provider. A redeploy preserves an existing pause. **Stop** takes the site offline and keeps its data.

## Open the controls

1. In File Explorer open the standalone `ticketpilot-aws` folder. Look for `TICKETPILOT.cmd` next to `README.md`. Double-click the launcher.
2. Choose **Check all service statuses (live)**. It queries both recorded cloud services, the project's Compose containers and the local kind demo. An expired login can make one result **unknown** while the others still report. Opening the main menu alone starts nothing.
3. Choose **AWS controls** or **GCP controls** for the site you want. **0** goes back. On November 19 GCP startup was verified, then GCP was paused at the user’s request. AWS was last verified paused. [Deployment evidence](DEPLOYMENT_STATUS.md)

If you prefer PowerShell, open that folder in File Explorer, type `powershell` in the address bar, press Enter and run `.\TICKETPILOT.cmd`. The launcher finds its own Python environment. On a fresh clone, complete [local setup](STACK_GUIDE.md#fresh-clone-setup). A public clone contains the source. Operating an existing cloud deployment also requires its private Terraform state, settings, deployment records and matching secrets from the original PC or backup.

## Run commands from the correct folder

If your PowerShell prompt ends in `ticketpilot-ai>`, use the child-folder launcher path.

```powershell
.\ticketpilot-aws\TICKETPILOT.cmd gcp stop
.\ticketpilot-aws\TICKETPILOT.cmd gcp status
```

You can also enter the standalone project folder once.

```powershell
Set-Location -LiteralPath '.\ticketpilot-aws'
.\TICKETPILOT.cmd gcp stop
.\TICKETPILOT.cmd gcp status
```

After entering `ticketpilot-aws`, use the shorter commands in the tables below. The same launcher accepts `gcp start`, `gcp redeploy` and `overview`. The launcher resolves its own Python environment and helpers from its folder. The parent-folder `--check` and GCP stop paths were verified on November 19.

## Bring back the existing AWS site

Check GCP status before switching. If it is serving, choose **GCP controls → Stop portal and cloud scrapes**, then **Check status** before switching to AWS. Choose **AWS controls → Sign in through browser** if your session expired. Use the existing `ticketpilot` profile. Choose **Start existing portal**, then **Check status**. Look for `paused: false` and a successful health response (HTTP 200). Choose **Open tenant portal** to see the login screen or **Open manager dashboard** to manage concerns. For a tenant check, sign in using that unit's privately delivered credentials. [Tenant access](TENANT_ACCESS.md)

## Redeploy after changing code

1. Save the version you want to publish in this folder. The launcher builds local files. If you edited the code on GitHub instead, bring those changes into this checkout first. Keep your private `.env`, `.secrets`, `.tools` deployment records and Terraform state. Check the commit and its tests in [GitHub Actions](https://github.com/rishchaw/ticketpilot-apartments/actions/workflows/ci.yml).
2. Choose **Local Docker and Kubernetes → Open Docker Desktop**. Wait until the Linux engine is ready. Open **Check all service statuses (live)**. Stop the other provider if it is serving. Renew any required login in its provider menu.
3. **For AWS**, choose **AWS controls → Redeploy current code**. **For GCP**, renew both Google sign-ins if needed and choose **GCP controls → Redeploy current code**. The initial Prepare and eight-account provisioning completed on November 19.
4. Wait for the action to finish. Docker builds and exercises the provider image. The scripts review and apply Terraform plans and select the new image by digest. Choosing Redeploy authorizes that operation. There is no second Apply button. A failing stage may follow a successful cloud change, so use **Check status** before retrying.
5. If you want the site available and Status says it is paused, select **Start existing portal**, then **Check status** again. Look for HTTP 200 on the health check. Open the tenant and manager pages. AWS and GCP have separate tenant credentials and concern histories.

PowerShell shortcuts from the project folder perform the same actions. Pick the line for your task.

| Task | Command |
| --- | --- |
| Show status across the project | `.\TICKETPILOT.cmd overview` |
| Publish current code to AWS | `.\TICKETPILOT.cmd aws redeploy` |
| Prepare an initial GCP tenant-login deployment, already completed on this PC | `.\TICKETPILOT.cmd gcp prepare` |
| Publish later code changes to GCP | `.\TICKETPILOT.cmd gcp redeploy` |
| Resume or pause AWS | `.\TICKETPILOT.cmd aws start` or `.\TICKETPILOT.cmd aws stop` |
| Resume or pause GCP | `.\TICKETPILOT.cmd gcp start` or `.\TICKETPILOT.cmd gcp stop` |

If the other provider's status cannot be verified, use its **Sign in through browser** and **Check status**. The command output explains the problem if a provider reports an active site, mismatched account, missing state, or unexpected image. [Provider operations](PROVIDER_OPERATIONS.md)

For how GCP was started and how to repeat the later AWS measurement, read the [deployment and benchmark report](CLOUD_BENCHMARKS.md).

## Monitor a deployment

| What you want to see | What to open | What to look for |
| --- | --- | --- |
| The tenant concern queue | Provider menu → Open manager dashboard | Open concerns, assignments, progress and private manager notes. |
| All requests, errors and latency at the cloud provider | Dashboards, services and costs → AWS Lambda monitoring / AWS CloudWatch, or GCP Cloud Run monitoring / GCP logs | Select the time of the request. A paused AWS Lambda can still display Active in the console. |
| Application metrics on your PC | Run Docker Desktop. In the **serving provider's** menu choose **Start local Prometheus/Grafana**. Open **Dashboards → Prometheus targets and scrape health**. | The `ticketpilot` target should show UP after its first scrape. Open Prometheus and run `up{job="ticketpilot"}`. Cloud scraping runs every five minutes and invokes the site. |
| Charts | Dashboards → Open local Grafana | Sign in as `admin` with `GRAFANA_ADMIN_PASSWORD` from your private `.env`. Open **TicketPilot Apartment Operations**. Rate panels need at least two samples. |
| Costs and credits | Dashboards → AWS billing / credits / budgets, or GCP billing/budgets/credits | Check service charges before credits, credit balance and expiry. GCP has a $10/month alert budget. Installing the optional AWS email budget requires a recipient. Alerts do not cap spending. |
| Database, images and configuration | Dashboards → DynamoDB / ECR / SSM or Firestore / GCP container images / GCP Secret Manager | These resources survive Stop. Terraform manages infrastructure when an operation needs it. |
| Kubernetes demo | Local → Check Kubernetes demo | Check replica counts. Forward each desired service in a separate launcher window. App uses port 18080, Prometheus 19090 and Grafana 13000. |

The optional legacy CloudWatch exporter has its own foreground process on Windows. If you explicitly started that exporter, stop it with Ctrl+C in that window. [Advanced exporter controls](AWS_CONNECTION.md#host-exporter-for-windows-login-profiles)

Use the serving provider's **Stop local Prometheus/Grafana** when finished. [Prometheus queries and stack details](STACK_GUIDE.md) · [Local Kubernetes credentials and ports](KUBERNETES.md)

## Run just the local tools

- **Local → Start local apartment app** starts Compose with SQLite. Use **Rebuild local app after editing code** to update it. Open **Dashboards → Local tenant portal**, **Local manager dashboard** or **Local app health**. Tenant sign-in requires accounts provisioned in that local database. For a ready-made demonstration with eight fictional accounts use **Local → Start and validate isolated Kubernetes demo**. [Tenant environments](TENANT_ACCESS.md)
- **Local → Monitor local app with Prometheus and Grafana** points the shared Compose dashboards at `app:8080`. The local scrape interval is 15 seconds. The most recently selected local or cloud monitoring target owns ports 9090 and 3000. Check the Targets screen after switching.
- **Local → Show TicketPilot Docker containers** lists the project's containers and port mappings. Docker Desktop's Containers view provides their logs. **Stop local app** and **Stop Compose monitoring** preserve the volumes. **Stop Kubernetes demo** removes the kind cluster and its fictional data.
- To check tooling without starting anything, run `.\TICKETPILOT.cmd --check`. [Local setup](STACK_GUIDE.md#fresh-clone-setup)

## Finish a demo

Use the provider's **Stop portal and cloud scrapes**, then **Check status**. AWS pause sets reserved concurrency to zero (expected HTTP 429). GCP pause selects manual scaling with zero instances (expected HTTP 503 on the retained URLs). The database, images, logs and secrets may still incur charges. Stop local workloads separately if you started them. **Stop all known cloud and local services** attempts both cloud pauses independently and stops the normal local stack and owned kind demo. Read each result, especially after a login expires. Closing the menu only exits the launcher.
