# Apartment concern management

TicketPilot is designed for an eight-unit apartment building. Tenants report water interruptions, maintenance, electrical issues, billing questions and renewal requests through an English/Filipino mobile portal. Management reviews a shared queue with ownership, progress and private internal notes.

Each environment has its own eight-account registry, data and deployment configuration. [Tenant access](TENANT_ACCESS.md) describes onboarding and revocation. [Deployment status](DEPLOYMENT_STATUS.md) records cloud acceptance.

## Tenant and manager workflow

1. A tenant opens `/tenant` and signs in with the assigned account. The portal, building notices, intake and private concern APIs require authorization.
2. The authenticated account fixes the unit. The tenant selects a category and describes the issue in English, Filipino or Taglish. The server rejects submissions for another unit.
3. Category-based bilingual guidance requests the information needed for follow-up.
4. The saved concern receives a reference and private tracking link.
5. Management opens `/manager`, reviews the queue, assigns responsibility and updates status or priority. Tenant-visible updates and internal manager notes have separate response fields.
6. The owning tenant uses the tracking link to view updates, reply or reopen a resolved concern. Access also requires the matching signed-in identity.
7. Management can publish confirmed building notices. Similar unresolved concerns may be flagged for human review as a possible shared issue.

Statuses are received, acknowledged, scheduled, in progress, waiting for tenant and resolved. Priority starts from the category and urgent flag and remains manager-reviewed. Scheduling, billing decisions and renewal approval are handled by management.

The cloud configuration uses manual manager refresh and a twenty-record recent queue. Queue counts describe those returned records. Notifications through Messenger, SMS or email remain outside the current release.

## Accounts, sessions and privacy

Management privately provisions and distributes one approved account per unit. Initial credentials and delivery handouts remain in ignored private files. The manager access code has a separate role. Public registration is disabled.

Passwords use salted Argon2id hashes. Browser sessions use opaque, HttpOnly, Secure, SameSite=Strict cookies with an eight-hour lifetime in hosted environments. Persisted session/account checks support revocation across runtime instances. Tenant writes require a session-bound CSRF token, and persisted login limits reduce credential guessing.

A concern stores the immutable tenant identity and a hash of its tracking key. The raw key travels in a URL fragment and request header. Tenant responses expose selected public fields, with manager notes and administrative fields restricted to management. Expected-version checks reject stale writes with HTTP 409.

Existing unowned concerns remain manager-accessible until ownership is deliberately verified and assigned. Password resets preserve tenant identity. Resident turnover requires disabling departed access and reviewing identity/history reassignment. Unit-label edits preserve existing record ownership.

Forgotten-password recovery, lost tracking links, retention periods and account turnover follow management's verified administrative process. Metrics use bounded labels without usernames, units, credentials or concern text.

## Building-specific handling

| Concern | Intake and management handling |
| --- | --- |
| Water / low pressure | Record the start time and affected fixtures. Management confirms scope, cause and any restoration estimate. |
| Maintenance | Record the location and symptoms. Management agrees access and schedules work. |
| Electrical | Flag urgent conditions for prompt human review through the building's established escalation process. |
| Billing | Record the period and discrepancy. Management checks the underlying bills and payment records. |
| Contract renewal | Record the request for management review against the agreement. |
| Other | Route for triage and assignment. |

Building procedures supply actual contacts, fees, deadlines and repair arrangements. Public notices should communicate confirmed shared information while preserving private billing/contract details.

## Architecture and verification

A shared FastAPI workflow uses SQLite locally, DynamoDB on AWS or Firestore on GCP through provider adapters. Authentication records are isolated from concern records and the IT demonstration. Durable sessions and version checks persist independently of individual application instances.

Docker packages the runtime. Separate Terraform roots configure native compute, storage, identity, secrets and telemetry. Prometheus/Grafana provide optional local diagnostics. The kind deployment uses an isolated fictional-data environment. Provider switching preserves separate account inventories and concern histories. [Portability](CLOUD_PORTABILITY.md) · [Stack guide](STACK_GUIDE.md) · [AWS](ARCHITECTURE_AWS.md) · [GCP](ARCHITECTURE_GCP.md)

Verification covers anonymous denial, the eight-account registry, fixed-unit creation, cross-account denial with a valid tracking key, CSRF, revocation, private-note isolation, version conflicts and restart persistence. Local/browser/emulator/kind checks use fictional records. Live acceptance verifies exact synthetic IDs and cleans those records without enumerating existing concerns or notices.

GCP's authenticated tenant/manager workflow passed live acceptance on November 19, 2026, including independent Firestore persistence reads and cleanup. AWS's authenticated image and accounts were provisioned with local/browser/Lambda-emulator acceptance. Its hosted sign-in acceptance remains pending. [Validation](VALIDATION.md)

## Pilot preparation

Approve building guidance and contact details, establish the manager review routine, privately onboard residents and define backup, retention and turnover procedures before operational use.

Acknowledgement time, resolution time, reopening frequency and repeated reports can be measured over a defined evaluation period. Photo attachments, tenant notifications, payment handling and authenticated document retrieval are separate extensions.
