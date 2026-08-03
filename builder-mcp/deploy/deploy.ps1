# Deploy builder-mcp to Bedrock AgentCore -- two-phase, template-driven.
#
# Workshop expedient: run by hand with the presenter's AWS CLI (needs `aws sso login`
# first). Everything still goes through the registered CloudFormation template
# (infra/builder-mcp.yml), so the CLI deploy and the future pipeline action stay in
# lockstep -- this script is `aws cloudformation deploy` plus a docker push, nothing more.
#
#   Phase 1  deploy stack without an image -> ECR repo, Cognito authorizer, runtime role
#   Phase 2  docker buildx build --platform linux/arm64, push to the repo from phase 1
#   Phase 3  redeploy with ContainerImageUri -> the AgentCore runtime itself
#
# Then verify with:  uv run python deploy/verify.py

param(
    [string]$Application = 'aidlc',
    [string]$Environment = 'main',
    [string]$Owner = 'tmf77',
    [string]$BlueprintVersion = '0.1.0',
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)   # builder-mcp/

$StackName = "$Application-$Environment-builder-mcp"
$Tags = @(
    "cornell:owner=$Owner",
    "cornell:blueprint=builder-mcp",
    "cornell:blueprint-version=$BlueprintVersion",
    "cornell:deployment-id=$StackName"
)

Write-Host "== Phase 1: base stack (ECR, Cognito, role) =="
aws cloudformation deploy `
    --region $Region `
    --stack-name $StackName `
    --template-file infra/builder-mcp.yml `
    --capabilities CAPABILITY_NAMED_IAM `
    --no-fail-on-empty-changeset `
    --tags $Tags `
    --parameter-overrides Application=$Application Environment=$Environment Owner=$Owner BlueprintVersion=$BlueprintVersion ContainerImageUri=
if ($LASTEXITCODE -ne 0) { throw "phase 1 failed" }

$RepoUri = aws cloudformation describe-stacks --region $Region --stack-name $StackName `
    --query "Stacks[0].Outputs[?OutputKey=='RepositoryUri'].OutputValue" --output text
Write-Host "ECR repository: $RepoUri"

Write-Host "== Phase 2: build and push linux/arm64 image =="
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin ($RepoUri.Split('/')[0])
if ($LASTEXITCODE -ne 0) { throw "ecr login failed" }
$ImageUri = "${RepoUri}:latest"
docker buildx build --platform linux/arm64 -t $ImageUri --push .
if ($LASTEXITCODE -ne 0) { throw "image build/push failed" }

Write-Host "== Phase 3: runtime =="
aws cloudformation deploy `
    --region $Region `
    --stack-name $StackName `
    --template-file infra/builder-mcp.yml `
    --capabilities CAPABILITY_NAMED_IAM `
    --no-fail-on-empty-changeset `
    --tags $Tags `
    --parameter-overrides Application=$Application Environment=$Environment Owner=$Owner BlueprintVersion=$BlueprintVersion ContainerImageUri=$ImageUri
if ($LASTEXITCODE -ne 0) { throw "phase 3 failed" }

Write-Host "== Outputs =="
aws cloudformation describe-stacks --region $Region --stack-name $StackName `
    --query "Stacks[0].Outputs" --output table

Write-Host ""
Write-Host "Verify with:"
Write-Host "  uv run python deploy/verify.py --stack $StackName --region $Region"
