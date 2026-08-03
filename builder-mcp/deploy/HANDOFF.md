# Deployment Handoff — builder-mcp → AgentCore

**The deployment method is the repo's own pipeline.** Nothing here is deployed by hand:
merging this branch's PR to `main` makes the webhook fire, the `Build` stage build the
arm64 image from the root `Dockerfile` (target `builder-mcp`), and the `BlueprintDeploy`
stage deploy [`../infra/builder-mcp.yml`](../infra/builder-mcp.yml) with the image pinned
by digest. AWS reference:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html

## What the merge deploys

| Piece | Where |
|---|---|
| ARM CodeBuild project (`aidlc-main-container-arm`) | `pipeline/pipeline.yml` — additive; the x86 reference project is untouched |
| `Build` stage → `BuilderMcpContainer` action | exports `CONTAINER_DIGEST` per `pipeline/codebuild.yml` |
| `aidlc-main-builder-mcp` stack | Entra ID JWT authorizer on the runtime, read-mostly execution role, AgentCore Runtime (MCP protocol) — every resource `cornell:*`-tagged |

Pipeline-order note: `PipelineDeploy` applies the new pipeline definition first and
`RestartExecutionOnUpdate` reruns from the top, so the first merge picks up the new
stages on its own — no console action needed.

## Required pre-flight (one-time, before the merge)

Inbound auth is **Microsoft Entra ID client-credentials** (platform-lead directive,
2026-08-03). The app registration is an Azure resource: the repo's Terraform-for-Azure
stage is deliberately not built, so it is created **by hand on the Microsoft side** and
its identifiers reach the stack via SSM parameters — the same hand-created-then-referenced
pattern as the CodeConnections ARN (`/code-connections/cu-aaii`).

### (a) Azure side — Entra app registration

1. Create an app registration (suggested name: `cornell-builder-mcp`) in the Cornell
   tenant. Record the **Directory (tenant) ID** and the **Application (client) ID**.
2. Create a **client secret** for it. Record the secret *value* (shown once).
3. Under *Expose an API*, set the **Application ID URI** to the default
   `api://<client-id>` form — the runtime's JWT authorizer validates the token `aud`
   against exactly that value.

### (b) AWS side — SSM parameters + Secrets Manager secret

The stack reads the tenant and client ids from SSM at deploy time; the client secret is
used only by callers (verify.py, Claude clients) and lives in Secrets Manager:

```sh
aws ssm put-parameter --name /entra/builder-mcp/tenant-id --type String --value '<tenant-id>' --region us-east-1
aws ssm put-parameter --name /entra/builder-mcp/client-id --type String --value '<client-id>' --region us-east-1
aws secretsmanager create-secret --name aidlc/main/builder-mcp/entra-client-secret --secret-string '<client-secret-value>' --region us-east-1
```

Ids are not secrets, so plain `String` parameters are fine; the secret value goes only to
Secrets Manager, never to SSM, never to this repo (public, no secret scanning).

## Pre-merge review points (the things worth a human's attention)

1. **`AWS::BedrockAgentCore::Runtime` via `cloudformation-deploy-role`** — confirm that
   role's policy covers `bedrock-agentcore:*`; it predates AgentCore. `cognito-idp:*` is
   **no longer needed** (the Cognito resources are gone), but the role now needs
   **`ssm:GetParameters`** on `/entra/builder-mcp/*` so CloudFormation can resolve the
   `AWS::SSM::Parameter::Value<String>` parameters at deploy time.
2. **Runtime name** is `aidlc_main_builder_mcp` (AgentCore takes underscores, not hyphens).
3. Assumed answers baked in: Runtime-only topology (P1-⭐) — see
   `../aidlc-docs/construction/agentcore-productionizing-questions.md`. Inbound auth (P2)
   is now decided: Entra ID, platform-lead directive 2026-08-03.

## Optional pre-flight (any time, one-time)

GitHub credential for repo/PR creation — without it the server runs fine but its GitHub
write tools return dry-run plans:

```sh
aws secretsmanager create-secret --name aidlc/main/builder-mcp/github-token --secret-string '<org-scoped fine-grained PAT>' --region us-east-1
```

(The secret name is passed to the stack by the pipeline as
`<app>/<env>/builder-mcp/github-token`.)

## Verify after the pipeline goes green

```sh
cd builder-mcp
uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1
```

Entra token (client secret from `BUILDER_MCP_ENTRA_CLIENT_SECRET` or the Secrets Manager
secret above) → MCP handshake → lists all eight tools → live `blueprint_search` call →
`VERIFIED: the Cornell Builder is live on AgentCore`.

Connect a Claude client: POST the stack's `EntraTokenEndpoint` output
(`https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`) with
`grant_type=client_credentials`, `client_id` = the `EntraClientId` output,
`client_secret` = the Secrets Manager value, `scope=api://<client-id>/.default`; MCP URL
`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<urlencoded RuntimeArn>/invocations?qualifier=DEFAULT`,
header `Authorization: Bearer <token>`.

## Debugging fallback

The template deploys by hand like any blueprint (repo convention): `aws cloudformation
deploy` with `ContainerImageUri=` empty deploys everything except the runtime; pass any
pushed image URI to add it. The hand deploy resolves the same two SSM parameters, so the
pre-flight above must exist first. Local image check:
`docker buildx build --platform linux/arm64 --target builder-mcp .` from the repo root.

## Teardown

Delete stack `aidlc-main-builder-mcp`. Remove the Build-stage action + stacks.yml entry
in a PR to stop rebuilding. Images live in the shared `aidlc-main` ECR repo and age out
by its lifecycle policy. The Entra app registration, the two SSM parameters, and the
`entra-client-secret` secret are hand-created, so hand-remove them too.
