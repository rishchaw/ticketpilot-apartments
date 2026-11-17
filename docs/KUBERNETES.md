# Local Kubernetes demonstration

TicketPilot includes a local kind deployment for demonstrating Kubernetes alongside the separate Terraform cloud paths. It runs on Docker Desktop on this PC and creates no GKE/EKS cluster, cloud load balancer or new cloud billing resource. The GCP site can remain paused throughout this demonstration. Check [deployment status](DEPLOYMENT_STATUS.md) for actual validation and offline state; commands and manifests alone are not evidence of a successful run.

## What the deployment exercises

| Resource | Purpose |
| --- | --- |
| Namespace `ticketpilot-demo` | Separates this fictional-data demonstration |
| Deployments and ClusterIP Services | Application, Prometheus and Grafana workloads/service discovery |
| ConfigMaps and generated Kustomize manifests | Prometheus scrape configuration and Grafana provisioning |
| Kubernetes Secrets | Separate private demo manager/metrics/Grafana credentials |
| PVC `app-state`, 512 MiB | SQLite records survive application-pod replacement within the cluster |
| Probes, resource limits and non-root application | Controlled startup/readiness and a 512 MiB application limit |
| Local port forwarding | Browser access without public ingress or a cloud load balancer |

The application uses one replica and a Recreate strategy for its SQLite volume. This is a learning/demo topology with fictional data. Prometheus/Grafana use temporary storage; their history/settings reset when those pods are recreated. Dashboards and datasource configuration are reprovisioned from repository files. It is not a database migration from the real GCP or Compose deployment.

## Requirements and scope

