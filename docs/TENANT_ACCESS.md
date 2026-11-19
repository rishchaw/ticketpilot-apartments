# Tenant access and private account administration

The source now provides eight approved tenant accounts, fixed unit ownership and private browser sessions. Check [deployment status](DEPLOYMENT_STATUS.md) before treating these changes as live. The authenticated image has been applied to AWS with eight provisioned accounts, while preserving the user's requested pause. GCP remains paused and has not received this authentication release. Do not resume either cloud merely to provision accounts or renew a CLI login.

## Accounts and delivery

| Unit | Username |
| --- | --- |
| 1A | unit-1a |
| 1B | unit-1b |
| 2A | unit-2a |
| 2B | unit-2b |
| 2C | unit-2c |
| 3A | unit-3a |
| 3B | unit-3b |
| 3C | unit-3c |

There is no public signup. The admission registry must contain exactly eight approved identities. Management provisions those identities and gives each tenant only their own username and password. A password authenticates its holder to the account; residents must keep it private.

The AWS operator's ignored local inventory is `.secrets/tenant-credentials.json`. Initial per-unit delivery files are under `.secrets/tenant-logins/`, such as `unit-1a.txt`. Each handout contains only that unit's login, password and tenant portal URL. Keep the full inventory with the operator; share each handout individually through a private channel or on paper. Never post credentials in the Messenger group, chat transcripts, GitHub, Terraform variables/state, container images, logs or screenshots. No delivery messages are sent automatically.

Tenant-chosen passwords are not copied back to the operator's local inventory. The inventory and original handout therefore become an initial-onboarding record after a tenant changes their password. Do not rerun provisioning to overwrite a tenant-chosen password. If access is lost, use the explicit reset operation below. A reset updates the inventory but does not automatically rewrite an existing text handout: replace the affected unit's handout before distributing it again.

## Tenant flow

1. Open `/tenant`. An unauthenticated visitor is redirected to `/tenant/login`; only the login form is public.
2. Sign in with the assigned account. The portal shows its fixed unit; changing a request payload cannot submit for another unit.
3. Submit a concern and retain its private tracking link. Reading or replying requires both the signed-in owning account and the matching link key. Another tenant cannot use a copied valid link to access it.
4. Use **Change password** when desired. Passwords support 15 through 128 characters; spaces are preserved. The current password is required. A successful change rotates the current session and invalidates other sessions for that account.
5. Use **Sign out** on shared devices. The server revokes that session, and the page clears private concern content and the tracking fragment.

The login page, static assets, `/health` and the separate `/demo` remain reachable for their intended purposes. They do not grant access to tenant configuration, building notices, concerns or replies. Manager APIs retain their separate owner access code; tenant cookies do not grant a manager role.

## Manage a cloud account

Existing AWS accounts survive Start, Stop and Redeploy. Sign in through the provider menu and run the account helper from the project folder only for the specific administrative task required. The wrapper checks the selected deployment and backend before writing.

| Task | Command |
| --- | --- |
| Provision or verify the AWS registry using its matching private inventory | `.\.venv\Scripts\python.exe scripts/manage_tenants.py aws provision` |
| Reset one AWS account after verifying the resident | `.\.venv\Scripts\python.exe scripts/manage_tenants.py aws reset --username unit-1a` |
| Disable or re-enable that account | `.\.venv\Scripts\python.exe scripts/manage_tenants.py aws disable --username unit-1a` or the same command with `enable` |

A state change bumps the credential version, so disabling and later re-enabling does not restore old sessions. These are alternative administrative operations; do not run them merely to test a real resident's access. Tenant turnover requires a reviewed replacement identity and record-assignment decision. Do not hand a departed resident's reset account to a new resident, because the immutable identity owns its historical concerns.

## Other environments

The same authentication modules use a separate SQLite table locally, private DynamoDB namespacing on AWS, and a dedicated Firestore collection on GCP. Password hashes, revocation versions, sessions and login counters are persistent backend records. They are never mixed into the legacy demo ticket queue or tenant concern responses.

