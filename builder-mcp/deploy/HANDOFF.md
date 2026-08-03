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
| `aidlc-main-builder-mcp` stack | Cognito client-credentials authorizer, read-mostly execution role, AgentCore Runtime (MCP protocol, JWT authorizer) — every resource `cornell:*`-tagged |

Pipeline-order note: `PipelineDeploy` applies the new pipeline definition first and
`RestartExecutionOnUpdate` reruns from the top, so the first merge picks up the new
stages on its own — no console action needed.

## Pre-merge review points (the things worth a human's attention)

1. **`AWS::BedrockAgentCore::Runtime` + `AWS::Cognito::*` via `cloudformation-deploy-role`**
   — confirm that role's policy covers `bedrock-agentcore:*` and `cognito-idp:*`; it
   predates AgentCore.
2. **Runtime name** is `aidlc_main_builder_mcp` (AgentCore takes underscores, not hyphens).
3. Assumed answers baked in: Cognito client-credentials inbound auth (P2-⭐), Runtime-only
   topology (P1-⭐) — see `../aidlc-docs/construction/agentcore-productionizing-questions.md`.

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

OAuth token → MCP handshake → lists all seven tools → live `blueprint_search` call →
`VERIFIED: the Cornell Builder is live on AgentCore`.

Connect a Claude client: token from the stack's `TokenEndpoint` output
(client-credentials, scope `cornell-builder/invoke`), MCP URL
`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<urlencoded RuntimeArn>/invocations?qualifier=DEFAULT`,
header `Authorization: Bearer <token>`.

## Debugging fallback

The template deploys by hand like any blueprint (repo convention): `aws cloudformation
deploy` with `ContainerImageUri=` empty deploys everything except the runtime; pass any
pushed image URI to add it. Local image check:
`docker buildx build --platform linux/arm64 --target builder-mcp .` from the repo root.

## Teardown

Delete stack `aidlc-main-builder-mcp` (Cognito domain included). Remove the Build-stage
action + stacks.yml entry in a PR to stop rebuilding. Images live in the shared
`aidlc-main` ECR repo and age out by its lifecycle policy.
