# Codebase map

TicketPilot shares its application workflow across local, AWS and GCP runtimes. The active storage backend and runtime wrapper determine the provider-specific paths.

| Component | Entry point | Responsibilities |
| --- | --- | --- |
| Tenant and manager application | `ticketpilot/api.py`, `apartments.py`, `tenant_auth.py`, `static/tenant-login.*` and `static/apartments.*` | Login, session validation, unit-scoped concerns, private tracking, replies, notices and manager updates |
| Persistence | `apartment_store.py`, `tenant_auth_store.py`, `storage.py`, `firestore_store.py` | SQLite, DynamoDB or Firestore selected by `STORAGE_MODE`, with durable identity/session records and expected-version writes |
| Account administration | `tenant_accounts.py`, `scripts/manage_tenants.py` | Explicit provisioning, resets and revocation bound to the selected backend |
| AWS runtime | `Dockerfile.lambda` → `lambda_handler.py` → Mangum → FastAPI | Lambda HTTP-event adaptation and SSM-backed runtime configuration through `aws_secrets.py` |
| GCP and local HTTP runtime | `Dockerfile.gcp` or `Dockerfile` → Uvicorn → `ticketpilot.api:app` | Shared HTTP application, with the Firestore SDK installed in the GCP image |
| IT demonstration | `static/index.html`, `api.py`, `cloud_inference.py`, `assistant.py`, `knowledge.py` | NumPy classifier, packaged runbook retrieval and optional owner-requested Bedrock generation |
| Provider lifecycle | `TICKETPILOT.cmd` → `scripts/control.py` → `cloud.py` → provider helper | Build/test, registry promotion, guarded Terraform plans, pause/resume and status |
| Local monitoring | `compose.yaml`, `monitoring/prometheus`, `monitoring/grafana` | Authenticated application scraping and provisioned dashboards |
| Local Kubernetes | `scripts/kubernetes_local.py`, `deploy/kubernetes` | Isolated kind deployment, Kustomize manifests, fictional-data validation and cleanup |
| CI and release | `.github/workflows/ci.yml`, `release.yml`, `deploy-aws.yml` | Automated validation, manual container release and gated AWS promotion |

## Runtime assets

The Docker images package `artifacts/model_numpy.npz`, `artifacts/vectorizer.joblib` and `data/knowledge_base.json`. The IT demo loads those assets for classification and retrieval. Apartment concern submissions use their selected category and bilingual guidance.

The hosted application starts the API. Training, export, benchmarking and deployment commands run explicitly outside the normal request path.

## Observed locally

A fictional tenant login and concern-creation trace exercised `api`, `apartments`, `apartment_store`, `tenant_auth`, `tenant_auth_store`, `storage` and `observability`. A separate `POST /api/analyze` trace exercised `api`, `cloud_inference`, `assistant`, `knowledge` and `observability`, returning `answer_mode=retrieval`.

These traces cover two local request paths. [Validation](VALIDATION.md) and [deployment status](DEPLOYMENT_STATUS.md) record the broader test and cloud-acceptance evidence.

## Files outside the normal request path

- `data.py`, `model.py`, `train.py` and `export_numpy.py` provide synthetic-data generation, PyTorch training and export. `benchmark.py` measures local TestClient requests.
- `ticketpilot/database.py` is a legacy SQLite implementation. The current application, operator scripts and CI have no first-party imports of it.
- `scripts/deploy_aws.ps1` is a legacy entry point. The shared launcher delegates to the Python provider helpers.
- `scripts/configure_cloud_monitoring.py` is a manual target generator. Normal cloud monitoring builds its private target configuration through `cloud.py`.
- `monitoring/cloudwatch_exporter.py`, `compose.aws.yaml` and the AWS exporter configurations provide an optional CloudWatch polling path.
- Validation scripts, `preflight_aws.py`, `upload_aws_secrets.py`, packaging/release helpers and tool installers support specific operational steps.
- The four Terraform roots in `infra/` run from a deployment workstation or configured runner.

[Provider portability](CLOUD_PORTABILITY.md) describes the storage/runtime boundaries. [AWS](ARCHITECTURE_AWS.md) and [GCP](ARCHITECTURE_GCP.md) diagrams show the provisioned services. [RAG](RAG_IMPLEMENTATION.md) documents the optional generation path.
