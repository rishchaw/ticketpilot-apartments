# Live GCP validation, November 19, 2026

All 451 local tests passed after the GCP transport-retry, Windows output and benchmark changes. The authenticated GCP image passed real Firestore emulator checks and live tenant/manager acceptance. Independent Firestore reads and guarded cleanup confirmed both synthetic records. Both service URLs returned HTTP 200 while AWS remained paused. [Deployment evidence](DEPLOYMENT_STATUS.md) · [Benchmark results](CLOUD_BENCHMARKS.md)

---

# Current validation - November 19, 2026

Use **Check all service statuses (live)** for current availability. CI verifies the app and disposable stacks. A local call trace exercised a fictional tenant login and concern creation and a separate IT demo analysis request. The specific modules are listed in [the code review](CODEBASE_USAGE.md#observed-locally). A live Bedrock attempt returned HTTP 403 during AWS account verification and exercised the cited fallback. [Controls](OPERATIONS_QUICKSTART.md) · [Bedrock result](RAG_IMPLEMENTATION.md)

The November 19 guide and service-control update passed **445 local tests**, including the launcher and status regressions. The earlier tenant-controls regression passed **435 tests**. Hosted [CI run44350751049](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44350751049) passed all five jobs for source commit `ff6633632bbfbe6e636612020a45697d3a5006f2`: application tests/mobile browser, Docker/Prometheus/Grafana/Lambda emulator, GCP container/real Firestore emulator, isolated kind/monitoring and all four Terraform roots. No cloud account credentials were used by CI.

The Windows launcher also passed `--check` from an unrelated folder, with cloud and Docker-engine contact both false. The source allowlist audit reviewed161files with zero matches for the eight initial tenant passwords and private local environment secrets. Real tenant inventories, handouts, state/plans and detailed reports remain excluded.

AWS's authenticated image and eight unit accounts are provisioned while compute remains paused. GCP still retains its paused pre-authentication image; these source/CI checks do not claim it was upgraded or that hosted tenant sign-in was exercised while paused. Bedrock remains disabled; generation safety/citation tests use mocks rather than paid model calls. See [deployment status](DEPLOYMENT_STATUS.md), [controls](OPERATIONS_QUICKSTART.md) and [RAG scope](RAG_IMPLEMENTATION.md).

Earlier dated records below are historical.

---

# Apartment validation - November 11, 2026

- **40 Python tests passed**: the original 26 tests plus 14 parameterized apartment workflow tests across SQLite and in-process DynamoDB emulation. Tenant key isolation, private-note exclusion, stale/future version rejection, replies/reopening, manager-controlled notices, multi-unit suggestions, input validation, process-local rate limiting and original-demo separation passed.
- A real Chrome browser check passed at a **390px mobile viewport** and **1280px manager viewport** using an isolated local server, fictional records and a separate test database. It exercised Filipino UI, submission, private tracking, manager resolution/private notes, tenant reply/reopening, a public notice and persistence through a server restart. No page errors were recorded. The screenshots were inspected for layout and mobile overflow. Tenant refresh now updates both the concern and the building notice.
- `node --check` validates browser script syntax. Python compile checks pass.
- The browser check uses `npm install --prefix .tools/browser --no-save --no-package-lock --ignore-scripts playwright@1.56.1` plus an existing Chrome installation, then `node scripts/validate_apartment_browser.cjs`. It stops its own test server/browser and leaves only fictional test artifacts under excluded `.tools`.
- These checks do not verify tenant identity, Messenger delivery, public HTTPS access, real AWS service permissions, or apartment-domain classifier accuracy. Tenant routing uses the submitted category, and no tenant flow invokes a paid model.

The updated local Docker check also passed: apartment pages/authentication, legacy persistence after app restart, Prometheus scrape, the ten-panel original Grafana dashboard and six-panel Apartment Operations dashboard. The rebuilt Lambda image passed tenant intake/private tracking, manager resolution and private-note isolation through the local emulator. No AWS or Bedrock calls were made.

Earlier November 10 records below describe the original support demo and remain historical.

---

# Validation status - November 10, 2026

All checks below ran on the user's local Windows PC, not in an AWS account.

- **26 Python tests passed.** These cover real classification/retrieval and HTTP workflows, in-process DynamoDB/SSM emulation, mocked Bedrock generation/citations/cache/limiter, the Lambda event adapter, CloudWatch metric-window calculations, and deployment-preflight gating on unavailable services/expired sign-in. One test-client dependency emits a deprecation warning; no tests fail.
- The **12 synthetic smoke scenarios** retain 75% category accuracy and 100% expected-runbook retrieval hit@3. These are authored examples, not a real-world accuracy estimate.
- Both Terraform stacks validate with Terraform 1.13.5 and AWS provider 6.72.0. Formatting checks pass. No AWS plan or apply was run.
- All three Prometheus scrape configuration syntaxes and four alert rules validate with promtool.
- The local app image builds and runs with Prometheus and Grafana through Compose. The live check confirms public analysis, owner authentication, create/resolve/list/export, SQLite persistence after an app-container restart, and cleanup of its synthetic ticket.
- Prometheus successfully authenticates to `/metrics`; the target is up. Grafana loads its ten-panel dashboard and reports its Prometheus datasource healthy.
- The Lambda image builds using Python 3.12 / Amazon Linux 2023 and binary wheels. The local emulator passes health, website, real inference/retrieval, anonymous access denial and owner create/resolve/delete with a read-only root filesystem and temporary state in `/tmp`. Its temporary container is stopped and removed afterward.

## Repeat the local integration checks on a disposable fictional Compose stack

```powershell
docker compose --profile local up --build -d
.\.venv\Scripts\python.exe scripts/validate_local_stack.py --restart-app --seed-demo-tenants
docker buildx build --platform linux/amd64 --provenance=false --load -f Dockerfile.lambda -t ticketpilot-aws-lambda:local .
.\.venv\Scripts\python.exe scripts/validate_lambda_image.py
```

The scripts write non-secret summaries to `.tools/local-validation.json` and `.tools/lambda-validation.json`. The local-stack check uses existing `.env` credentials without printing them; it only deletes its own synthetic record. No AWS credentials are passed into the Lambda test container. CI now includes both integration checks; the updated workflow has not yet run on GitHub.

The source virtual environment was repaired after the directory move. Use a fresh pytest `--basetemp` under `.tools/test-runs` and disable the cache provider if old Windows temp/cache permissions remain inaccessible. For normal fresh environments, `python -m pytest -q` remains sufficient.

Live DynamoDB permissions, deployed Lambda cold starts, account billing eligibility and real Bedrock output still need verification after account activation. See [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md).

## Tenant authentication fixtures

The portal now requires an approved tenant account. Fresh disposable CI/Compose validation explicitly uses --seed-demo-tenants to create eight fictional accounts; never use that option to replace operational tenant accounts. For an already provisioned local backend, pass its matching private --credentials-file. Cloud onboarding inventories are separate from local demo accounts. See TENANT_ACCESS.md.

The standalone Lambda RIE validator serializes invocations for its single execution environment and checks same-version conflict behavior. Genuine concurrent requests are tested separately in application, Firestore and Kubernetes acceptance. The harness preserves the original failure if session cleanup also fails.
