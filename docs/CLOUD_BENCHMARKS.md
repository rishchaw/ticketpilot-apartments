# Cloud deployment and latency measurements

GCP was prepared and enabled on November 19, 2026. AWS stayed paused. The GCP tenant portal is [available here](https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/tenant). Its eight unit accounts use the private GCP inventory on the operator PC. [Deployment evidence](DEPLOYMENT_STATUS.md)

## How this GCP release was started

1. Renew Google CLI login and Application Default Credentials with `.\TICKETPILOT.cmd gcp login`. Two Google browser approvals are required. The second credential set is used by Terraform and the independent Firestore checks.
2. Confirm AWS is paused with `.\TICKETPILOT.cmd aws status`. Renew `ticketpilot` browser sign-in if required. This run confirmed concurrency 0 and HTTP 429.
3. Run `.\TICKETPILOT.cmd gcp prepare` for the initial authentication rollout. The helper builds `Dockerfile.gcp`, exercises it against the real isolated Firestore emulator and promotes that image by digest. Terraform updates `infra/gcp/bootstrap` and `infra/gcp/app` while preserving the pause. The separate GCP account-provisioning step admits the eight confirmed units.
4. Run `.\TICKETPILOT.cmd gcp start`. Terraform restores automatic min0/max1 scaling. Verify both recorded URLs, health200, the login requirement and manager access restrictions.
5. Exercise synthetic tenant concerns through the existing validator and independently verify their exact Firestore records. Guarded cleanup removes those synthetic records.

During this run Prepare applied the image before a Windows output-encoding error interrupted the wrapper. The applied state was checked, UTF-8 output was fixed, and `scripts/manage_tenants.py gcp provision` completed the pending account step. Start then hit a transient health ReadTimeout after applying automatic scaling. Subsequent status and HTTPS checks passed. Bounded transport retries were added, and a repeated Start completed with a no-change Terraform plan and successful acceptance.

The deployed app code matches the earlier tested application source. The benchmark and operational fixes are in source commit `84e1497` and run on the operator PC. They change the deployment tools. The Cloud Run image digest in the report identifies the hosted application.

For later code updates use `.\TICKETPILOT.cmd gcp redeploy`. For a temporary offline period use `.\TICKETPILOT.cmd gcp stop`. Routine lifecycle operations reuse the eight accounts.

## GCP baseline

Measured on the operator Windows PC using the existing connection, November 19, 2026, 15:09 Asia/Manila. This is a short client-observed sample from one network. GCP ran in Singapore with 1 vCPU, 512 MiB, concurrency4 and at most one instance. Source commit, timestamps, image digest and individual timings are in the [JSON report](benchmarks/gcp-2026-11-19.json).

| Endpoint | GCP measured successes | GCP median | GCP p95 | AWS |
| --- | --- | --- | --- | --- |
| GET `/health` | 20/20 | 91.493 ms | 94.927 ms | Pending |
| GET `/tenant/login` | 20/20 | 95.09 ms | 110.968 ms | Pending |
| POST `/api/analyze` | 20/20 | 93.781 ms | 107.349 ms | Pending |

The client makes one health preflight, then a first observed request, three warmups and 20 measured requests per endpoint. One keep-alive HTTP client uses concurrency1, a 250ms pause between requests, a 45-second timeout and no retries. Median and nearest-rank p95 summarize successful measured requests. HTTP and transport failures are retained. All measured requests in this run succeeded.

These numbers include the client network, TLS/connection behavior and full response body. The health preflight and preceding acceptance requests may warm the instance. Cold-start latency is unverified. `/health` reports the configured backend without a database probe. `/tenant/login` measures the public login document. `/api/analyze` exercises CPU classification and runbook retrieval in the IT demo. It uses no paid generation and persists no tenant concern. Tenant authentication latency, concern writes, database throughput and concurrent load require a separate measurement.

## Later AWS comparison

AWS measurements are pending a later switch. A speed winner and monthly cost comparison require AWS timings and billing evidence. The stored local TestClient benchmark measures a different environment and is kept outside this comparison.

Use the same PC, network, script revision, request counts and application source. Record the actual AWS image digest and runtime settings. The deployed AWS profile currently uses 1024 MiB Lambda and DynamoDB, while GCP uses 512 MiB Cloud Run and Firestore. Their provider-specific images and compute allocations differ. This compares the configured deployments, with those differences disclosed.

When ready to make that deliberate switch, use these commands from the project folder.

```powershell
.\TICKETPILOT.cmd gcp stop
.\TICKETPILOT.cmd gcp status
.\TICKETPILOT.cmd aws login
.\TICKETPILOT.cmd aws start
.\TICKETPILOT.cmd aws status
.\.venv\Scripts\python.exe scripts/benchmark_cloud.py aws --samples 20 --interval 0.25
```

Check status after each changing action and resolve failures before continuing. Benchmarking an intentionally paused URL does not measure application performance. `aws redeploy` is needed first if the application code has changed since its retained image. Keep only one provider serving at a time. The central guard enforces this using authenticated state and fresh endpoint observations.

To repeat GCP's baseline while GCP is serving, run the following command.

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_cloud.py gcp --samples 20 --interval 0.25
```

Each run writes `.tools/cloud-benchmark-PROVIDER.json`. Review its fields before adding a dated report under `docs/benchmarks`. Tenant inventories, secrets, Terraform state and raw cloud diagnostics stay private. Record later AWS results beside this baseline and document the date gap and any network or configuration changes.

For cost comparison, inspect native billing by service and time window, record gross charges and credits separately, and account for retained storage. A short latency sample does not establish a monthly bill. The $10 monthly target uses alerts. Zero idle instances still allow requests to start the service. Local Prometheus, Grafana and kind stayed stopped during this run.
