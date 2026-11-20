# AWS credentials and local tooling

The AWS deployment uses the `ticketpilot` CLI profile in Singapore, `ap-southeast-1`. Terraform and deployment scripts use local development credentials. The deployed application uses its scoped Lambda execution role. [AWS deployment](AWS_DEPLOYMENT.md) · [Operations](OPERATIONS_QUICKSTART.md)

## CLI browser sign-in

Install the official AWS CLI v2 with support for `aws login`, then authenticate the named profile.

```powershell
aws login --profile ticketpilot
aws sts get-caller-identity --profile ticketpilot --region ap-southeast-1
```

The launcher provides the same browser flow through **AWS controls → Sign in through browser**. Renew the session when required and verify the account before changing infrastructure.

Development credentials remain local. The Lambda runtime receives its own role for database access, runtime parameters and logging. Credential values stay outside source, container images and Terraform variables.

## Recommended local connection for Terraform

For compatibility with credential-process consumers, configure a separate `ticketpilot-terraform` profile that exports temporary credentials from the browser session.

```powershell
aws configure set credential_process 'aws configure export-credentials --profile ticketpilot --format process' --profile ticketpilot-terraform
aws configure set region ap-southeast-1 --profile ticketpilot-terraform
$env:AWS_PROFILE = 'ticketpilot-terraform'
$env:AWS_REGION = 'ap-southeast-1'
aws sts get-caller-identity
.\.venv\Scripts\python.exe scripts/preflight_aws.py
```

The bridge stores the export command in the profile configuration. Keep the AWS CLI on PATH and renew the source `ticketpilot` session when it expires. An existing working IAM Identity Center or temporary-credential profile can also be used.

The deployment identity needs ECR image/repository access, Lambda function/URL and resource-policy management, DynamoDB table/index management, CloudWatch Logs, SSM parameter setup, scoped role/policy creation and permission to pass the runtime role. Terraform also requires the corresponding read/list/tag/delete operations. The runtime identity is separately restricted in `infra/aws`.

## Optional AWS MCP connection

AWS MCP can provide additional account inspection, documentation and resource tooling to compatible development clients. Its connection has its own IAM authorization. Terraform and Docker continue to use their configured local credential providers for deployment.

Configure an optional MCP client through the official AWS setup documentation and verify the selected account/profile before using account-changing tools. The project deployment workflow operates through the CLI and Terraform scripts.

- [AWS CLI sign-in and credential-process sharing](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
- [AWS MCP setup](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/getting-started-aws-mcp-server.html)
- [AWS MCP OAuth permissions](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/oauth-authentication.html)

## Host exporter for Windows login profiles

A Windows credential process must run on the Windows host. For the optional CloudWatch exporter, start the Python process from the repository root using the authenticated profile.

```powershell
$env:AWS_PROFILE = 'ticketpilot'
$env:AWS_REGION = 'ap-southeast-1'
.\.venv\Scripts\python.exe monitoring/cloudwatch_exporter.py
```

In another terminal, select the host-exporter scrape configuration and start the local dashboards.

```powershell
$env:PROMETHEUS_CONFIG = './monitoring/prometheus/aws-host.yml'
docker compose up -d prometheus grafana
```

The exporter exposes aggregate service metrics on port 9101 for Docker Desktop through `host.docker.internal`. Stop the foreground exporter with Ctrl+C. The Grafana and Prometheus ports bind to localhost.

The normal provider monitoring action is available through `TICKETPILOT.cmd`. See [monitoring operations](OPERATIONS_QUICKSTART.md#monitor-a-deployment) for target selection and scrape health.
