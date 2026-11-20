# Project development instructions

Read the component map, deployment status and relevant operations guide before changing application or infrastructure behavior.

## Application boundaries

- Preserve the tenant/manager workflow, exactly eight approved account slots, immutable tenant ownership and private tracking checks.
- Keep Argon2id password verification, persistent session revocation, CSRF validation and manager authorization intact.
- Preserve expected-version writes and conflict behavior in SQLite, DynamoDB and Firestore adapters.
- Keep the apartment workflow and the separate IT classifier/retrieval demonstration distinct.
- Keep production credentials, account inventories, tracking keys and real concern data out of logs, screenshots, fixtures and artifacts.

## Infrastructure and validation

- Use separate provider Terraform roots and preserve their existing private state and settings.
- Cloud lifecycle changes require an explicit operational request. Documentation, code review and local validation do not authorize starting a cloud deployment.
- Treat an authentication or transport failure as an unverified observation. Verify provider state and endpoint behavior before reporting an operation successful.
- Keep cloud promotion bound to the validated image digest. Review plans for replacements, deletes and unrelated changes.
- Use isolated fictional data for browser, emulator and kind checks. Clean up resources owned by those checks.
- Keep the kind cluster name and ownership checks intact. Use its isolated kubeconfig.
- Run checks appropriate to the change and retain accurate evidence of what ran.

## Local material and publishing

Personal study guides, resume drafts, interview notes and workstation histories belong in ignored `.local-notes/`. Keep that material out of commits, container contexts and source exports. The local operator checkpoint is `.local-notes/OPERATOR_CONTEXT.md` when present.

Public documentation should describe the product, architecture, reproducible operations, measured results and known technical limits. Keep live identifiers and private configuration in ignored local records. Use the dated deployment and validation documents for recorded evidence.
