# Validation

The November 19, 2026 regression checkpoint passed **453 Python tests**. Hosted [CI run 44530000339](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44530000339) passed all five jobs for source commit `af4ec96`. The checks cover application behavior, browser workflows, disposable container environments and Terraform configuration.

| Layer | Coverage | Recorded result |
| --- | --- | --- |
| Application | Authentication, tenant ownership, CSRF, private tracking, manager-note isolation, session revocation and version conflicts | 453-test local suite passed |
| Browser | English/Filipino tenant forms, manager updates, replies, reopening and persistence through a server restart | Chrome workflow passed with fictional accounts and records |
| Containers and monitoring | Application persistence, authenticated Prometheus scraping, Grafana datasource/dashboards and Lambda runtime behavior | CI validation passed |
| GCP adapter | Real Firestore SDK against an isolated emulator, ownership, concurrency and persistence after restart | CI validation passed |
| Kubernetes | App, Prometheus and Grafana on kind, probes, resource limits, PVC persistence and cleanup | CI validation passed on the hosted Linux runner |
| Infrastructure | Formatting and provider-schema validation for all four AWS/GCP Terraform roots | CI validation passed without cloud credentials |

The November 20 local regression passed **454 tests**, including source-export exclusion of private notes. The isolated Chrome workflow also passed and produced the fictional-data screenshots used in the README. A built source ZIP was inspected to confirm that private study material and archived notes are excluded.

Cloud acceptance is recorded separately in [deployment status](DEPLOYMENT_STATUS.md).

| Deployment | Acceptance evidence |
| --- | --- |
| GCP | The authenticated release passed live tenant/manager workflows on November 19. Exact-ID Firestore reads verified two synthetic concerns, and guarded cleanup deleted both. |
| AWS | The authenticated image and eight accounts were provisioned. Local browser and Lambda-emulator checks passed. Hosted sign-in acceptance for that image remains pending. |
| Bedrock | The November 19 live request returned HTTP 403 during account verification and exercised the cited retrieval fallback. Successful generation remains pending. |

## Repeat the local checks

Run commands from the repository root with the project virtual environment installed. The unit suite uses isolated fixtures.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check ticketpilot/static/apartments.js
node --check scripts/validate_apartment_browser.cjs
```

The browser validator uses Playwright and Chrome. It starts its own temporary server and stores fictional screenshots and summary reports under ignored `.tools/`.

```powershell
npm install --prefix .tools/browser --no-save --no-package-lock --ignore-scripts playwright@1.56.1
node scripts/validate_apartment_browser.cjs
```

## Repeat the local integration checks on a disposable fictional Compose stack

Complete [local setup](STACK_GUIDE.md#fresh-clone-setup) and start Docker Desktop before running the container checks. The following Compose validation seeds eight fictional accounts in a disposable local database.

```powershell
docker compose --profile local up --build -d
.\.venv\Scripts\python.exe scripts/validate_local_stack.py --restart-app --seed-demo-tenants
docker buildx build --platform linux/amd64 --provenance=false --load -f Dockerfile.lambda -t ticketpilot-aws-lambda:local .
.\.venv\Scripts\python.exe scripts/validate_lambda_image.py
```

For an existing provisioned local backend, use its matching private `--credentials-file` instead of seeding accounts. The Lambda validator uses an isolated runtime container and serializes invocations to its single RIE execution environment. Concurrent version-conflict tests also run at the application, Firestore and Kubernetes layers. Cleanup failures preserve the primary validation error.

Build and check the GCP image independently.

```powershell
docker buildx build --platform linux/amd64 --load -f Dockerfile.gcp -t ticketpilot-gcp:local .
docker pull gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators
.\.venv\Scripts\python.exe scripts/validate_firestore_local.py --image ticketpilot-gcp:local
```

The Firestore validator uses a private Docker network, a real emulator and an application container with a read-only root filesystem and resource limits. It verifies real HTTP workflows and SDK persistence with fictional data, then removes its own resources.

The [Kubernetes guide](KUBERNETES.md) describes the isolated kind deployment and its validator. The [CI workflow](CI_CD.md) runs these disposable environments on GitHub-hosted infrastructure.

## Tenant authentication fixtures

The portal admits eight approved accounts. Browser, emulator and kind checks create independent fictional registries. Operational inventories remain private and environment-specific.

Tenant verification covers anonymous denial, wrong or disabled accounts, fixed-unit submissions, access denial with another tenant's valid tracking key, manager-role separation, CSRF, logout/password revocation, private-note exclusion and stale-version rejection. Exact synthetic IDs constrain live acceptance and cleanup. Validators preserve existing concerns and notices.

Public artifacts use explicit allowlists for summary JSON, JUnit and fictional screenshots. Credential inventories, cookies, databases, kubeconfig, Terraform state and saved plans remain excluded.

## Interpretation

Local tests and emulators establish behavior within their configured environments. Cloud acceptance additionally checks deployed identity, service access, runtime settings and persistence. A successful CI run validates its recorded commit.

The authored IT-demo evaluation uses synthetic scenarios. Apartment category guidance is hand-authored, and apartment-domain classifier accuracy remains unevaluated. [RAG implementation](RAG_IMPLEMENTATION.md) documents optional generation and fallback. [Cloud benchmarks](CLOUD_BENCHMARKS.md) describes the separate latency sample and its limits.
