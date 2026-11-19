# Controls and RAG documentation - November 19, 2026

TICKETPILOT.cmd now opens an explicit start/stop/status menu for the separate AWS and GCP deployments, optional local monitoring, Docker status and isolated kind demonstration. Start resumes an existing deployment; Update builds/deploys explicitly. Opening the menu and --check contact neither cloud nor Docker. The launcher also passed --check from an unrelated working directory. See docs/OPERATIONS_QUICKSTART.md.

AWS retains the authenticated image and eight native unit accounts described below, with concurrency zero. GCP retains its paused pre-authentication revision and requires the explicit Prepare workflow before Start; that workflow deploys the authenticated image with --leave-paused and provisions a separate account inventory. No provider was resumed or upgraded during this documentation/control work. Private handouts remain under .secrets/tenant-logins/.

The full current local regression passed 435 tests. The first tenant-authentication hosted run (44317754504, source b2c49bb) passed application/browser, Firestore emulator, Kubernetes and Terraform jobs; its Lambda-emulator step failed. The standalone RIE validation transport now serializes invocations to its single execution environment, and cleanup failures preserve the primary error. The corrected real Lambda-image acceptance and 15 focused helper tests passed locally. Hosted [CI run44350751049](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44350751049) passed all five jobs for source commitff6633632bbfbe6e636612020a45697d3a5006f2: application/browser, Docker/monitoring/Lambda, GCP/Firestore emulator, local kind/monitoring and Terraform. The earlier run remains a historical failure; the corrected source is green.

The RAG implementation is documented in docs/RAG_IMPLEMENTATION.md: packaged TF-IDF retrieval plus optional owner-requested Bedrock generation for the original IT demo. Paid generation remains disabled. Apartment submissions use fixed bilingual category guidance and do not currently query property documents or call a model.

---

# Eight tenant accounts deployed; services paused - November18,2026

The user confirmed units1A,1B,2A,2B,2C,3A,3B,3C. Exactly eight approved accounts were provisioned in private native DynamoDB auth records. The ignored operator inventory is .secrets/tenant-credentials.json, with one private .txt handout perunit under .secrets/tenant-logins. No credentials were printed, published, included in Terraform, embedded in images, or sent to tenants.

The stop-command path error was resolved against the actual Documents project root. Browser AWS login was renewed, the stop helper completed, local Compose/owned kind were stopped, and AWS reserved concurrency0 was verified with HTTP429. GCP remains paused with known URLs503 and expired authentication. Real data/state remain retained.

The authenticated Lambda image was built as Linux/amd64, exercised through the real Lambda emulator with eight fictional accounts, pushed by immutable digest and applied through Terraform while paused. Accepted digest: sha256:722722a0310ebf824b0740f58d21092f643c213b9132f4c23fe3661e92ca1106. The app plan changed only the existing Lambda image/environment for the confirmed unit labels. Paid AI remains disabled; no paid identity service, VM or managed Kubernetes cluster was added.

The portal/API require an approved account; concerns bind to immutable tenant_id plus their private tracking key. Forged units, cross-account valid-key access, missing CSRF and manager-role escalation are denied. Argon2id hashes, host-scoped HttpOnly/Secure/Strict opaque sessions, persisted logout/version revocation and shared login attempt limits use separate auth storage. Existing unowned concerns remain manager-only with no automatic unit adoption.

Local validation before lifecycle hardening passed312tests and a real mobile browser workflow, including password/session rotation, logout, own-unit restrictions, stolen-key denial and authenticated restart persistence. The accepted Lambda image passed the full fictional HTTPv2-cookie workflow and cleaned its disposable container. External hosted sign-in acceptance was deliberately not run while AWS is paused. Final source regression after lifecycle/packaging hardening:372tests passed. Hosted CI results follow when available.

Routine lifecycle operations do not need current tenant passwords: public health/anonymous-denial checks are automatic; real-tenant synthetic workflow testing is an explicit option with selected private credentials. Native resume requires matching validated authentication-release metadata for the exact image. The retained GCP revision predates authentication and must be replaced/provisioned before helper resume is allowed.

---

# AWS deployed and accepted - November 17, 2026

AWS is deployed in Singapore and live apartment acceptance passed, including independent DynamoDB reads and guarded synthetic cleanup. Terraform pause returned HTTP 429 and resume restored HTTP 200. GCP remains paused; its login needs renewal before control-plane changes. No plan was upgraded and paid AI stays disabled.

