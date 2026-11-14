#!/usr/bin/env bash
# GitHub-hosted runner only. One-time infrastructure/state setup stays explicit.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true ]] || { echo 'Run this script through the configured GitHub deployment workflow.' >&2; exit 1; }
for name in AWS_ACCOUNT_ID TF_STATE_BUCKET TF_STATE_KEY RELEASE_COMMIT RELEASE_LAMBDA_REF; do
  [[ -n "${!name:-}" ]] || { echo "Missing $name" >&2; exit 1; }
done
[[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ && "$RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "${AWS_REGION:-}" == ap-southeast-1 ]]
[[ "$TF_STATE_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]
[[ "$TF_STATE_KEY" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$ && "$TF_STATE_KEY" != *..* ]]
[[ "$RELEASE_LAMBDA_REF" =~ ^ghcr.io/[a-z0-9._-]+/[a-z0-9._-]+-lambda@sha256:[0-9a-f]{64}$ ]]
account=$(aws sts get-caller-identity --query Account --output text)
[[ "$account" == "$AWS_ACCOUNT_ID" ]]
aws lambda get-account-settings >/dev/null
aws dynamodb describe-table --table-name ticketpilot-aws-tickets >/dev/null
# Read metadata, never parameter values. These must be created during first deployment.
for parameter in /ticketpilot-aws/admin-token /ticketpilot-aws/metrics-token; do
  count=$(aws ssm describe-parameters --parameter-filters "Key=Name,Option=Equals,Values=$parameter" --query 'length(Parameters)' --output text)
  [[ "$count" == 1 ]] || { echo 'Complete one-time application parameter setup first.' >&2; exit 1; }
done
aws s3api head-object --bucket "$TF_STATE_BUCKET" --key "$TF_STATE_KEY" --expected-bucket-owner "$AWS_ACCOUNT_ID" >/dev/null
repository=$(aws ecr describe-repositories --repository-names ticketpilot-aws --query 'repositories[0].repositoryUri' --output text)
[[ "$repository" == "$AWS_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/ticketpilot-aws" ]]
mkdir -p .tools
cat > infra/aws/backend.ci.tf <<'BACKEND'
terraform {
  backend "s3" {}
}
BACKEND
terraform -chdir=infra/aws init -input=false -lockfile=readonly -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="key=$TF_STATE_KEY" -backend-config='region=ap-southeast-1' -backend-config='encrypt=true' -backend-config='use_lockfile=true'
state_addresses=$(terraform -chdir=infra/aws state list)
printf '%s\n' "$state_addresses" | grep -Fx 'aws_lambda_function.app' >/dev/null
printf '%s\n' "$state_addresses" | grep -Fx 'aws_dynamodb_table.tickets' >/dev/null
# Pull by digest and verify the release commit before copying into ECR.
docker pull "$RELEASE_LAMBDA_REF"
revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RELEASE_LAMBDA_REF")
[[ "$revision" == "$RELEASE_COMMIT" ]]
python scripts/validate_lambda_image.py --image "$RELEASE_LAMBDA_REF"
registry="${repository%%/*}"
aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
tag="deploy-${RELEASE_COMMIT:0:12}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
docker tag "$RELEASE_LAMBDA_REF" "$repository:$tag"
docker push "$repository:$tag"
digest=$(aws ecr describe-images --repository-name ticketpilot-aws --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)
[[ "$digest" == "${RELEASE_LAMBDA_REF##*@}" ]] || { echo 'Copied registry manifest differs from the tested release; no app update applied.' >&2; exit 1; }
export TF_VAR_image_uri="$repository@$digest"
export TF_VAR_region=ap-southeast-1
plan_path="$GITHUB_WORKSPACE/.tools/deployment.tfplan"
terraform -chdir=infra/aws plan -input=false -lock-timeout=60s -out="$plan_path"
terraform -chdir=infra/aws show -json "$plan_path" > .tools/deployment-plan.json
python scripts/check_deployment_plan.py .tools/deployment-plan.json --image-uri "$TF_VAR_image_uri"
terraform -chdir=infra/aws apply -input=false -lock-timeout=60s "$plan_path"
service_url=$(terraform -chdir=infra/aws output -raw service_url)
python scripts/smoke_aws.py "$service_url"
{
  echo '### AWS image promotion completed'
  echo "Release commit: $RELEASE_COMMIT"
  echo "Image digest: $digest"
  echo "Tenant portal: ${service_url%/}/tenant"
  echo "Manager dashboard: ${service_url%/}/manager"
  echo 'Full tenant/manager acceptance still requires the manager access code; no live tenant records were created by the public smoke check.'
} >> "$GITHUB_STEP_SUMMARY"
