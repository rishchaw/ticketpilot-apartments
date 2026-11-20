# Deployment status

Recorded deployment evidence through November 19, 2026. The retained environments are paused. Authenticated status commands refresh the observation before any lifecycle change.

| Environment | Accepted configuration | Recorded validation | Retained state |
| --- | --- | --- | --- |
| AWS Singapore | Lambda container, Function URL, DynamoDB, SSM and ECR | Authenticated image passed local/browser/Lambda-emulator checks. Eight native accounts provisioned. Hosted sign-in acceptance for this image is pending. | Reserved concurrency 0 and HTTP 429 at the Function URL. |
| GCP Singapore | Cloud Run, Firestore, Secret Manager and Artifact Registry | Eight native accounts and live protected tenant/manager workflow passed. Independent exact-ID Firestore reads confirmed two synthetic concerns, both cleaned up. | Manual scaling, zero instances and HTTP 503 at both recorded URLs. |
| Local Compose | SQLite application with optional Prometheus/Grafana | Browser workflow and monitoring acceptance recorded. | Stopped with persistent volumes retained. |
| Local kind | App, Prometheus, Grafana and a fictional SQLite PVC | Hosted CI exercised deployment, privacy, monitoring and restart persistence. | Owned demonstration cluster cleaned up. |

## Accepted application images

| Provider | Image digest |
| --- | --- |
| AWS | `sha256:722722a0310ebf824b0740f58d21092f643c213b9132f4c23fe3661e92ca1106` |
| GCP | `sha256:36361c401d556b44c608be7694afcd784399316e27e601f9a165d833f4209472` |

GCP revision `ticketpilot-apartments-00002-s9x` was Ready with 100% traffic during hosted acceptance. Its enabled configuration used 1 vCPU, 512 MiB and automatic min0/max1. The subsequent pause changed only the existing service's scaling configuration. Image, database, eight accounts, secrets and Terraform state were retained.

The AWS deployment retains its validated authentication image and account registry. Earlier AWS live persistence checks covered the preceding application release. The current authentication release still requires hosted sign-in acceptance.

## Validation and release evidence

The November 19 full local regression passed 453 tests. All five hosted CI jobs passed for source `af4ec96` in [run 44530000339](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44530000339). Later commits have their own CI results in the repository's Actions history. [Validation matrix](VALIDATION.md) · [CI workflow](CI_CD.md)

The GCP public-endpoint baseline completed 60 measured requests with no measured failures. Warm-up policy, configuration, raw samples and measurement limits are recorded in [benchmarks](CLOUD_BENCHMARKS.md).

The optional live Bedrock trial returned an account-verification HTTP 403 and exercised retrieval fallback. Hosted paid generation remains disabled. [Retrieval and optional generation](RAG_IMPLEMENTATION.md)

## Operations

Run `TICKETPILOT.cmd` from the standalone checkout for explicit provider status, start, stop, redeploy and monitoring actions. The shared lifecycle guard checks the other provider before enabling a deployment. CLI authentication and private Terraform records are required for fresh authenticated observations.

A paused service retains billable storage and supporting resources. The GCP $10 budget is an alert target. AWS email-budget provisioning remains optional and requires an explicit recipient. [Operations guide](OPERATIONS_QUICKSTART.md) · [Provider lifecycle](PROVIDER_OPERATIONS.md)
