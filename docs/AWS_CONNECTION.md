# Connect AWS for development and deployment

The project can be written and tested without an AWS account. Live validation and deployment require an authenticated AWS identity allowed to manage the resources in `infra/`. No passwords, root access keys, or secret keys need to be pasted into chat.

## Agent Toolkit setup completed in this workspace

AWS CLI 2.39.6 was installed using AWS's signed Windows user installer. Browser sign-in and STS identity verification succeeded for profile `ticketpilot`, with Singapore (`ap-southeast-1`) as its default region. The current browser session uses the account's root identity; no static access keys were created.

The official Agent Toolkit installed 25 default skills and registered AWS MCP for Codex, Claude Code, and Cursor. Each generated entry has `AWS_MCP_PROXY_PROFILES=ticketpilot`; generated launch commands and arguments were preserved. The toolkit service and its generated MCP endpoint use `us-east-1`. That does not change the project's Singapore deployment region. Remote skill-catalog access was verified successfully.

Restart the coding client to load the new MCP server and skills. The MCP tool connection must be checked in that new session. Terraform/SDK authentication and cloud deployment still need their own validation. The manual alternatives below are reference instructions; do not overwrite the existing `ticketpilot` login profile when adding a credential-process bridge.

To use another AWS account later, run `aws login --profile <name>`, add that profile name to the space-separated `AWS_MCP_PROXY_PROFILES` list in each MCP configuration file, and restart the coding tool.

## Recommended local connection for Terraform

Install the current [AWS CLI v2 for Windows](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), then sign in using your console identity:

```powershell
aws login --profile ticketpilot
aws sts get-caller-identity --profile ticketpilot
```

Complete the browser login yourself. AWS documents `aws login` as a way to use temporary console-derived credentials, with automatic refresh during the session. Use a development IAM identity rather than creating root access keys. Do not set up AWS Organizations merely to enable SSO: joining an organization can affect Free plan eligibility.

For broad compatibility with Terraform and SDK credential providers, use AWS's documented credential-process bridge. The following commands write two settings to the named local `ticketpilot` profile; they do not store the temporary keys in the config file:

```powershell
aws configure set credential_process 'aws configure export-credentials --profile ticketpilot --format process' --profile ticketpilot-terraform
aws configure set region ap-southeast-1 --profile ticketpilot-terraform
$env:AWS_PROFILE = 'ticketpilot-terraform'
$env:AWS_REGION = 'ap-southeast-1'
aws sts get-caller-identity
.\.venv\Scripts\python.exe scripts/preflight_aws.py
```

Keep the AWS CLI on PATH. Re-run `aws login --profile ticketpilot` when the session expires. If you already have a working IAM Identity Center or temporary-credential profile, use it instead of replacing it.

The authenticated deployment identity needs ECR repository/image permissions, Lambda function/URL and resource-policy management, DynamoDB table/index management, CloudWatch Logs management, SSM token parameter read/write, and permission to create the scoped execution role/policy and pass it to Lambda. Terraform also needs the corresponding read/list/tag/delete permissions. Read-only MCP access will not deploy the project. Runtime permissions are separately scoped in Terraform.

## Optional AWS MCP connection

An MCP server is useful for account inspection, AWS documentation, resource management, logs, and post-deployment checks. It does not replace Terraform's local AWS credential provider or Docker's image build/push access.

The official AWS MCP endpoint in Singapore is:

```text
https://aws-mcp.ap-southeast-1.api.aws/mcp?oauth=initialize
```

For a Codex CLI/Desktop client with remote MCP OAuth support, register and authenticate it:

```powershell
codex mcp add aws-mcp --url 'https://aws-mcp.ap-southeast-1.api.aws/mcp?oauth=initialize'
codex mcp login aws-mcp
```

The first command changes the client's MCP configuration. The second starts the user-controlled AWS sign-in flow. The connecting IAM identity needs the AWS MCP OAuth permissions described in AWS's setup guide (the managed policy `AWSMCPSignInOAuthAccessPolicy` covers OAuth sign-in), plus permissions for the AWS actions requested. OAuth sign-in alone grants no extra resource permissions. Reconnect/restart the client if it does not discover the newly connected tools immediately.

This project's plugin search found an AWS analytics connector, but its advertised analytics capabilities are not a substitute for Lambda/IAM/Terraform deployment access. Use the official AWS MCP server or the CLI profile above.

## Host exporter for Windows login profiles

The Linux exporter container cannot execute Windows AWS CLI credential processes. Run it directly on your signed-in Windows host instead:

```powershell
$env:AWS_PROFILE = 'ticketpilot'
$env:AWS_REGION = 'ap-southeast-1'
.\.venv\Scripts\python.exe monitoring/cloudwatch_exporter.py
```

Then, in another terminal:

```powershell
$env:PROMETHEUS_CONFIG = './monitoring/prometheus/aws-host.yml'
docker compose up -d prometheus grafana
```

This exposes the exporter on port 9101 for Docker Desktop to reach through `host.docker.internal`. Keep it on a trusted development machine; it exposes aggregate service metrics. Stop it with Ctrl+C when finished. The main Grafana and Prometheus ports bind only to localhost.

## Sources

- [User-requested Agent Toolkit setup workflow](https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/refs/heads/main/setup-instructions/setup.md)
- [AWS CLI console sign-in and credential-process sharing](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
- [Official AWS MCP setup, supported regions and Codex registration](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/getting-started-aws-mcp-server.html)
- [AWS MCP OAuth permissions](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/oauth-authentication.html)
- [OpenAI documentation for MCP configuration and login](https://learn.chatgpt.com/docs/extend/mcp?surface=app)

## Python deployment-tool dependency

Local scripts that use an `aws login` profile require Boto3 1.41+ with its CRT extra. `requirements-dev.txt` now includes `boto3[crt]>=1.41,<2`. For this existing uv-created environment, install with `uv pip install --python .venv/Scripts/python.exe "boto3[crt]>=1.41,<2"`; fresh pip-based environments can install the normal development requirements. The Lambda runtime uses its execution role and does not need browser-login CRT dependencies.

An expired refresh token still requires a new browser login; installing CRT does not renew credentials or activate restricted AWS services. See the [official Boto3 console-login guidance](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html#login-with-console-credentials).

