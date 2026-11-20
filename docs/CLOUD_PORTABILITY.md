# Cloud portability and deployment choices

TicketPilot shares application behavior across independently deployable AWS and GCP paths. Each environment uses its own data, credentials and Terraform state. The [deployment record](DEPLOYMENT_STATUS.md) contains verified rollout results. [Operations](OPERATIONS_QUICKSTART.md) · [Latency baseline](CLOUD_BENCHMARKS.md)

## One application, native cloud adapters

TicketPilot is one modular FastAPI application for eight apartment units. Tenant/manager screens, concern workflow, private tracking, version checks, the NumPy classifier and local TF-IDF retrieval share a release. Modules separate domain behavior, persistence, optional AI and metrics. This keeps deployment and troubleshooting manageable for the building's actual workload.

Compute wrappers and storage adapters connect the shared application to native databases, registries, identity and secret services. Prometheus and Grafana run in optional local Compose or kind environments.

```mermaid
flowchart TB
    UI["Tenant and manager UI"] --> API["Shared FastAPI concern workflow"]
    API --> STORE["Create/get/recent/versioned-update contract"]
    API --> CPU["Packaged CPU classifier and local retrieval"]
    STORE --> SQL["Local SQLite adapter"]
    STORE --> DDB["AWS DynamoDB adapter"]
    STORE --> FS["GCP Firestore adapter"]
    CLI["scripts/cloud.py: shared lifecycle verbs"] --> AWS["AWS scripts and Terraform states"]
    CLI --> GCP["GCP scripts and Terraform states"]
    AWS --> L["Lambda runtime wrapper"]
    GCP --> R["Cloud Run HTTP server"]
    K["Separate local kind demo"] --> OBS["Demo app, PVC, Prometheus and Grafana"]
```

| Concern | AWS native path | GCP native path | Portable boundary |
| --- | --- | --- | --- |
| HTTPS compute | Lambda container and Function URL | Cloud Run container/service URL | FastAPI routes and domain modules |
| Durable data | DynamoDB on-demand table/recent-record GSI | Firestore Standard Native database | Record shape and conflict behavior |
| Runtime identity | Lambda execution role | Attached service account | SDK default credentials; no embedded keys |
| Runtime secrets | Standard SSM SecureString | Secret Manager versions | ADMIN_TOKEN/METRICS_TOKEN names |
| Images | ECR immutable digest | Artifact Registry immutable digest | Docker build/test process |
| Metrics/logs | CloudWatch | Cloud Monitoring/Cloud Logging | Acceptance criteria and HTTP behavior |
| Infrastructure | infra/bootstrap and infra/aws | infra/gcp/bootstrap and infra/gcp/app | Terraform workflow; separate providers/state |
| Optional local tooling | Compose/kind Prometheus and Grafana | Same local demonstration | Metrics format and dashboards |

Lambda uses its handler/Mangum wrapper; Cloud Run starts Uvicorn. Shared source and Docker tooling do not make those images interchangeable. Terraform resources, IAM, pause semantics and state remain provider-specific. See [AWS architecture](ARCHITECTURE_AWS.md) and [GCP architecture](ARCHITECTURE_GCP.md).

## Operations and data boundaries

The shared CLI exposes provider-first deploy, pause, resume, status, monitor-start and monitor-stop actions. Both providers build by default; GCP also runs its pinned real Firestore emulator check before native deployment, bound to the same local image ID. An explicit --skip-build path uses a previously built/validated image. It delegates real work to separate provider scripts. The default exclusive guard prevents enabling a target when the other configured deployment is active or unknown. A narrow explicit operator attestation is available only with recorded pause and a fresh unavailable HTTP response; it does not turn an auth error into authenticated verification. See [provider operations](PROVIDER_OPERATIONS.md).

Provider switching is not migration or automatic failover. SQLite, DynamoDB and Firestore retain separate datasets; tracking links refer to their original service/data. Moving real records needs an explicit export/import plan, identifier/token preservation and reconciliation. No implicit replication or import is performed.

Preserve both providers' private Terraform states and generated variables while paused. Never apply fresh empty state over existing resources. Cloud pause retains records, images, secrets and alerts. Local kind uses fictional data that is deleted with its owned cluster.

## Cost and engineering rationale

Keep one cloud serving the demonstration at a time. Lambda execution and DynamoDB on-demand avoid idle application instances and fixed throughput planning. Provisioned DynamoDB free capacity is a different allowance, so on-demand requests must not be called free or universally cheaper. [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/).

Cloud Run is request-based with automatic min0/max1 when enabled and manual0 when paused; Firestore keeps data independently. Singapore serves the intended users, while regional prices/shared billing-account allowances still apply. [Cloud Run pricing](https://cloud.google.com/run/pricing), [Firestore quotas](https://docs.cloud.google.com/firestore/quotas).

The GCP budget uses a USD 10/month alert target. AWS email alerts are optional and require a configured recipient. Account credits, expiry and retained-resource charges must be monitored independently. Storage, logs, secret accesses, traffic and monitoring requests can consume usage while the deployment is retained.

Paid AI is disabled by default. CPU inference and TF-IDF retrieval run within the application image. The optional Bedrock integration supports an explicitly requested IT-demo generation path with retrieval fallback. [AI implementation and validation](RAG_IMPLEMENTATION.md)

The kind environment exercises Deployments, Services, ConfigMaps, Secrets, probes, resource limits, persistent storage and monitoring. Hosted CI acceptance covers an isolated Kubernetes cluster on the runner. [Kubernetes](KUBERNETES.md) · [CI/CD](CI_CD.md)