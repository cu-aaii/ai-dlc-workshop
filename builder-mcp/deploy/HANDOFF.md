# Deployment Handoff — builder-mcp → AgentCore

For whoever deploys (Marty): everything is verified locally and parameterized; nothing
here assumes the author's machine or credentials. AWS reference:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html

## What you're deploying

One CloudFormation stack, `aidlc-main-builder-mcp`, from
[`infra/builder-mcp.yml`](../infra/builder-mcp.yml) (registered in `pipeline/stacks.yml`
as `deployed_by: manual`). It creates: ECR repo → Cognito user pool/domain/resource
server/client (OAuth client-credentials authorizer) → execution role (read-mostly; see
SPEC C5) → AgentCore Runtime (arm64 container, MCP protocol, JWT authorizer). Every
resource carries the four `cornell:*` tags.

## Pre-flight (one-time)

1. **GitHub credential** (optional but needed for repo/PR creation): create an org-scoped
   fine-grained PAT and store it:
   ```sh
   aws secretsmanager create-secret --name aidlc/main/builder-mcp/github-token --secret-string '<token>' --region us-east-1
   ```
   Without it the server runs fine; GitHub write tools return dry-run plans.
2. Docker with buildx (arm64), or any builder that produces `linux/arm64` images.

## Deploy

Scripted (PowerShell): [`deploy.ps1`](deploy.ps1) — pass `-Owner <netid>`. It is nothing
but the three steps below; if your own system replaces it, match these:

1. **Base stack** — `aws cloudformation deploy` with `ContainerImageUri=` (empty) →
   creates ECR/Cognito/role. Stack-level tags: the four `cornell:*` values.
2. **Image** — `docker buildx build --platform linux/arm64 -t <RepositoryUri>:latest --push .`
   from `builder-mcp/` (RepositoryUri is a stack output).
3. **Runtime** — same deploy command with `ContainerImageUri=<RepositoryUri>:latest`.

## Verify ("snazzy" check)

```sh
uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1
```

Fetches the Cognito client secret, gets a client-credentials token, does the MCP
handshake against the runtime endpoint, lists all seven tools, and makes a live
`blueprint_search` call. Success ends with `VERIFIED: the Cornell Builder is live on
AgentCore`.

Connect a Claude client: token from the Cognito token endpoint (stack output), then add
an HTTP MCP server at
`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<urlencoded-runtime-arn>/invocations?qualifier=DEFAULT`
with header `Authorization: Bearer <token>`.

## Known limitations / open items

- Inbound auth is Cognito client-credentials (assumed answer to P2 in
  [`../aidlc-docs/construction/agentcore-productionizing-questions.md`](../aidlc-docs/construction/agentcore-productionizing-questions.md));
  Entra ID is the P1 target. P1/P3/P6 answers may adjust this stack.
- The catalog is fetched from the GitHub repo when running off-repo — unauthenticated
  GitHub API calls are rate-limited (60/hr/IP); the token secret also fixes this.
- Teardown: delete the stack; ECR images and the Cognito domain go with it. Nothing else
  was created outside CloudFormation.
