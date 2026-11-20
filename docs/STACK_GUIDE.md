# How the project uses the deployment stack

Use the [operations guide](OPERATIONS_QUICKSTART.md) for the menu steps. For the modules, storage adapters, image contents and development-only files behind each service, consult the [codebase usage review](CODEBASE_USAGE.md).

TicketPilot is one modular application. Tenant, manager and retrieval modules share a release. Managed cloud services supply compute, persistence, runtime identity, images and telemetry.

| Technology | What it does here | Where to inspect it |
| --- | --- | --- |
| Docker | Reproducible Linux images; Lambda handler or Cloud Run HTTP entry point; local acceptance before digest promotion | Dockerfile, Dockerfile.lambda, Dockerfile.gcp, compose.yaml |
| Terraform | Creates native resources, scoped runtime identities, retention and pause settings; four separate private states | infra/bootstrap, infra/aws, infra/gcp/bootstrap, infra/gcp/app |
| Kubernetes | Optional local kind exercise with Deployments, ClusterIP Services, probes, resource limits, ConfigMaps/Secrets and a fictional SQLite PVC | deploy/kubernetes, scripts/kubernetes_local.py |
| Prometheus | Authenticated app metrics; local scrape15s, optional selected-cloud scrape300s; local seven-day/512MB retention | monitoring/prometheus, ticketpilot/observability.py |
| Grafana | Provisioned Prometheus datasource and two dashboards: API/AI operations and apartment workflow | monitoring/grafana |
| AWS | Lambda/Function URL, DynamoDB, SSM, ECR, IAM and CloudWatch | [AWS diagram and rationale](ARCHITECTURE_AWS.md) |
| GCP | Cloud Run, Firestore, Secret Manager, Artifact Registry, service account and native monitoring | [GCP diagram and rationale](ARCHITECTURE_GCP.md) |

## Fresh-clone setup

Install Python3.11, Docker Desktop with Linux containers, Terraform and the selected cloud CLI. Browser authentication and account service access are required; never download long-lived cloud keys for this demo. From a fresh clone only:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/setup_local.py
```

For GCP also install its SDK adapter: `.\.venv\Scripts\python.exe -m pip install -r requirements-gcp.txt`.

Preserve an existing environment and private `.env`. `setup_local.py` reuses its current values. Grafana uses username `admin` and `GRAFANA_ADMIN_PASSWORD`. The separate manager and metrics credentials are `ADMIN_TOKEN` and `METRICS_TOKEN`. Packaged classifier artifacts support CPU serving without retraining.

## Use one provider

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws pause --profile ticketpilot
```

For GCP use `gcp` and `--project YOUR-GCP-PROJECT-ID` after CLI/ADC sign-in. Follow [provider operations](PROVIDER_OPERATIONS.md) when switching environments. Deployment builds and validates the selected image. Monitoring starts separately. Each provider retains its own accounts, concerns and tracking links.

## Use Prometheus and Grafana

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-start --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws monitor-stop --profile ticketpilot
```

Prometheus opens at http://127.0.0.1:9090. Allow container startup/discovery and up to five minutes for the first scrape. Its Targets page should then show exactly the selected cloud job up. Try these expressions:

```promql
up{job="ticketpilot"}
sum by (route) (rate(ticketpilot_http_requests_total[15m]))
sum by (status) (increase(ticketpilot_http_requests_total[15m]))
```

Grafana opens at http://127.0.0.1:3000. Sign in privately and open TicketPilot AWS Operations and TicketPilot Apartment Operations. Cloud scrapes occur every five minutes; rate panels need at least two samples and use a15-minute window. Alerts are evaluated locally; this setup does not send tenant messages or provision an external alert notification receiver.

The cloud application's counters belong to individual process/container lifetimes. Lambda environments can change between scrapes, so these graphs are diagnostic examples, not authoritative fleet totals, queue counts or billing records. Use CloudWatch or Cloud Run native metrics for fleet health. Scraping invokes the cloud app; stop monitoring after a demonstration. Native metrics and logs may also have service-specific charges.

## Use Kubernetes separately

```powershell
.\.venv\Scripts\python.exe scripts/kubernetes_local.py start
.\.venv\Scripts\python.exe scripts/validate_kubernetes_local.py
.\.venv\Scripts\python.exe scripts/kubernetes_local.py status
.\.venv\Scripts\python.exe scripts/kubernetes_local.py stop
```

The helper uses an owned kind cluster, private kubeconfig, isolated credentials and fictional SQLite data. Stop removes the verified demo cluster and its PVC. [Kubernetes setup and forwarding](KUBERNETES.md) documents required tools and validator options. Hosted results are linked from [validation](VALIDATION.md).

The IT demo performs CPU classification and local retrieval. The apartment workflow selects bilingual guidance by category. Optional Bedrock generation is preserved, disabled by default. Real building procedures, tenant onboarding, backups and data retention need deliberate review before using real tenant data.
