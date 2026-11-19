# Local Kubernetes portfolio manifests

From the project launcher choose **Local Docker and Kubernetes → Start and validate isolated Kubernetes demo**, then use **Forward** for the desired service. [Kubernetes operations and ports](../../docs/KUBERNETES.md)

Use `python scripts/kubernetes_local.py prepare` and then `start`; do not apply these templates against a global/current kubecontext. The helper creates a private kind kubeconfig and copies the reviewed existing monitoring configuration into `.tools/kubernetes/manifests`, where Kustomize file references remain within its root. No secret value is committed here; the helper supplies a fresh local-demo Secret via stdin.

The SQLite PVC is exclusively for fictional Kubernetes demo records. It survives app Pod replacement but is lost when the owned kind cluster is deleted with `stop`. Real Compose, Firestore and DynamoDB records are never mounted or migrated. Prometheus/Grafana history is disposable. See `docs/KUBERNETES.md` for the local-only lifecycle and validation.
