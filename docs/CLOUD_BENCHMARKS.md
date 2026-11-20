# HTTP latency benchmark

This baseline measures three public endpoints on the Singapore GCP deployment. AWS measurements are pending. Results describe the configured service and test connection.

## Results

The November 19, 2026 run used one Windows client at 15:09 Asia/Manila. Cloud Run used 1 vCPU, 512 MiB, concurrency 4 and a maximum of one instance. Paid AI was disabled. The [raw report](benchmarks/gcp-2026-11-19.json) records timestamps, source commit, image digest and individual timings.

| Endpoint | Successful measured requests | Median | p95 |
| --- | --- | --- | --- |
| GET `/health` | 20/20 | 91.493 ms | 94.927 ms |
| GET `/tenant/login` | 20/20 | 95.090 ms | 110.968 ms |
| POST `/api/analyze` | 20/20 | 93.781 ms | 107.349 ms |

## Method

The client performs a health preflight and then, for each endpoint, one first-observed request, three warmups and 20 measured requests. A single keep-alive HTTP client uses concurrency 1, a 250 ms pause between requests and a 45-second timeout. Requests have no automatic retries. HTTP and transport failures remain in the report.

Median and nearest-rank p95 summarize successful measured requests. The run completed 60/60 measured requests successfully. Source `84e1497` identifies the benchmark implementation.

## Interpretation

Elapsed time includes the network, connection behavior and complete response body. The preflight and preceding acceptance requests can warm the instance. Cold-start timing remains unverified.

The health endpoint reports configured backend information. The login endpoint serves the public login document. The analysis endpoint exercises the separate IT demo's CPU classifier and runbook retrieval. Tenant authentication, concern writes, database throughput and concurrent load require separate tests.

The AWS configuration uses a 1024 MiB Lambda runtime and DynamoDB. GCP uses a 512 MiB Cloud Run container and Firestore. A provider comparison should record those differences, the image/source versions, test date, client network and request policy.

## Reproduce

From a checkout with its private deployment records and an active GCP service, run the following command.

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_cloud.py gcp --samples 20 --interval 0.25
```

The report is written to `.tools/cloud-benchmark-gcp.json`. A corresponding active AWS deployment uses the same command with `aws` and writes `.tools/cloud-benchmark-aws.json`.

Use the [provider lifecycle](PROVIDER_OPERATIONS.md) to pause the serving provider before enabling the other. Preserve the same request policy and record configuration changes. Add reviewed, dated reports under `docs/benchmarks`.

Cost comparisons require service billing records over a defined time window, with gross charges and credits recorded separately. The latency sample establishes elapsed request timings. [Deployment evidence](DEPLOYMENT_STATUS.md)
