# CI and release workflows

GitHub Actions validates changes to `rishchaw/ticketpilot-apartments`. Cloud deployments use explicit provider operations through the [deployment controls](OPERATIONS_QUICKSTART.md). The repository contains a manual container release workflow and a separately gated AWS promotion workflow.

## Three workflows

| Workflow | Trigger | Result |
| --- | --- | --- |
| [TicketPilot CI](../.github/workflows/ci.yml) | Push to main, pull request, manual run or reusable workflow call | Five validation jobs for application/browser behavior, Docker/monitoring/Lambda runtime, GCP/Firestore, local Kubernetes and Terraform |
| [Container release](../.github/workflows/release.yml) | Manual run from the default branch | Reuses CI, builds and validates app/Lambda images, publishes to GHCR and records image digest, source commit and workflow provenance |
| [AWS promotion](../.github/workflows/deploy-aws.yml) | Manual run with a successful release run ID | Requires configured OIDC and remote state, verifies provenance and promotes an existing Lambda image through a guarded Terraform plan |

CI jobs have read-only repository permissions and use fictional data without cloud deployment credentials. The release publisher can write packages. The deployment job can request an OIDC token after its gates succeed. Actions are pinned to commit IDs, jobs have timeouts and obsolete CI runs are canceled.

Reports use allowlisted JSON/JUnit files and fictional screenshots. CI artifacts are retained for three days, and release manifests/source archives for seven days. Databases, tokens, credential inventories, Terraform state, plans and kubeconfig stay outside uploaded artifacts.

## Use the existing repository

Push or open a pull request to run CI, then inspect all five job results. The November 19 checkpoint passed in [run 44530000339](https://github.com/rishchaw/ticketpilot-apartments/actions/runs/44530000339) for source commit `af4ec96`.

Run **TicketPilot container release** from main for a tested release artifact. The manifest binds immutable digests to the repository, source commit and workflow run. Tags include commit/run identifiers, while promotion selects the recorded digest.

The GHCR targets are `ghcr.io/rishchaw/ticketpilot-apartments` and `ghcr.io/rishchaw/ticketpilot-apartments-lambda`. Package visibility is configured separately from repository visibility. The release uses its scoped `GITHUB_TOKEN`.

## Optional AWS promotion from GitHub

The promotion workflow is implemented and remains disabled until its deployment identity and state backend are configured. Keep `AWS_DEPLOY_ENABLED` unset or false during setup. The local launcher supports the retained AWS deployment and paused-image updates.

1. Create a private S3 state bucket in Singapore with versioning, encryption and public-access blocking. Back up the existing application state.
2. Create the ignored `infra/aws/backend.ci.tf` file.

   ```hcl
   terraform {
     backend "s3" {}
   }
   ```

3. Migrate the existing application state interactively using the intended bucket and key.

   ```powershell
   $env:AWS_PROFILE = 'ticketpilot'
   $env:AWS_REGION = 'ap-southeast-1'
   terraform -chdir=infra/aws init -migrate-state -backend-config='bucket=YOUR-PRIVATE-STATE-BUCKET' -backend-config='key=ticketpilot-aws/app/terraform.tfstate' -backend-config='region=ap-southeast-1' -backend-config='encrypt=true' -backend-config='use_lockfile=true'
   terraform -chdir=infra/aws state list
   ```

   Verify that the migrated state includes `aws_lambda_function.app` and `aws_dynamodb_table.tickets`. The ECR bootstrap state remains separate. Existing infrastructure requires its matching state.

4. Configure GitHub's OIDC provider and a dedicated deployment role. Scope permissions to the project ECR repository, Lambda/Terraform operations, S3 state/lock access and SSM parameter metadata. Runtime secret values remain outside CI.
5. Create the GitHub environment `aws-demo` with deployment branches restricted to main. Bind the role trust to audience `sts.amazonaws.com` and exact subject `repo:rishchaw/ticketpilot-apartments:environment:aws-demo`.
6. Set the deployment variables and enable the repository flag after state migration and identity checks succeed.

   | Variable | Value |
   | --- | --- |
   | AWS_ACCOUNT_ID | Deployment account ID |
   | AWS_DEPLOY_ROLE_ARN | Dedicated GitHub OIDC role ARN |
   | TF_STATE_BUCKET | Private state bucket |
   | TF_STATE_KEY | Migrated application-state key |
   | AWS_DEPLOY_ENABLED | Repository variable set to true when ready |

7. Run promotion from main using a successful release run ID and confirmed AWS activation/service access.

The job verifies release provenance, checks existing table/parameter/state metadata, pulls the Lambda image by digest, verifies its revision label and runs the Lambda emulator before promotion to ECR. Terraform applies a saved plan restricted to the known Lambda image update. Creates, deletes, replacements and unrelated drift fail the guard.

The public smoke test checks routes, access denial and retrieval. Full tenant workflow acceptance is an explicit operation with current authorized credentials. The promotion expects an available endpoint. Local provider controls maintain private deployment records and support the paused workflow.

To roll back an image, select an earlier successful release with a retained manifest and use the same promotion workflow. Infrastructure/configuration changes require separate plan review.

## GCP deployment boundary

GCP uses `Dockerfile.gcp`, separate bootstrap/application Terraform roots and its Firestore dependency. Deployment runs through the browser-authenticated CLI configuration and ADC in `scripts/deploy_gcp.py`, invoked by the shared lifecycle controls.

CI builds the GCP image and runs the real Firestore emulator without cloud credentials. The Terraform job validates all four roots with readonly provider locks and backend access disabled. GitHub-to-GCP deployment identity and remote-state setup remain future configuration. A GitHub deployment workflow can use Workload Identity Federation when those components are established. [Google deployment pipeline federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)

## Local verification

The Python suite tests malformed manifests, repository/commit/run mismatches, mutable image references, fork/PR release rejection and destructive/unrelated Terraform plans. `actionlint` checks the workflows. Browser, Docker-stack and Lambda/Firestore validators are also available through the [validation guide](VALIDATION.md).

## Local Kubernetes verification

The Kubernetes CI job creates the isolated `ticketpilot-portfolio` kind cluster, deploys the application, Prometheus and Grafana, and validates the stack through localhost forwards. It checks probes, limits, workflow behavior, monitoring and PVC persistence. Cleanup deletes the verified owned cluster even after a failure. Only the allowlisted validation summary is uploaded.

This job runs Kubernetes on the GitHub runner's local Docker engine. Application cloud hosting uses Lambda or Cloud Run, and the kind job has no cloud deployment identity. [Kubernetes configuration](KUBERNETES.md)

## References

- [GitHub Actions usage and billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub Container Registry billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [Terraform S3 state and locking](https://developer.hashicorp.com/terraform/language/backend/s3)
