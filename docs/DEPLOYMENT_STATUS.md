# GCP deployed and verified - November 16, 2026

TicketPilot Apartments is live on Google Cloud Run in Singapore (`asia-southeast1`), provisioned through the separate GCP Terraform roots. The deployed apartment workflow and independent Firestore persistence checks passed with fictional records.

- **Tenant portal:** [https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/tenant](https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/tenant)
- **Manager dashboard:** [https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/manager](https://ticketpilot-apartments-xliyw4o22q-as.a.run.app/manager). Use the private manager access code from local `.env`; never publish it or give it to tenants.
- **Image digest:** `sha256:a63417546288d205f2ec99479dcfb13997dc5e8057fca7bb52574d9e94da35c4`.

The runtime uses request-based billing, minimum 0/maximum 1 instances, one vCPU, 512 MiB, concurrency 4 and a 30-second timeout. Manager refresh is manual and the queue is limited to 20 records. `LLM_PROVIDER=none` disables paid model-provider calls; the packaged CPU classifier and local retrieval remain available. No hosted monitoring or vector database was provisioned.

Terraform bootstrap and application deployment completed: required APIs, the regional image repository and retention rules, two Secret Manager resources/versions, dedicated runtime identity and access bindings, public Cloud Run HTTPS service, and a protected Standard Native `(default)` Firestore database. Preflight confirmed there were no existing Firestore databases before creation. Secret values were uploaded outside Terraform and do not enter its state. The active image is kept by the `deployed` tag while the runtime uses its immutable digest. Provider locks cover Google 7.46.2 on Linux/Windows.

The project-wide USD 10/month budget was created after correcting the provider quota-project configuration. It alerts at 50%, 90% and 100% of gross cost before credits, using default billing-account recipients. **This is an alert budget, not a spending cap.** Trial credits and service allowances remain account-dependent; no billing-plan upgrade was performed.

Validation evidence:

- **101 local tests passed.** Terraform formatting, configuration validation and provider-lock checks passed for the GCP roots.
- **Real local Firestore emulator passed:** the GCP application ran under a 512 MiB/one-CPU limit and read-only root filesystem. The observed memory snapshot was 120.1 MiB; this is one test observation, not a peak-memory guarantee. Both synthetic concerns survived an application-container restart.
- **Docker Desktop networking was corrected:** the emulator stays on an internal network with no published port; a separate app bridge supports localhost access. The validator removed only its own labeled containers/networks and mounted no cloud credentials.
- **Live HTTPS acceptance passed:** pages/health, CPU classification/retrieval, two synthetic tenant submissions, private tracking and cross-key denial, manager private-note isolation, tenant-visible replies/reopening, and concurrent updates yielding one success plus one conflict.
- **Independent persistence passed:** the local Google SDK/ADC read only the exact synthetic Firestore document IDs. Both created documents were deleted with guarded cleanup (2 created, 2 deleted, 0 skipped). Existing private records and building notices were not listed or modified.

The authoritative local reports are `.tools/gcp-deployment.json`, `.tools/gcp-deployment-validation.json` and `.tools/gcp-local-validation.json`; these ignored files are not public artifacts. Google Cloud access uses browser-authenticated CLI configuration `ticketpilot-gcp` plus ADC. No GCP MCP connection or long-lived service-account key is configured.

Prometheus and Grafana remain in the local Docker stack. AWS deployment remains separately paused while phone/account activation is unresolved; its Terraform, optional Bedrock RAG and local data are preserved. GCP deployment does not migrate SQLite/DynamoDB records or replicate data between providers.

The new credential-free GCP/Firestore and Terraform CI checks are prepared, but **a hosted GitHub run of those additions has not yet been observed** at this checkpoint. Remaining rollout work is to publish/watch CI, review actual building guidance and contacts, decide retention and tenant onboarding, and keep monitoring cost/credit expiry. The public link does not verify tenant identity. Keep report-specific tracking links private and use fictional records for portfolio demonstrations. See [the GCP deployment guide](GCP_DEPLOYMENT.md) for operation and protected cleanup.

---

# GitHub repository and CI/CD

The standalone project is now public at https://github.com/rishchaw/ticketpilot-apartments under the verified GitHub CLI account `rishchaw`. The original parent projects were not uploaded. Reviewed source excludes local credentials, databases, tools and Terraform state/plans.

GitHub CI runs tests, the real apartment browser workflow, Docker/monitoring, Lambda emulation and Terraform checks. The initial hosted run passed application/browser and container checks but exposed a Windows-only provider-lock checksum problem; both Terraform roots now record signed Linux and Windows AWS provider 6.72.0 checksums. Current hosted results are visible in the repository Actions tab.

Manual container delivery publishes tested app/Lambda images to GHCR with immutable digest/provenance manifests. AWS promotion is manual, requires an existing deployment plus remote state and OIDC, and is explicitly disabled with repository variable `AWS_DEPLOY_ENABLED=false`. The `aws-demo` environment allows only the main branch. No AWS credentials or resources were configured during GitHub setup.

See CI_CD.md for workflow triggers, setup, free-platform limits and the separation between GitHub code/container delivery and actual application hosting.

---

# Latest deployment retry: AWS service access still blocked

The user requested another deployment attempt. AWS MCP tools were not exposed in this chat, so the documented AWS CLI fallback was used with profile `ticketpilot` in Singapore (`ap-southeast-1`). STS GetCallerIdentity succeeded at the beginning of the retry.

Fresh required-service checks returned:

| Check | Result |
| --- | --- |
| Lambda GetAccountSettings | `SubscriptionRequiredException` |
| DynamoDB ListTables | `SubscriptionRequiredException` |

Both service errors stated: `The AWS Access Key Id needs a subscription for the service`. No Terraform plan/apply, image push, parameter upload, resource creation, or plan upgrade was performed. Account/service activation must be resolved before provisioning.

The initial Python preflight separately failed because the local environment lacked CRT support for console-login credentials. Installed compatible `awscrt` 0.38.0 using uv and added the Boto3 CRT extra to development requirements only. Package compatibility checks pass. A later Python preflight reached the login provider but returned `LoginRefreshRequired`; the complete cause was CreateOAuth2Token `AccessDeniedException`: `The refresh token has expired.` A fresh browser login is required for that path before the next attempt. Do not confuse a valid earlier CLI access token with a working expired refresh session.

A read-only code review found the apartment storage model compatible with the existing DynamoDB key/index and IAM operations. Updated AWS deployment documentation now requires apartment-specific post-deploy checks and accurately describes monitoring as local. Remaining work after activation: renew login, verify required service access and plan/credits, review/apply Terraform, push the verified image, and test the deployed tenant/manager workflow and HTTPS URL. Current building defaults are Our Apartment and units 1-8; real-tenant onboarding remains separate.

---

# Apartment prototype - November 11, 2026

The project now targets the family's **eight-unit apartment building**, replacing concerns buried in a Messenger group chat with a formal queue for the user's mother.

Local routes are `/tenant` (also `/`) and `/manager`; the original IT support demo remains at `/demo`. The tenant portal supports English/Filipino labels, apartment categories, private per-concern tracking, replies and reopening. Managers can assign work, update status/priority, add tenant-visible messages or private notes, and publish a shared building notice. Possible multi-unit problems are flagged for human review rather than asserted to have the same cause.

40 tests and a real-browser workflow check passed using fictional records and local/emulated storage. The apartment-enabled local app and Lambda images were rebuilt. Updated local-stack validation passed, including restart persistence, Prometheus scraping and both Grafana dashboards. The local Lambda emulator also passed tenant intake, private tracking, manager updates and private-note isolation. Existing local ticket data has been preserved. The separate Apartment Operations Grafana dashboard has six panels.

This is still a local prototype. The tenant portal has no public HTTPS address, verified tenant accounts or automatic Messenger/SMS/email notifications. The open manager dashboard refreshes every 30 seconds. Approved building contacts/procedures and unit labels should be reviewed before a real-tenant pilot. The current tenant knowledge is category-based guidance, not an apartment-trained AI model. Optional Bedrock RAG and Terraform remain preserved.

AWS deployment remains paused pending account activation. CLI authentication was restored as documented below; no AWS infrastructure or billing-plan changes were made for this apartment implementation.

---

# AWS MCP configuration restored - November 11, 2026

The user authorized AWS MCP reconnection. The Codex AWS MCP entry is enabled, and the saved Claude and Cursor entries have been restored. The configurations retain AWS profile `ticketpilot`. Deployment operations remain scoped to Singapore (`ap-southeast-1`).

AWS CLI 2.39.6 is installed. Following explicit user approval, browser login completed successfully for profile `ticketpilot` in Singapore. STS GetCallerIdentity verified the expected account using a root console identity. No static access keys were created. AWS MCP tools are not exposed in the current chat; the restored client configuration still needs a client restart and a live MCP check. Successful CLI authentication does not confirm account activation or Lambda/DynamoDB service access.

Cloud deployment remains paused while phone verification/account activation is unresolved. No resources were created or modified, no Terraform deployment was run, and Bedrock remains disabled. Local app and monitoring configuration are preserved.

The earlier validation and service-access results below are historical.

---

# Deployment status - November 10, 2026

## Current result

Local validation is complete in the relocated `ticketpilot-aws` directory. The app, Prometheus and Grafana are running on this Windows PC through Docker Desktop. The Lambda image has also been built and exercised through its local Runtime Interface Emulator. No AWS deployment or real Bedrock invocation has been performed.

AWS Support is resolving an SMS verification problem during account setup. Do not create partial cloud infrastructure or upgrade the AWS plan while activation remains pending.

## Local services

| Service | Local address | Verified result |
| --- | --- | --- |
| TicketPilot | http://localhost:8080 | Analysis, authentication, ticket workflow, CSV export and persistence after app restart passed |
| Prometheus | http://localhost:9090 | Authenticated app scrape is up |
| Grafana | http://localhost:3000 | Ten dashboard panels provisioned; Prometheus datasource healthy |
| Lambda image | Temporary local emulator, stopped after validation | Health, website, classifier/retrieval and owner workflow passed with a read-only root filesystem |

Local owner/Grafana credentials remain in `.env`; they were not printed. The validation scripts removed only their synthetic test records and temporary Lambda container. The three Compose services remain running for local use.

## Docker and relocation issues resolved

Current Windows checks report `HypervisorPresent=true`, `VirtualizationFirmwareEnabled=true`, and installed WSL/Virtual Machine Platform features. Docker Engine 29.9.3 on Docker Desktop 4.99.0 responds successfully. The November 9 virtualization failure is historical and no longer describes current Docker health.

The moved Python environment still referenced the old Desktop interpreter. It was retargeted to the relocated Python 3.11.18 installation, preserving installed packages. Tests use a fresh project-local directory to avoid an inaccessible old pytest temp/cache folder.

The original Lambda Python 3.11 / Amazon Linux 2 image could not use current NumPy wheels and attempted a source build without a compiler. `Dockerfile.lambda` now uses Python 3.12 / Amazon Linux 2023 and binary packages only; its build and runtime validation passed.

## AWS access: last live checks were November 9

The official AWS MCP connection previously verified the expected account identity using the configured `ticketpilot` profile. AWS MCP tools are not exposed in the current chat, so no new live account checks were performed on November 10.

Historical Singapore (`ap-southeast-1`) checks:

| Check | Result |
| --- | --- |
| STS GetCallerIdentity | Succeeded |
| ECR DescribeRepositories | Succeeded; empty regional result |
| Lambda GetAccountSettings / ListFunctions | `SubscriptionRequiredException` |
| DynamoDB ListTables | `SubscriptionRequiredException` |

The service error was `The AWS Access Key Id needs a subscription for the service`. The Lambda console displayed **Finish account setup**. Free Tier GetAccountPlanState returned a missing-account-data error, so plan/credit eligibility remains unverified.

## Resume cloud deployment

1. Wait for AWS Support/account activation confirmation.
2. Reconnect AWS MCP and verify identity plus Lambda/DynamoDB/ECR/SSM access in Singapore with profile `ticketpilot`.
3. Verify the actual account plan, credits and expiry. Do not automatically change billing plans.
4. Validate local Terraform authentication, inspect the plans, build/push the verified Lambda image and apply the scoped deployment.
5. Verify the public HTTPS app, owner workflows, DynamoDB persistence and cloud monitoring. Bedrock stays disabled unless model access and its optional use are enabled.

The deployment preflight now returns a failure exit code when any required service is unavailable, preventing the deployment script from proceeding to secret uploads or infrastructure creation.

References: [AWS activation guidance](https://repost.aws/knowledge-center/error-access-service), [AWS Python container images](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html).
