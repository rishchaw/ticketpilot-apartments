# How the project uses the deployment stack

Use the [beginner redeploy and monitoring guide](OPERATIONS_QUICKSTART.md) for the menu steps. For the modules, storage adapters, image contents and development-only files behind each service, consult the [codebase usage review](CODEBASE_USAGE.md).

TicketPilot is one modular application. Its tenant, manager and retrieval modules share a release. Managed cloud services provide separate compute, storage, identity, images and telemetry. Calling each application module a deployed microservice would overstate this design; eight units do not justify independent services and queues yet.

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

The existing PC environment and private .env should be preserved. setup_local.py reuses existing values. Read GRAFANA_ADMIN_PASSWORD privately from .env; Grafana username is admin. The manager code is ADMIN_TOKEN and is distinct from the metrics token. Never publish these values. Keep packaged classifier artifacts from the repository; GPU training is not required for hosting.

## Use one provider

```powershell
.\.venv\Scripts\python.exe scripts/cloud.py aws deploy --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws status --profile ticketpilot
.\.venv\Scripts\python.exe scripts/cloud.py aws pause --profile ticketpilot
```

For GCP use gcp and --project YOUR-GCP-PROJECT-ID after its CLI/ADC login. Follow [provider operations](PROVIDER_OPERATIONS.md) before switching. Default deploy builds/validates the selected image; optional monitoring starts separately. GCP was started and its eight-account workflow verified on November 19 while AWS remained paused. Prepare is already complete for this GCP installation. Provider switching preserves independent datasets; it does not migrate concerns or their tracking links.

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

The helper uses a project-owned kind cluster, private kubeconfig, isolated credentials and fictional SQLite data. Stop deletes only that verified demo cluster/PVC. It does not deploy EKS/GKE or migrate native cloud records. See [Kubernetes setup and forwarding](KUBERNETES.md) for required kind/kubectl versions and exact validator options. Hosted CI already exercised this demo; do not claim the earlier interrupted PC attempt passed.

The IT demo performs CPU classification and local retrieval. The apartment workflow selects bilingual guidance by category. Optional Bedrock generation is preserved, disabled by default. Real building procedures, tenant onboarding, backups and data retention need deliberate review before using real tenant data.