Run all commands from the standalone repository root, `ticketpilot-aws`, in PowerShell. Have Python/the existing project environment, Docker Desktop with Linux containers, kind and kubectl available. Start Docker Desktop before creating the demo. The pinned tool configuration uses kind 0.33.0, kubectl 1.36.1 and a digest-pinned kindest/node 1.36.4 image. Install tools deliberately; the helper does not install them or provision a cloud cluster. See [kind's official quick start](https://kind.sigs.k8s.io/docs/user/quick-start/) for platform setup.

The helper is fixed to cluster `ticketpilot-portfolio`, context `kind-ticketpilot-portfolio` and namespace `ticketpilot-demo`. It uses `.tools/kubernetes/kubeconfig` and an ownership marker rather than the active global kubectl context. Generated manifests stay in `.tools/kubernetes/manifests`. Keep `.tools` and `.secrets` private and ignored by Git.

Private demo credentials are generated into `.secrets/kubernetes-demo.json`, with names `ADMIN_TOKEN`, `METRICS_TOKEN` and `GRAFANA_ADMIN_PASSWORD`. They are separate from the real Compose `.env` and GCP secrets. Do not place cloud credentials or real tenant records in this demo, and do not publish credential files or kubeconfig. Kubernetes Secrets should not be treated as encryption of arbitrary credentials; this local cluster uses disposable demonstration access codes. See [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

## Prepare and start when wanted

These commands create local Docker/Kubernetes resources and consume this PC's CPU, memory and disk. They do not resume Cloud Run:

```powershell
.\.venv\Scripts\python.exe scripts/kubernetes_local.py --help
.\.venv\Scripts\python.exe scripts/kubernetes_local.py prepare
.\.venv\Scripts\python.exe scripts/kubernetes_local.py start
.\.venv\Scripts\python.exe scripts/kubernetes_local.py status
```

`start` builds the base `Dockerfile` as `ticketpilot-k8s:local`, creates the owned kind cluster, loads that image and applies the local workloads. To reuse an already built local image, use `start --skip-build --image YOUR-LOCAL-IMAGE-TAG`. Tool paths can be supplied explicitly when they are not on PATH, for example:

```powershell
.\.venv\Scripts\python.exe scripts/kubernetes_local.py start --kind .tools/kind.exe --kubectl .tools/kubectl.exe
```

For an explicit view of the isolated resources:

```powershell
kubectl --kubeconfig .tools/kubernetes/kubeconfig --context kind-ticketpilot-portfolio -n ticketpilot-demo get pods,services,pvc
```

## Open the application and monitoring

Run each forward in its own terminal. Each stays in the foreground and binds only to localhost:

```powershell
.\.venv\Scripts\python.exe scripts/kubernetes_local.py forward app
.\.venv\Scripts\python.exe scripts/kubernetes_local.py forward prometheus
.\.venv\Scripts\python.exe scripts/kubernetes_local.py forward grafana
```

- Tenant/manager: http://localhost:18080/tenant and http://localhost:18080/manager. Use the private demo `ADMIN_TOKEN` for the manager page.
- Prometheus: http://localhost:19090. Check the app scrape target and query `up` plus application request metrics. Scraping stays inside the local cluster.
- Grafana: http://localhost:13000. Username `admin`; use the private demo `GRAFANA_ADMIN_PASSWORD`. The datasource and existing TicketPilot dashboards are provisioned automatically.

Use `--port` to override a forward's localhost port if needed. These defaults avoid Compose's ports 8080/9090/3000. Ctrl+C stops that forward only; workloads continue until stopped below. Keep any report tracking links and demo access codes out of published screenshots.

## Stop and understand the data boundary

For a combined stop from the repository root, run:

```powershell
.\.venv\Scripts\python.exe scripts/stop_services.py
```

It stops Compose while preserving volumes, removes only an owned disposable kind demo when Docker is available, and pauses the existing GCP service through Terraform. The project comes from the private local deployment record; use `--project YOUR-PROJECT-ID` if needed. `--local-only` skips GCP. If Docker is already off, it stays off and cluster deletion is skipped; cloud pause is still attempted. Check the printed summary for errors or skipped cloud work. Real cloud records/images/secrets and Compose volumes are retained; only kind's fictional demo data is disposable.

Stop all forward terminals, then run:

```powershell
.\.venv\Scripts\python.exe scripts/kubernetes_local.py stop
.\.venv\Scripts\python.exe scripts/kubernetes_local.py status
```

`stop` deletes only the cluster whose fixed name/context and local ownership marker match this helper. Deleting the kind node removes its disposable SQLite PVC/data and temporary monitoring history. A later start recreates the demonstration; it is not a state-preserving cluster pause. Private tool/configuration files remain for reproducibility. Do not use this cluster for real tenant data.

The real Compose data volumes, GCP Firestore records, cloud images/secrets/budget and AWS source configuration are separate and remain intact. A PVC protects against a pod replacement within a running cluster, not deletion of its backing kind node. See [Kubernetes persistent volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/).

For the real local Compose stack, `docker compose --profile local stop` retains its data volumes; `docker compose --profile local up -d` starts that stack again. Those commands are separate from kind and cloud scaling. To pause/resume the existing Cloud Run service through Terraform, use [the GCP guide](GCP_DEPLOYMENT.md#temporarily-pause-and-resume). Retained cloud storage/secrets can still consume allowances, and the USD 10 budget is an alert rather than a cap. No billing-plan upgrade is required.

## Evidence and portfolio scope

All five jobs in [CI run 44023034882](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44023034882) passed for source commit 4401872. Real Kubernetes acceptance verified workloads, privacy, monitoring and PVC persistence after app-pod replacement, then removed its owned cluster successfully. This is GitHub Linux-runner runtime evidence; the interrupted PC attempt is not claimed as a completed PC runtime test.

Record actual rollout, probe/resource checks, tenant/manager privacy, authenticated app scraping, Grafana provisioning and SQLite persistence after replacing the app pod. Preserve only redacted summaries or fictional screenshots. A manifest review does not establish that these checks passed; the latest observed results belong in [deployment status](DEPLOYMENT_STATUS.md).

This path demonstrates local Kubernetes workload configuration, storage and observability. GCP Cloud Run deployment and AWS Terraform remain separate provider implementations. The project does not claim a hosted GKE/EKS deployment, multi-node availability or automated provider failover. GitHub CI and cloud deployment are also separate; see [CI/CD](CI_CD.md) for the actual workflow coverage.

On Windows, double-click STOP_SERVICES.cmd in the repository root to run the stop helper. Docker stays off if already offline. Future cloud actions require renewed Google CLI/ADC browser sign-in; local kind does not use Google credentials.