Use a separate private inventory for each environment, such as `.secrets/gcp-tenant-credentials.json` for an intentionally configured GCP deployment and `.secrets/local-tenant-credentials.json` for local development. Account/session data is not replicated or migrated when switching providers. Local browser, Lambda emulator, Firestore emulator and kind validation generate isolated fictional accounts instead of reading the AWS inventory.

Choose **GCP controls → Prepare first tenant-login deployment**. It deploys the protected release while paused and runs `scripts/manage_tenants.py gcp provision`. GCP uses `.secrets/gcp-tenant-credentials.json`. Subsequent GCP account administration uses `gcp` in the same wrapper. [Provider controls](OPERATIONS_QUICKSTART.md)

## First login for the local Docker app

For a new local SQLite demo, set `APARTMENT_UNITS=1A,1B,2A,2B,2C,3A,3B,3C` in the private `.env` before starting the app. From the project folder run the following PowerShell commands. The inventory stays on this PC. The last command passes it directly to the app container.

```powershell
.\TICKETPILOT.cmd local app-start
.\.venv\Scripts\python.exe -m ticketpilot.tenant_accounts generate --units "1A,1B,2A,2B,2C,3A,3B,3C" --credentials-file .secrets/local-tenant-credentials.json
Get-Content -Raw -LiteralPath .secrets/local-tenant-credentials.json | docker compose -p ticketpilot-aws --profile local exec -T app python -m ticketpilot.tenant_accounts apply --credentials-stdin
```

Open **Dashboards → Local tenant portal** and sign in with one unit from the local inventory. For an existing SQLite demo, reuse its original settings, volume and credentials. Stop, Start and Rebuild preserve that volume.

## Session and access controls

Passwords use salted Argon2id hashes. Browser sessions are random opaque values; only their hashes are stored. Production cookies are host-scoped, HttpOnly, Secure and SameSite=Strict, with an eight-hour lifetime. Session, registry and credential-version checks persist across app/container restarts and cloud instances. Logout, expiry, disabling and password/version changes invalidate the relevant sessions.

Tenant writes require a session-bound CSRF header; login requires its own custom request header, and cross-origin requests are rejected. Persisted login limits allow at most ten attempts for a known account per fifteen minutes and sixty globally per five minutes. Unknown usernames share a bounded bucket. These limits include attempts, not only failures. They reduce guessing and do not cap cloud request charges. Metrics/log labels exclude usernames, units, passwords, session IDs and concern contents.

A local fictional-data test may explicitly set `TENANT_COOKIE_SECURE=false` for localhost HTTP. Cloud configuration must retain secure cookies. API responses and login/portal pages use no-store and privacy headers; credentials are not stored in browser localStorage/sessionStorage or URL query strings.

Existing concerns without an immutable tenant owner remain manager-only, even when a signed-in tenant has their old capability link. No unit-number guessing or automatic migration grants access. Management must verify ownership before any deliberate reassignment. Keep current records and private state intact.

## Stop the services

From the project directory:

```powershell
.\.venv\Scripts\python.exe scripts/stop_services.py --provider aws --profile ticketpilot
```

Or double-click `STOP_SERVICES.cmd` to stop local workloads and independently pause both recorded clouds. `--local-only` contacts neither cloud. Inspect each result: an expired cloud login is an unverified pause, while retained database/image/secret storage can still incur costs. Pausing does not delete accounts, concerns or Terraform state. Follow [provider operations](PROVIDER_OPERATIONS.md) for later explicit resume and rollout verification.

Routine deploy/resume performs read-only health and anonymous-access checks without reading tenant passwords. Explicit --validate-tenant-workflow --credentials-file is available when the operator has current authorized credentials; it creates only owned synthetic concerns and cleans them up. Initial handouts may be stale after tenant-selected password changes. Native resume refuses a retained image without a matching validated authentication-release record; GCP must receive this release before it can resume through these helpers.
