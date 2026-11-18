# Apartment concern tracker

TicketPilot serves a family-managed apartment building with eight confirmed units: **1A, 1B, 2A, 2B, 2C, 3A, 3B and 3C**. It replaces concerns buried in a Messenger group chat with an English/Filipino mobile form and one manager queue.

The source now includes closed tenant accounts and per-account concern ownership. Read [deployment status](DEPLOYMENT_STATUS.md) for the accepted cloud image and current pause state. Authentication rollout verification is still being completed; a source change alone does not establish deployed behavior. AWS is to remain paused under the latest stop request, and GCP remains separately paused without this authentication release. No cloud plan is upgraded automatically.

## Tenant and manager workflow

1. A tenant opens `/tenant` and signs in using their assigned account. The login page is public, while the portal, configuration/notices, intake and private concern APIs require authorization. There is no public signup.
2. The portal fixes the unit from the authenticated account. The tenant chooses water/plumbing, maintenance, electrical, billing, contract renewal or another concern and describes it in English, Filipino or Taglish. The server rejects attempts to submit for another unit.
3. Category-based bilingual guidance requests useful details. It is intake assistance, not an apartment-trained classifier, a paid AI answer or approved building policy.
4. A saved report receives a reference and a private tracking link. This is a receipt, not confirmation that a manager read it or received a notification.
5. Management signs in separately at `/manager` using the private owner access code, reviews the queue, assigns responsibility and updates status/priority. Tenant-visible messages and internal manager notes remain separate.
6. The owning signed-in tenant uses the tracking link to view updates, reply or reopen a resolved concern. Another tenant cannot use a copied valid key to read or reply to it.
7. Management can publish a confirmed notice for signed-in tenants. Similar unresolved concerns can be flagged as a possible shared issue; a person confirms the cause before linking explanations or making building-wide claims.

Statuses are received, acknowledged, scheduled, in progress, waiting for tenant and resolved. Priority starts from the chosen category/urgent checkbox and remains manager-reviewed. A report does not automatically schedule a repair or approve a renewal.

The low-cost cloud settings use manual manager refresh and a queue of up to twenty recent records. Counts describe the returned records, not all historical concerns. Local demonstration settings may differ. Agree a review routine with management; this release does not send Messenger, SMS or email notifications.

## Accounts, sessions and privacy

Management privately distributes one account for each confirmed unit. The operator's initial credentials and per-unit handouts stay in ignored `.secrets/` files. Give a resident only their own handout; never post passwords or concern-specific tracking links in the Messenger group. The manager access code is separate and must not be given to tenants. [Tenant access](TENANT_ACCESS.md) documents initial onboarding, password changes, resets and revocation.

Passwords are salted Argon2id hashes. Browser sessions use opaque, HttpOnly, Secure, SameSite=Strict cookies with an eight-hour lifetime. Session checks and revocation are durable across runtime instances. Tenant mutations require a session-bound CSRF token; persisted login limits reduce credential guessing. Passwords/session tokens are not placed in URL queries or browser localStorage/sessionStorage. Metrics use bounded workflow labels without unit IDs, usernames or concern text.

Each new concern is bound to an immutable tenant identity. The tracking capability is an additional check: only its hash is stored, and the raw key stays in a URL fragment and request header. Tenant responses exclude manager notes, assignments and authentication/storage fields. Optimistic version checks prevent stale tenant/manager writes from silently overwriting newer updates.

Existing concerns without a tenant owner remain readable to management but are denied to tenant sessions until management verifies an explicit assignment. Changing unit labels does not migrate records. Password resets preserve the same tenant identity; a new resident must not inherit a departed resident's reset account and history. Disable departed access and review turnover/reassignment deliberately.

The portal authenticates an approved account; residents must still protect its credentials. There is no public registration, automatic tenant identity verification, self-service forgotten-password recovery, automatic retention policy or lost-tracking-link recovery in this release. Management verifies those requests through its established private process.

## Building-specific handling

| Concern | Information and handling |
| --- | --- |
| No water / low pressure | Ask when it began and which fixtures are affected. Management checks scope and confirms the cause or any restoration estimate. |
| Repairs / maintenance | Record the location and issue. Management agrees access and schedules work rather than promising an automatic visit. |
| Electrical / immediate hazard | Flag for prompt human review. Immediate-danger cases use established emergency contacts; a ticket is not emergency response. |
| Billing | Record the period and discrepancy. Management verifies actual bills/payments; the portal does not calculate authoritative balances, confirm payments or change charges. |
| Contract renewal | Record the request. Management reviews the real agreement; the portal does not approve renewal or invent terms. |
| Other | Management triages and assigns action. |

Actual contact numbers, fees, deadlines, renewal terms and repair availability have not been invented. Guidance remains generic until the parents approve building procedures. Building notices must exclude private billing/contract details and distinguish confirmed facts from estimates.

## Architecture and verification

The same FastAPI workflow runs on local SQLite, AWS DynamoDB or GCP Firestore through separate adapters. Authentication records are namespaced separately from apartment concerns and the original IT demo. Durable sessions and version checks do not require a hosted identity subscription or an always-running cloud VM. The original IT classifier and optional disabled Bedrock retrieval/generation flow remain at `/demo`; their synthetic accuracy figures do not describe apartment concern routing.

Docker packages the runtime. Separate Terraform roots retain native AWS/GCP compute, persistence, identity, secrets and telemetry. Prometheus/Grafana are optional local diagnostic tools, and kind provides an isolated fictional-data Kubernetes demonstration. Provider switching does not replicate accounts, sessions, concerns or tracking links. See [portability](CLOUD_PORTABILITY.md), [stack guide](STACK_GUIDE.md), and the separate [AWS](ARCHITECTURE_AWS.md) and [GCP](ARCHITECTURE_GCP.md) diagrams.

Security verification must include anonymous denial, exactly eight admitted accounts, fixed-unit creation, cross-account denial with a genuine stolen key, manager-role separation, CSRF, session/password revocation, private-note isolation, version conflicts and persistence after restart. Local, browser, emulator and kind tests use fictional credentials/data. Live acceptance may touch only exact synthetic IDs owned by that run and must not enumerate or modify real tenant records/notices. Current results belong in deployment status and safe allowlisted validation reports; no credential inventory, cookie or database is a public artifact.

## Pilot preparation

Before real tenant use, finish deployment acceptance, approve building guidance and contacts, privately onboard residents, agree management's review routine, and decide backups/data retention and tenant-turnover handling. A stopped cloud service remains unavailable until an explicit verified resume. No messages or credentials are sent to tenants automatically.

Measure acknowledgement time, resolution time, reopened concerns and repeated messages about the same issue, together with the sample size and evaluation period. Payments, automatic renewals, photos, tenant notifications and authenticated document RAG are separate future features.
