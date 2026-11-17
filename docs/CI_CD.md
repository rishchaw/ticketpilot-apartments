# CI/CD for TicketPilot Apartments

The public repository is `rishchaw/ticketpilot-apartments`. Publish the **contents of ticketpilot-aws as the repository root**, including its `.github` directory. The parent ticketpilot-ai folder contains separate projects; publishing the whole parent would put this project's workflows in a nested folder that GitHub does not run.

GitHub stores the source, runs the checks and publishes container images. It does not host the FastAPI application through GitHub Pages. The public tenant HTTPS address requires application hosting: AWS activation still blocks the AWS path, while the separately deployed GCP Cloud Run/Firestore service is currently paused to save costs. See [GCP deployment](GCP_DEPLOYMENT.md) and [observed status](DEPLOYMENT_STATUS.md).

## Three workflows

| Workflow | Trigger | Result |
| --- | --- | --- |
| TicketPilot CI (`ci.yml`) | Push to main, pull request, manual run, reusable workflow call | Tests and JUnit, English/Filipino browser workflow, synthetic legacy evaluation, Docker/Prometheus/Grafana checks, Lambda runtime emulator, GCP container/Firestore emulator, local kind Kubernetes/monitoring acceptance, AWS/GCP Terraform format/validation |
| TicketPilot container release (`release.yml`) | Manual run from the default branch | Reuses CI, builds and tests the exact app/Lambda images, pushes to GHCR and records digest/commit/run provenance plus a source archive |
| TicketPilot AWS promotion (`deploy-aws.yml`) | Manual run with a successful release run ID | Disabled until explicitly configured; verifies provenance, uses OIDC and remote Terraform state, promotes only an existing Lambda image and runs public apartment checks |

CI has read-only repository permissions and no cloud credentials. Only the release publisher can write packages; only the AWS deployment job can request an OIDC token. Actions are pinned to commit IDs. Obsolete CI runs are canceled, jobs have timeouts, and evidence artifacts are retained for three days (seven for release manifests/source). Dependabot proposes grouped weekly action/Python updates.

The normal CI path makes no AWS calls and no paid model calls. The apartment browser test uses a separate fictional-data database, a temporary server and test-only access codes. Artifacts use an explicit allowlist of JSON/JUnit summaries and fictional screenshots. The workflow never uploads the full .tools directory, .env, .secrets, databases, Terraform state, or saved plans.

## First GitHub run

1. Authenticate with the intended GitHub account through the plugin or the official GitHub CLI browser flow. No passwords or access tokens need to be pasted into chat. Publishing workflows needs repository and workflow-write permission.
2. Create the standalone public repository and push its main branch. CI starts automatically. Confirm all five jobs pass in Actions before claiming GitHub validation succeeded.
3. Run **TicketPilot container release** from main when you want a tested deliverable. Releases are manual to avoid rebuilding/publishing containers on every small change.
4. Read the release summary and download `release-manifest` if needed. The manifest binds immutable image digests to the repository, commit and workflow run. Commit-addressed tags also include run/attempt IDs; deployments use digests because tags can move.

GHCR images are `ghcr.io/rishchaw/ticketpilot-apartments` and `ghcr.io/rishchaw/ticketpilot-apartments-lambda`. A new GHCR package may be private even when its source repo is public. Package visibility is a separate setting. The repository's GITHUB_TOKEN publishes/reads associated packages; do not add a personal access token merely to publish from this workflow.

## AWS promotion: configure only after activation

The AWS workflow updates an **already deployed** application. It deliberately does not perform initial provisioning, upload manager secrets, create billing plans, or enable Bedrock. First complete the reviewed Windows deployment in AWS_DEPLOYMENT.md after account activation, then configure CI state/authentication below. Keep `AWS_DEPLOY_ENABLED` unset or false while AWS Support resolves activation.

1. Create a private S3 bucket in Singapore for Terraform state. Enable versioning, encryption, and public-access blocking. Back up the existing application state privately before migration. Ordinary AWS storage/request charges can apply.
2. Add the following ignored file at `infra/aws/backend.ci.tf` locally:

   ```hcl
   terraform {
     backend "s3" {}
   }
   ```

3. Migrate the existing application state interactively, using the correct private bucket/key:

   ```powershell
   $env:AWS_PROFILE = 'ticketpilot'
   $env:AWS_REGION = 'ap-southeast-1'
   terraform -chdir=infra/aws init -migrate-state -backend-config='bucket=YOUR-PRIVATE-STATE-BUCKET' -backend-config='key=ticketpilot-aws/app/terraform.tfstate' -backend-config='region=ap-southeast-1' -backend-config='encrypt=true' -backend-config='use_lockfile=true'
   terraform -chdir=infra/aws state list
   ```

   Confirm the state includes `aws_lambda_function.app` and `aws_dynamodb_table.tickets`. Do not enable CI against a fresh empty key when infrastructure already exists. The bootstrap ECR stack remains separately managed; migrate its state separately if you later automate that stack.

