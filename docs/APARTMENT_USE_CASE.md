# Apartment concern tracker

Confirmed November 11, 2026: a family-managed building with **eight units**. Tenants currently send concerns through a Messenger group chat, requiring the user's mother to repeatedly search messages. TicketPilot provides a formal queue with an English/Filipino mobile tenant form.

## Implemented local workflow

1. A tenant opens `/tenant` and selects a unit and category. Default unit labels are 1-8 and can be customized through `APARTMENT_UNITS`. The building display name is configurable through `APARTMENT_NAME`.
2. The tenant describes the issue in English, Filipino or Taglish. Categories are water/plumbing, maintenance, electrical, billing, renewal and other. Category-based bilingual guidance requests useful details; no IT classifier or paid AI is used for this workflow.
3. The report is saved with a reference and a private tracking link. Saving is a receipt, not an acknowledgement that a manager has read the concern or received a notification.
4. A manager opens `/manager` using the existing owner access code, reviews the queue, assigns action and updates status/priority. Messages for the tenant and private manager notes are separate.
5. The tenant opens their tracking link to read updates, reply, or reopen a resolved concern. Refresh retrieves the current concern and building notice. The manager dashboard checks for new reports every 30 seconds while open.
6. If multiple units have unresolved reports in a shared category, the manager sees a possible shared issue. Management confirms the cause before publishing a public building notice. Individual reports remain private and are not automatically linked or closed.

Statuses: received, acknowledged, scheduled, in progress, waiting for tenant, resolved. Priority is initially based on the selected category/urgent checkbox and is editable by management; it is not a calibrated AI risk estimate.

## Privacy and access model

Each concern has a random capability key. Only its hash is stored. The tenant API requires that key, and response fields exclude private notes, the hash and internal assignment. Unit numbers do not authenticate anyone or grant access to that unit's other reports. Anyone holding the private tracking link can read and reply to that concern, so keep it out of the group chat. The key is placed in the URL fragment and sent to the API in a header, not as a query-string credential.

The manager access code stays in the tab's memory. Do not share it with tenants. Dynamic responses are not cached, and the apartment page uses a restrictive content security policy and safe text rendering. Optimistic version checks prevent stale tenant or manager edits from silently overwriting newer updates.

Intake does not verify tenant identity. There are no full tenant accounts, tracking-link recovery/revocation, global cloud-wide abuse quotas or automatic retention/deletion policies yet. Public live-tenant rollout needs deliberate onboarding and access decisions. Development and validation use fictional records.

## Building-specific handling

| Concern | Information and handling |
| --- | --- |
| No water / low pressure | Ask when it started and which fixtures are affected. Manager checks scope and confirms cause or restoration estimates. |
| Repairs / maintenance | Record location and issue. Manager agrees access and schedules work rather than promising a visit automatically. |
| Electrical / immediate hazard | Flag for prompt human review. The form directs immediate-danger cases to established emergency contacts; a ticket is not emergency response. |
| Billing | Record period and discrepancy. Manager verifies actual bills/payments; the portal does not calculate authoritative balances, confirm payments, or change charges. |
| Contract renewal | Record the request. Manager reviews the actual agreement and decides; the portal does not approve renewal or invent contract terms. |
| Other | Manager triages and assigns action. |

Actual contact numbers, fees, deadlines, renewal conditions and repair availability have not been supplied or invented. The existing guidance is generic intake assistance, not approved property policy or legal advice. Public building notices must exclude private billing/contract details and identify only confirmed information.

## Architecture and evidence

Apartment records live in a separate SQLite document table locally or a separate queue partition in the existing DynamoDB table. Existing demo records are preserved. The manager queue is bounded to 200 recent records and at most one DynamoDB query page; counts are scoped to returned records. The original IT demo is retained at `/demo`, with its classifier and optional Bedrock RAG. Its synthetic accuracy figures do not apply to apartment concerns.

Prometheus retains bounded labels without unit IDs or concern text. Grafana provisions a separate six-panel Apartment Operations dashboard. Counters reset on process restart and measure workflow activity, not outstanding work. Terraform and AWS integration source are preserved; cloud deployment remains paused pending account activation.

Forty Python tests cover the original app plus apartment workflows on SQLite and emulated DynamoDB. A Chrome check exercises mobile Filipino submission, private tracking, manager resolution/private notes, replies/reopening, notices and restart persistence. The local Docker stack and Lambda runtime emulator also pass the updated validation scripts. See VALIDATION.md for scope and limits.

## Deployment and next pilot steps

The current app is bound to this computer's localhost. It is not accessible from tenants' phones. After a reachable HTTPS deployment, share the public `/tenant` URL or create a QR code for that exact URL; keep private tracking links separate. No messages have been sent to tenants or the Messenger group.

Before a real pilot: confirm actual unit labels and building contacts, review the guidance with the parents, agree a concern-review routine, and decide how residents will be onboarded. Automatic Messenger/SMS/email notifications, photos, confirmed incident linking, authenticated private-document RAG, and model training are future work, not current capabilities. Notifications are particularly useful if management should not need to keep the dashboard open.

Pilot success should be measured using acknowledgement time, resolution time, reopened concerns and repeated messages about the same building issue, with sample size and evaluation period reported.
