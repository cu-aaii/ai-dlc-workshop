# Deployment Handoff — builder-mcp → AgentCore

**The deployment method is the repo's own pipeline.** Nothing here is deployed by hand:
merging this branch's PR to `main` makes the webhook fire, the `Build` stage build the
arm64 image from `builder-mcp/Dockerfile` (target `builder-mcp`, build context
`builder-mcp/` via `CONTAINER_CONTEXT`), and the `BlueprintDeploy`
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

## Testing phase: AuthMode=open (current)

**The pipeline currently deploys the stack with `AuthMode=open`** (user directive
2026-08-04): the Entra JWT authorizer is **masked, not removed** — the full Entra
configuration stays in `infra/builder-mcp.yml` behind the `UseEntra` condition, and the
Entra pre-flight below is **not required** while open. An open-mode deploy has zero
pre-flight: no Azure app registration, no SSM parameters, no client secret.

**What "open" actually means — read this before the demo.** AgentCore has **no
unauthenticated inbound mode**. A runtime without an authorizer configuration falls back
to the service default, **AWS IAM SigV4** ("the default authentication and authorization
mechanism that works automatically without additional configuration" — AWS devguide,
`bedrock-agentcore/latest/devguide/runtime-oauth.html`; a runtime supports either SigV4
*or* JWT, never neither). So `AuthMode=open` means:

- Nobody logs in via Entra, and no token pre-flight exists — that part is real.
- But callers still need **AWS credentials** with `bedrock-agentcore:InvokeAgentRuntime`
  and must **SigV4-sign** every request. `verify.py` handles this automatically
  (`--no-auth`, auto-detected — it signs with the same credentials it already uses to
  read the stack).
- **Implication for Claude clients**: a plain bearer-token MCP client (Claude Code /
  Cowork pointed at a URL with an `Authorization` header) **cannot call the open cloud
  endpoint** — standard MCP HTTP clients do not SigV4-sign. The zero-login way to use
  the server conversationally remains the **local stdio path** (`.mcp.json`, see
  [LOCAL-TESTING.md](LOCAL-TESTING.md)). This is as publicly accessible as the platform
  allows.

**Restore checklist (flipping back to Entra):**

1. Do the pre-flight below (Azure app registration + client secret; then either raw ids
   or the SSM parameters, see step 2).
2. In `infra/builder-mcp.yml`, choose the parameter form: pass the **raw** tenant/client
   ids straight into `EntraTenantId` / `EntraClientId` (current plain-String form), or
   restore the stashed `AWS::SSM::Parameter::Value<String>` declarations (commented
   block marked STASHED in the template — delete the plain pair, uncomment the stashed
   pair; the SSM form needs the two `/entra/builder-mcp/*` SSM parameters to exist and
   `cloudformation-deploy-role` to hold `ssm:GetParameters` on them).
3. In `pipeline/pipeline.yml`, `BuilderMcpCloudFormation` → `ParameterOverrides`: set
   `"AuthMode": "entra"` and re-add the two Entra overrides (values per the form chosen
   in step 2 — the stashed overrides are in a comment right above the block).
4. Merge; then verify with `uv run python deploy/verify.py` (no `--no-auth` — it must
   report `OAUTH OK`).

## Stashed production path — Entra pre-flight (one-time, required only when AuthMode=entra)

Inbound auth for the **production path** is **Microsoft Entra ID client-credentials**
(platform-lead directive, 2026-08-03; masked for the testing phase, see the section
above). The app registration is an Azure resource: the repo's Terraform-for-Azure
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

The two SSM parameters are needed only if you restore the stashed SSM-valued parameter
form in `infra/builder-mcp.yml` (testing-phase default is plain-String parameters taking
the raw ids directly — see the restore checklist, step 2). The client secret is used
only by callers (verify.py, Claude clients) and lives in Secrets Manager:

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
   **no longer needed** (the Cognito resources are gone). `ssm:GetParameters` on
   `/entra/builder-mcp/*` is needed **only when the stashed SSM-valued parameter form is
   restored** (testing phase uses plain-String parameters, so no SSM resolution happens).
2. **Runtime name** is `aidlc_main_builder_mcp` (AgentCore takes underscores, not hyphens).
3. Assumed answers baked in: Runtime-only topology (P1-⭐) — see
   `../../../docs/aidlc/builder-mcp/construction/agentcore-productionizing-questions.md`.
   Inbound auth (P2) is now decided: Entra ID, platform-lead directive 2026-08-03.

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
cd packages/builder-mcp
uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1
```

**Testing phase (AuthMode=open)**: verify.py auto-detects the missing Entra outputs and
SigV4-signs with your AWS credentials (equivalent to passing `--no-auth`) — no Entra
setup needed. **Production path (AuthMode=entra)**: Entra token (client secret from
`BUILDER_MCP_ENTRA_CLIENT_SECRET` or the Secrets Manager secret above) → MCP handshake.
Either way it lists all eight tools, makes a live `blueprint_search` call, and prints
`VERIFIED: the Cornell Builder is live on AgentCore`.

Connect a Claude client (**entra mode only** — in open mode the endpoint requires SigV4,
which bearer-token MCP clients cannot do; use the local stdio path in LOCAL-TESTING.md
instead): POST the stack's `EntraTokenEndpoint` output
(`https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`) with
`grant_type=client_credentials`, `client_id` = the `EntraClientId` output,
`client_secret` = the Secrets Manager value, `scope=api://<client-id>/.default`; MCP URL
`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<urlencoded RuntimeArn>/invocations?qualifier=DEFAULT`,
header `Authorization: Bearer <token>`.

## Debugging fallback

The template deploys by hand like any blueprint (repo convention): `aws cloudformation
deploy` with `ContainerImageUri=` empty deploys everything except the runtime; pass any
pushed image URI to add it. In the testing-phase default (`AuthMode=open`, plain-String
Entra parameters) a hand deploy needs **zero pre-flight**; only the stashed SSM-valued
form resolves the two SSM parameters and therefore needs the pre-flight first. Local
image check:
`docker buildx build --platform linux/arm64 --target builder-mcp builder-mcp/` from the
repo root (or the same command with `.` as the context from inside `builder-mcp/`).

## Teardown

Delete stack `aidlc-main-builder-mcp`. Remove the Build-stage action + stacks.yml entry
in a PR to stop rebuilding. Images live in the shared `aidlc-main` ECR repo and age out
by its lifecycle policy. The Entra app registration, the two SSM parameters, and the
`entra-client-secret` secret are hand-created, so hand-remove them too.