4. Create GitHub's OIDC provider in the AWS account and a dedicated deployment role. Generate/review its scoped policy during bootstrap. It needs project-scoped ECR promotion, Lambda/Terraform read/update access, private S3 state/lock access, and parameter metadata checks. Do not grant AdministratorAccess or store static AWS access keys in GitHub. CI never reads SSM parameter values.
5. Create the GitHub environment **aws-demo**. Restrict its deployment branches to **main**. Add a reviewer if your GitHub plan supports that feature. The environment restriction matters because its OIDC subject identifies the environment, not the branch.
6. Bind the role trust to `aud=sts.amazonaws.com` and the exact subject `repo:rishchaw/ticketpilot-apartments:environment:aws-demo`, not a wildcard repository. See the official GitHub AWS OIDC guide linked below.
7. Configure these non-secret variables in the aws-demo environment, then set the repository-level enable flag only when setup and service access are confirmed:

   | Variable | Value |
   | --- | --- |
   | AWS_ACCOUNT_ID | Verified twelve-digit account ID |
   | AWS_DEPLOY_ROLE_ARN | Dedicated GitHub OIDC deployment role ARN |
   | TF_STATE_BUCKET | Private state bucket |
   | TF_STATE_KEY | Existing migrated application-state key |
   | AWS_DEPLOY_ENABLED | Repository variable: true only when deployment is ready |

8. Run AWS promotion from main with a successful container-release run ID and explicitly confirm activation. The selected release must belong to this repository/default branch and pass the strict manifest checks. Expired/deleted manifest artifacts require a new release run.

The deploy job checks existing table/SSM metadata/state, pulls the Lambda image by digest, verifies its revision label, runs the local Lambda emulator, and copies the same manifest into ECR. Terraform uses S3 locking and a saved local plan. The plan guard permits only a known existing Lambda image update; creates, deletes, replacements, unrelated drift and configuration changes are rejected. Review infrastructure changes separately rather than bypassing the guard. Bedrock configuration is not automatically enabled or altered.

The public smoke check checks apartment pages/configuration and access denial plus legacy retrieval; it creates no live tenant records. Full acceptance still includes an authorized manager/tenant test as described in AWS_DEPLOYMENT.md. A successful container release alone is not an AWS deployment. Prometheus/Grafana stay local, and AWS-only monitoring does not aggregate apartment counters across Lambda environments.

To roll back an image, select an earlier successful release with a retained manifest and run the same manual promotion. The existing-state and image-only rules still apply. If configuration changed since that release, stop and review infrastructure/state instead.

## GCP deployment boundary

GCP uses its own Terraform bootstrap/application roots and `Dockerfile.gcp` with the optional Firestore dependency. The Cloud Run image must be built from that Dockerfile; the existing GHCR app/Lambda release is not automatically a Firestore-enabled release. Local GCP deployment uses the browser-authenticated `ticketpilot-gcp` CLI configuration and ADC through `scripts/deploy_gcp.py`. No GCP MCP connection, GitHub service-account key, GCP remote-state bucket or GitHub-to-GCP deployment identity has been installed by this setup.

The GCP Terraform roots have been validated locally with Google provider locks for Linux and Windows. CI now includes a fourth credential-free job that builds `Dockerfile.gcp`, runs the isolated Firestore emulator validator and retains allowlisted GCP metadata/validation reports for three days. Its Terraform job validates all four AWS/GCP roots with readonly provider locks and no cloud backend. Hosted GCP checks passed in run 43913020484; CI configuration, local validation and actual deployment remain separate evidence. The current AWS promotion workflow does not deploy to GCP. A future manual GCP promotion can use GitHub OIDC through Workload Identity Federation after remote-state and deployment permissions are deliberately configured; do not upload a long-lived service-account JSON key to GitHub. See [Google's deployment pipeline federation guide](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

Prometheus/Grafana stay in local Compose, and the GCP profile disables paid AI calls and automatic manager polling. GitHub runner allowances do not cover Cloud Run, Firestore, image storage or other application-hosting usage. The optional USD 10 GCP budget sends alerts only; it does not enforce a project-wide cost ceiling.

## Local verification

`actionlint` checks all workflow files. The Python suite covers malformed manifests, wrong repository/commit/run provenance, fork/PR releases, mutable image references, and destructive/unrelated Terraform plans. The existing real-browser, Docker-stack and Lambda-emulator validators remain runnable without GitHub or AWS. Hosted GitHub execution must be observed separately; local checks do not establish that external permissions work.

## Free platform choices

GitHub Actions fits this repository: standard GitHub-hosted runners are free for public repositories. Current GitHub Free private-repository compute is expressed as a monthly monetary allowance, not a guaranteed fixed minute count. GitLab Free provides 400 compute minutes per namespace per month and may require identity verification. CircleCI Free includes 30,000 credits, with usable minutes depending on executor size. CI/CD allowances do not make application hosting free.

Official references:

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub included usage](https://docs.github.com/en/billing/reference/product-usage-included)
- [GitHub Container Registry billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [Terraform S3 backend and state locking](https://developer.hashicorp.com/terraform/language/backend/s3)
- [GitLab compute minutes](https://docs.gitlab.com/ci/pipelines/compute_minutes/)
- [CircleCI pricing](https://circleci.com/pricing/)

## Local Kubernetes verification

The additional credential-free Kubernetes CI job installs checksum-verified kind 0.33.0 and kubectl 1.36.1, creates only the isolated ticketpilot-portfolio kind cluster, deploys the application/Prometheus/Grafana manifests, and runs real acceptance through localhost forwards. Cleanup runs even after failures and deletes only its verified owned demonstration cluster. The only Kubernetes artifact is .tools/kubernetes-validation.json, retained for three days. No kubeconfig, Secrets, tenant databases or raw pod logs are uploaded.

This job uses local Docker compute on the GitHub runner. It has no GCP/AWS deployment identity, does not create GKE/EKS infrastructure and does not resume the paused Cloud Run site. See [the local Kubernetes guide](KUBERNETES.md). Check actual Actions results for the new job before claiming hosted Kubernetes success.
