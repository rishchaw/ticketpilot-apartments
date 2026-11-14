param([string]$Region = 'ap-southeast-1', [string]$Profile = 'ticketpilot')
$ErrorActionPreference = 'Stop'
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousProfile = $env:AWS_PROFILE
$previousRegion = $env:AWS_REGION
Push-Location -LiteralPath $projectRoot
try {
    $env:AWS_PROFILE = $Profile
    $env:AWS_REGION = $Region
    foreach ($tool in @('aws', 'docker')) { Get-Command $tool -ErrorAction Stop | Out-Null }
    $terraformCommand = Get-Command terraform -ErrorAction SilentlyContinue
    $terraform = if ($terraformCommand) { $terraformCommand.Source } else { Join-Path $projectRoot '.tools/terraform.exe' }
    if (-not (Test-Path -LiteralPath $terraform)) { throw 'Install Terraform on PATH or at .tools/terraform.exe first.' }
    $python = Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements-dev.txt first; see README.md.' }
    Invoke-Checked $python @('scripts/preflight_aws.py', '--region', $Region, '--profile', $Profile)
    Invoke-Checked 'docker' @('info', '--format', '{{.ServerVersion}}')
    Invoke-Checked $python @('scripts/setup_local.py')
    Invoke-Checked $python @('scripts/upload_aws_secrets.py', '--region', $Region)
    Invoke-Checked $terraform @('-chdir=infra/bootstrap', 'init')
    Invoke-Checked $terraform @('-chdir=infra/bootstrap', 'apply', "-var=region=$Region")
    $repository = & $terraform '-chdir=infra/bootstrap' output -raw repository_url
    if ($LASTEXITCODE -ne 0) { throw 'Could not read ECR repository URL' }
    $registry = ($repository -split '/')[0]
    $password = & aws ecr get-login-password --region $Region
    if ($LASTEXITCODE -ne 0) { throw 'ECR authentication failed' }
    $password | & docker login --username AWS --password-stdin $registry
    if ($LASTEXITCODE -ne 0) { throw 'Docker login failed' }
    $password = $null
    $tag = 'build-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
    $image = "${repository}:$tag"
    Invoke-Checked 'docker' @('buildx', 'build', '--platform', 'linux/amd64', '--provenance=false', '--load', '-f', 'Dockerfile.lambda', '-t', $image, '.')
    Invoke-Checked 'docker' @('push', $image)
    $digest = & aws ecr describe-images --region $Region --repository-name ticketpilot-aws --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text
    if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Could not resolve image digest' }
    Invoke-Checked $terraform @('-chdir=infra/aws', 'init')
    Invoke-Checked $terraform @('-chdir=infra/aws', 'apply', "-var=region=$Region", "-var=image_uri=${repository}@$digest")
    Invoke-Checked $terraform @('-chdir=infra/aws', 'output', 'service_url')
} finally {
    $env:AWS_PROFILE = $previousProfile
    $env:AWS_REGION = $previousRegion
    Pop-Location
}