Tenant portal: [https://f76rtnytvzpyuw53oueg5il2by0gbpzc.lambda-url.ap-southeast-1.on.aws/tenant](https://f76rtnytvzpyuw53oueg5il2by0gbpzc.lambda-url.ap-southeast-1.on.aws/tenant). Manager page: [https://f76rtnytvzpyuw53oueg5il2by0gbpzc.lambda-url.ap-southeast-1.on.aws/manager](https://f76rtnytvzpyuw53oueg5il2by0gbpzc.lambda-url.ap-southeast-1.on.aws/manager); the private manager code stays in local .env.

AWS profile ticketpilot, ap-southeast-1; no AWS MCP tools were exposed, so deployment used the authorized CLI fallback. Before provisioning the Free Tier API confirmed plan FREE/ACTIVE, USD100 remaining credits and expiration 2027-05-17. This balance was a pre-deploy snapshot, not a promise of remaining credit after usage.

Terraform created ECR, a protected PAY_PER_REQUEST DynamoDB table/GSI, scoped runtime role, 7-day CloudWatch log group, Lambda container/Function URL and both public URL invoke permissions. Two Standard SSM SecureString tokens were uploaded outside Terraform state. App settings: 1024MiB, 30-second timeout, manual refresh0/queue20, LLM_PROVIDER=none. The regional quota is10; reserved_concurrency=-1 uses the shared pool and is not a per-function spending cap. Table/GSI throughput targets25read/10write are best-effort controls.

Accepted digest: sha256:72591b309f4c42c3992987a4240686ed40595eb3c60d89f7d8d3c4b91f82732d. Local Linux/amd64 Lambda image emulation passed before digest promotion. Both AWS Terraform roots validate. The initial post-apply URL check hit a transient reachability error; subsequent authenticated runtime readback and health200 passed, and the helper now retries bounded transient health errors.

Live acceptance passed pages/health, CPU retrieval, tenant intake, cross-key tracking denial, private-note isolation, replies/reopening and one-success/one-conflict concurrent updates. Independent strong reads verified both exact synthetic records. Guarded cleanup deleted both; existing concerns/notices were not listed or modified. Pause/resume changed only Lambda concurrency and verified429 then200 with the same URL/image/data.

GCP remains recorded paused with fresh HTTP503 from both known URLs. Its expired CLI login prevented a fresh control-plane read. The explicit cross-provider guard recorded operator attestation plus the prior pause and fresh unavailable HTTP, without claiming authenticated GCP state. No GCP resume or billing-plan change occurred.

The USD10 AWS budget is implemented as optional Terraform email alerts but NOT installed: no explicit alert recipient was provided. It is not a cap. The existing GCP USD10 gross-cost budget remains separate. Storage/logs/requests can consume credits; tagged ECR images are retained to protect the active digest and need deliberate cleanup of obsolete versions.

The one-click stop helper now pauses both recorded providers independently and preserves data; --provider selects one, --local-only neither. Auth failures remain visible and do not prevent an independent other-provider attempt. Separate provider README.txt guides, Terraform roots and Mermaid architecture diagrams are linked from README.md. Source-level DynamoDB legacy-route isolation now rejects cross-queue writes/races with404/409.

Final local regression:206 tests passed, including storage isolation, version conflicts, provider guard, empty AWS CLI output, pause preservation, post-apply recovery and independent stopping. Hosted CI results and final monitoring verification are recorded below. Authoritative reports remain private under .tools; credentials, state/plans, databases and detailed logs are excluded from source packaging. GCP and local kind are not redeployed by this task.


Final verification on November 18, 2026: system HTTP client confirmed AWS /health200 with DynamoDB/AI-off and the retained GCP health URL503. Optional local monitoring acceptance passed: exactly one selected AWS target up at300s, Grafana datasource healthy, both dashboards loaded and15-minute server-error rules present. Prometheus/Grafana were stopped afterward; local volumes remain.

Hosted [CI run44088138007](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44088138007) passed all five jobs for source commit30cd12a63e9e7077d047326ee5f2551656501f52: application/browser workflow, Docker/monitoring/Lambda runtime, GCP/Firestore emulator, local Kubernetes/monitoring, and Terraform configuration. The Kubernetes job ran on the hosted Linux runner, independently of cloud hosting. This follow-up edits evidence/guides only; no provider was redeployed and no real tenant data was touched.

---

# Temporarily offline; Kubernetes portfolio addition - November 17, 2026

The user requested a temporary cost-saving stop. The GCP Cloud Run service is paused with Terraform-managed paused=true, scaling mode MANUAL and zero manual instances. Both known public service URLs returned HTTP 503. No revision traffic tags were present. The pause applied only the existing Cloud Run service; its image, Firestore database, runtime identity, secrets and budget remain in place.

The local Compose app, Prometheus and Grafana were stopped without deleting their volumes. Docker Desktop is now offline. The one-command scripts/stop_services.py helper ran successfully, recognized the offline Docker engine without restarting it and confirmed the GCP pause. Its ignored report is .tools/stop-services.json; detailed GCP verification is .tools/gcp-service-state.json.

Real app/cloud data is retained. Image/database/secret storage may still incur costs; the USD 10 budget remains an alert rather than a cap. AWS provisioning remains separately blocked by account activation. No billing plan was upgraded, no GKE/EKS cluster was provisioned and paid AI remains disabled.

Pause/resume is explicit through scripts/deploy_gcp.py --stage pause or --stage resume using the existing private settings and Terraform state. Normal deploy/all preserves the saved pause state and skips online acceptance when paused. Ten dedicated pause-control tests and two stop-wrapper tests passed; they reject unrelated resource/image changes, wrong project settings, unsafe tagged-revision offline claims and accidental resume when settings are missing.

The local kind Kubernetes path is implemented. Hosted [CI run 44023034882](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44023034882) passed all five jobs for source commit 44018725c28eabeca635821e0297fe9b8355c2f0. Kubernetes acceptance ran on the GitHub Linux runner while this PC's Docker engine and the GCP site remained offline. The interrupted PC attempt is not claimed as a completed PC runtime test.

Acceptance verified three ready Deployments/ClusterIP Services; non-root/read-only workloads, probes, resource requests/limits and no mounted API tokens; a bound SQLite PVC with one app replica and Recreate strategy; tenant tracking privacy, manager-note isolation, version conflicts and reopening; authenticated Prometheus scraping/counters; both Grafana dashboards and datasource health; and persistence after replacing the app pod. Port-forwards were cleaned up and the owned kind cluster/PVC was deleted successfully. The artifact contains only a passing kubernetes-validation.json; no kubeconfig, credentials, databases or raw logs were uploaded.

Initial creation failed because a reserved application label was passed through kubelet node-label flags. Nodes now use the custom project label domain, with a regression check. Private metadata writes are atomic, Windows temporary filenames are short, and changed local image IDs trigger a new app rollout.

For easy Windows shutdown, double-click STOP_SERVICES.cmd in the repository root. kind and its pinned node image were downloaded; kubectl is bundled with Docker Desktop. No separate Kubernetes server installer or GKE/EKS cluster is required.

Both public health URLs still returned HTTP 503 at final verification. Google CLI and Terraform ADC authentication had expired with a reauthentication requirement (invalid_rapt). The final repeated stop attempt could not refresh the control plane and did not change or resume resources. The earlier successful Terraform pause is the last verified control-plane state. Renew browser sign-in before future cloud changes; remaining offline does not require renewing it now.

---

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

Hosted GitHub [CI run 43913020484](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/43913020484) passed all four jobs for commit `866742c8a9a8e3aaaf5380d077e06cdaea10c507`. The new GCP artifact contains only the approved metadata and passing emulator report; no credentials, databases or container logs were uploaded. Hosted observed app memory was 120.6 MiB. Live readback confirms ready revision `ticketpilot-apartments-00001-92t`, Firestore `freeTier=true` with deletion protection, configured Cloud Run min 0/max 1, and Artifact Registry automatic scanning disabled. Private Terraform state/settings backups are retained under ignored `.secrets/gcp-state/`. Remaining rollout work is to review actual building guidance and contacts, decide retention and tenant onboarding, and monitor cost/credit expiry. The public link does not verify tenant identity. Keep report-specific tracking links private and use fictional records for portfolio demonstrations. See [the GCP deployment guide](GCP_DEPLOYMENT.md) for operation and protected cleanup.

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
