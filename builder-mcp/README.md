# builder-mcp — the Cornell Builder (Track A)

The MCP server that turns plain-language intent into governed deployments: search the
blueprint catalog, create a deployment (new repo + registration PR), and operate what you
deployed. **Merge is the only deploy trigger** — no tool here deploys anything directly,
and the builder's client never holds a git or AWS credential.

Start here, in order: [`SPEC.md`](SPEC.md) (contracts C1–C7 — the agreements that must
not drift), [`aidlc-docs/PROJECT-KNOWLEDGE.md`](aidlc-docs/PROJECT-KNOWLEDGE.md)
(decision log, gotchas, glossary), [`deploy/HANDOFF.md`](deploy/HANDOFF.md) (deployment
runbook). Inception artifacts live in [`aidlc-docs/`](aidlc-docs/aidlc-state.md).

## Tools

| Tool | What it does | Mutates? |
|---|---|---|
| `blueprint_search` | Rank the catalog against a plain-language ask; returns each blueprint's full contract | no |
| `create_deployment` | New org repo (thin shell, pinned blueprint version) + registration PR adding the pipeline action | `dry_run` first |
| `deployment_status` | Registration PR → pipeline stages → stack status, the whole chain | no |
| `propose_change` | Turn file changes into a PR on a deployment repo — never a push | `dry_run` first |
| `health_check` | Stack health + failure events + cornell:* tag inventory audit | no |
| `restart_deployment` | Retry failed pipeline stage / re-run at current version. Never a version change | `dry_run` first |
| `export_spec` | Render the deployment spec for an audience: coder, narrative, security, transfer, user, offboarding | no |

Confirm-before-doing UX: mutating tools default to `dry_run=true` and return the full plan.
(MCP elicitation is unavailable on stateless transports, which AgentCore requires — the
dry-run pattern works everywhere.)

## Run locally

```sh
cd builder-mcp
uv run builder-mcp                 # streamable HTTP on http://127.0.0.1:8000/mcp
```

Connect from Claude Code:

```sh
claude mcp add --transport http cornell-builder http://127.0.0.1:8000/mcp
```

Tests: `uv run pytest -q` (also run repo-level `tools/check` before pushing).

## Configuration (all env vars, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | *(unset)* | Server-side GitHub credential. Unset → write tools return dry-run plans. GitHub App installation is the P1 target (D3) |
| `BUILDER_MCP_GITHUB_ORG` | `cu-aaii` | Org for deployment repos |
| `BUILDER_MCP_WORKSHOP_REPO` | `ai-dlc-workshop` | Repo the pipeline tracks |
| `BUILDER_MCP_APPLICATION` / `BUILDER_MCP_ENVIRONMENT` | `aidlc` / `main` | Stack-name prefix `<app>-<env>-<name>` |
| `AWS_REGION` | `us-east-1` | All AWS reads |
| `BUILDER_MCP_REPO_ROOT` | auto-detected | Catalog source; unset off-repo → catalog is fetched from GitHub |
| `BUILDER_MCP_TRANSPORT` | `streamable-http` | `stdio` for local stdio use |
| `BUILDER_MCP_HOST` / `BUILDER_MCP_PORT` | `127.0.0.1` / `8000` | Bind address |
| `BUILDER_MCP_STATELESS` | off | Set `1` on AgentCore (no session affinity) |

## AWS access is read-mostly by design

The AWS surface is: CloudFormation describe*, CodePipeline get/state, Resource Groups
Tagging get-resources, plus exactly two writes — `StartPipelineExecution` and
`RetryStageExecution` — which can only re-run what the tracked branch already defines.
The server cannot create, update, or delete stacks; that permission belongs to the
pipeline's role, and the pipeline acts only on merge.

## Deploying to Bedrock AgentCore

**Merge deploys — same as every blueprint.** The pipeline's Build stage builds the
`builder-mcp` target of the repo-root `Dockerfile` (linux/arm64) and the BlueprintDeploy
stage deploys [`infra/builder-mcp.yml`](infra/builder-mcp.yml) with the image pinned by
digest. Runbook and review points: [`deploy/HANDOFF.md`](deploy/HANDOFF.md); post-deploy
proof: `uv run python deploy/verify.py`.
