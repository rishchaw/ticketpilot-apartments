# Which code TicketPilot uses

This review covers the standalone repository. It follows Docker entry points, FastAPI routes, backend selection, subprocess calls and GitHub workflow steps. The table describes which operation calls each component. Actual running instances and recent tenant traffic are separate questions. Use the launcher's **Check all service statuses (live)** for current availability.

| When | Entry point and dependency path | What executes |
| --- | --- | --- |
| A tenant or manager opens the site | `ticketpilot/api.py` includes the `apartments.py` and `tenant_auth.py` routers and serves `static/tenant-login.*` and `static/apartments.*` | Login, session checks, unit-bound concerns, replies and the manager queue. Category and language select the guidance. `observability.py` and counters in `apartments.py` instrument requests and actions. |
| A concern or login is stored | `apartment_store.py`, `tenant_auth_store.py`, shared helpers in `storage.py` and the Firestore adapter `firestore_store.py` | `STORAGE_MODE` selects SQLite in Compose/kind, DynamoDB in AWS or Firestore in GCP. `tenant_accounts.py` is an operator command for provisioning and credential changes. |
| Lambda receives a request | `Dockerfile.lambda` → `ticketpilot/lambda_handler.py` → Mangum → FastAPI | The Lambda adapter loads SSM-backed settings through `aws_secrets.py`. The normal AWS release has hosted AI disabled. |
| Cloud Run or local Docker receives a request | `Dockerfile.gcp` or `Dockerfile` → Uvicorn → `ticketpilot.api:app` | Same HTTP routes. The GCP image installs the Firestore dependency. The authenticated Cloud Run deployment was accepted on November 19. |
| Someone uses the original `/demo` IT workflow | `static/index.html`, `api.py` → `cloud_inference.py`, `assistant.py`, `knowledge.py` | Loads `artifacts/model_numpy.npz` and `vectorizer.joblib` for classification, retrieves from `data/knowledge_base.json` and formats cited steps. Only the owner workflow can explicitly request Bedrock when configured. `storage.py` also stores these IT tickets. |
| Operator starts, stops or redeploys | `TICKETPILOT.cmd` → `scripts/control.py` → `cloud.py` → `deploy_aws.py` or `deploy_gcp.py` | Shared provider checks, separate Docker builds, registry pushes and Terraform roots. `manage_tenants.py` binds administration to a selected deployment. `STOP_SERVICES.cmd` runs `stop_services.py` directly. |
| Operator opens local monitoring | `compose.yaml`, `monitoring/prometheus` and `monitoring/grafana` | Local app scrapes use `local.yml`. Cloud monitoring writes a private target config. Grafana loads the provisioned datasource and both dashboards. `cloudwatch_exporter.py`, `compose.aws.yaml` and the AWS exporter configs are optional separate CloudWatch polling paths. |
| Operator demonstrates Kubernetes | `scripts/kubernetes_local.py` and `deploy/kubernetes` | kind, kubectl and Kustomize deploy local workloads with fictional data. The validator checks routes, monitoring and persistence. |
| A change goes through GitHub | `.github/workflows/ci.yml`, `release.yml` and `deploy-aws.yml` | CI runs tests, browser/emulator/monitoring checks, kind, Terraform validation and `ticketpilot/evaluate_pipeline.py`. Manual release uses packaging and manifest helpers. Optional AWS promotion uses `select_release.py`, `deploy_ci.sh`, `check_deployment_plan.py` and `smoke_aws.py`. A push to main runs checks. |

## Observed locally

A Python call trace of the fictional login and concern-creation test exercised `api`, `apartments`, `apartment_store`, `tenant_auth`, `tenant_auth_store`, `storage` and `observability`. A separate fictional request through `POST /api/analyze` exercised `api`, `cloud_inference`, `assistant`, `knowledge` and `observability`, and returned `answer_mode=retrieval`. These observations cover two local request paths. The other entries above come from source and deployment configuration, with dated cloud checks in [deployment status](DEPLOYMENT_STATUS.md).

## Files outside the normal request path

- `ticketpilot/data.py`, `model.py`, `train.py` and `export_numpy.py` support generating data, PyTorch training and exporting weights. `benchmark.py` is a developer benchmark. The container Dockerfiles copy the Python package, but their startup commands load the API. Training and benchmarking require an explicit invocation. The untracked training checkpoint, synthetic CSV and old benchmark/evaluation reports on the operator PC are outside the runtime asset list.
- `ticketpilot/database.py` is an older SQLite implementation. No first-party import from the current app, operator scripts or CI was found. Both apartment and IT routes have other storage implementations.
- `scripts/deploy_aws.ps1` is a legacy deployment entry. The Windows menu calls the Python lifecycle scripts. `configure_cloud_monitoring.py` is a separate manual target generator. The regular cloud monitor action builds its own config in `cloud.py`.
- `scripts/validate_*`, `smoke_cloud.py`, `preflight_aws.py`, `upload_aws_secrets.py` and `install_validation_tools.py` run during specific deployment, checking or setup tasks. `tests/` and `.github/` run outside the hosted app. The four `infra/` roots run on the operator's machine or a configured deployment runner.

The two cloud diagrams describe provisioned services and their connections. The RAG guide documents the live Bedrock denial and local fallback. [AWS](ARCHITECTURE_AWS.md) · [GCP](ARCHITECTURE_GCP.md) · [RAG implementation](RAG_IMPLEMENTATION.md) · [Operating instructions](OPERATIONS_QUICKSTART.md)
