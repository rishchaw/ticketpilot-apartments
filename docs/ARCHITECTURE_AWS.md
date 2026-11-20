# AWS architecture and rationale

The AWS deployment uses Lambda and DynamoDB in Singapore. Shared FastAPI routes serve tenant and manager interfaces, with native runtime, persistence, identity and infrastructure. [Operations](OPERATIONS_QUICKSTART.md) · [Code map](CODEBASE_USAGE.md)

The authenticated image and eight-account DynamoDB registry have been deployed. The last recorded service state is paused. Local browser and Lambda-emulator acceptance passed. Hosted sign-in acceptance for this image remains pending. Exact digests and dated results are in [deployment status](DEPLOYMENT_STATUS.md).

```mermaid
flowchart TB
    B["Tenant / manager browser"] --> URL["Public HTTPS Lambda Function URL"]
    subgraph AWS["AWS Singapore: ap-southeast-1"]
        URL --> APP["Lambda: tenant login, FastAPI, UI and local retrieval"]
        APP -->|"Owner-bound concerns and durable sessions"| DB["DynamoDB: concerns + private auth namespace; on-demand + GSI"]
        APP -->|"Cold-start token resolution"| SEC["SSM Standard SecureString"]
        ROLE["Scoped Lambda execution role"] -.-> APP
        ECR["ECR immutable image digest"] --> APP
        APP --> LOG["CloudWatch Logs: short retention"]
        APP -.-> MET["CloudWatch native Lambda metrics"]
        APP -.-> AI["Optional Bedrock: disabled"]
        BUD["Optional USD 10 alert budget"]
    end
    OP["Operator / scripts/cloud.py aws"] --> TF["AWS bootstrap and application Terraform states"]
    TF -.-> ECR
    TF -.-> APP
    TF -.-> DB
    TF -.-> ROLE
    TF -.-> BUD
    OP -->|"Private account CLI, outside Terraform state"| DB
    subgraph OBS["Optional local cloud monitoring session"]
        CP["Prometheus: selected cloud only"] --> CG["Grafana dashboards"]
        CP -->|"Bearer /metrics, every 300s"| APP
    end
    subgraph LOCAL["Separate local PC or hosted CI demonstration"]
        K["kind / isolated demo credentials"] --> DA["Same app + fictional SQLite PVC"]
        DA --> P["Prometheus"] --> G["Grafana"]
    end
```

The authentication registry uses the existing DynamoDB table. The optional email budget requires an explicit recipient and is unconfigured in the recorded deployment. Prometheus and Grafana are optional local workloads.

## Service rationale

Use Lambda because this Python request/response application accepts its tested container packaging and does not need an always-running server. The Function URL supplies the simple HTTPS front door. Tenant account admission, opaque sessions, CSRF, manager authorization and concern ownership stay in application code. The existing DynamoDB table stores private authentication records, salted password hashes and session hashes; no additional hosted identity service is provisioned. Units come from authenticated identities. See [tenant access](TENANT_ACCESS.md). Lambda starts through ticketpilot.lambda_handler/Mangum, while Cloud Run uses a separate Uvicorn wrapper.

Use DynamoDB on-demand for key-based records and bounded index queries. Conditional updates reject stale versions; apartment/legacy records stay logically separate. This avoids fixed table/GSI throughput planning but retains request/storage charges. Provisioned free-capacity allowances do not make on-demand writes free. [Capacity modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html), [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/).

Use Standard SSM SecureString for the two runtime tokens, resolved with the execution role. Values are uploaded outside Terraform state. Standard parameters have no extra parameter-storage fee; KMS/optional higher-throughput conditions are separate. Do not automatically enable advanced parameters or a paid custom key. [Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/).

Use ECR for the Lambda image and deploy an immutable digest. Registry storage continues while compute is idle. Separate bootstrap/application states keep registry publication and infrastructure changes reviewable. [ECR pricing](https://aws.amazon.com/ecr/pricing/).

## Runtime and cost controls

The default configuration disables paid AI and provisioned concurrency. A supported reserved-concurrency value limits simultaneous work. When the regional quota cannot support the selected reservation, the helper records the shared/unreserved setting as `reserved_concurrency=-1`. This setting supplies no dedicated per-function concurrency ceiling. DynamoDB request ceilings provide best-effort throttling.

Terraform pause sets reserved concurrency zero, giving Function URL HTTP429 responses. Resume restores the reviewed enabled setting. Retain the URL, table/index, parameters, image, role and state. Deleting/recreating the Function URL gives a different address. [Function URL deactivation](https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html), [reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html).

The optional USD 10 budget sends email alerts to an explicitly configured recipient. Monitor gross spend, account credits and expiry independently. Retained storage, logs and API use can incur charges while compute is paused. [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)

## Native monitoring and separate local tooling

Use Lambda/CloudWatch for deployed invocations, errors, throttles, duration and execution logs. Lambda publishes native invocation metrics without an additional metric charge; log ingestion, dashboards and API retrieval may still cost. [Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html).

Prometheus/Grafana are optional local Compose/kind workloads. Central monitor-start selects only the active cloud and scrapes on a 300-second interval; pause stops local cloud monitoring. Scrapes still invoke the cloud endpoint and can consume usage. The existing optional CloudWatch exporter is another local integration with API charges. None is an always-running AWS monitoring server in this architecture.

App counters reset with each execution environment. The manager queue reads persisted concern records. CloudWatch supplies the service-wide invocation view. The application remains a single modular deployment with native managed services.

Deployment evidence must include the exact digest, storage mode, AI-off setting, private tracking/manager-note isolation, version conflicts and independent DynamoDB persistence with fictional records/guarded cleanup. CI and local Lambda emulation do not prove current account permissions. See [operations](PROVIDER_OPERATIONS.md), [AWS guide](aws/README.txt) and [portability](CLOUD_PORTABILITY.md).
