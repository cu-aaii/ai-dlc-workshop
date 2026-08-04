# builder-mcp — the Cornell Builder (Track A)

The MCP server that turns plain-language intent into governed deployments: search the
blueprint catalog, create a deployment (new repo + registration PR), and operate what you
deployed. **Merge is the only deploy trigger** — no tool here deploys anything directly,
and the builder's client never holds a git or AWS credential.

Start here, in order: [`SPEC.md`](SPEC.md) (contracts C1–C7 — the agreements that must
not drift), [`PROJECT-KNOWLEDGE.md`](../../docs/aidlc/builder-mcp/PROJECT-KNOWLEDGE.md)
(decision log, gotchas, glossary), [`deploy/HANDOFF.md`](deploy/HANDOFF.md) (deployment
runbook). The AI-DLC artifacts that produced this package are a historical record at
[`docs/aidlc/builder-mcp/`](../../docs/aidlc/builder-mcp/aidlc-state.md).

## Tools

Names follow noun_verb (SPEC C3): the resource first, then the operation.

| Tool | What it does | Mutates? |
|---|---|---|
| `blueprint_search` | Rank the catalog against a plain-language ask; returns each blueprint's full contract | no |
| `deployment_create` | New org repo (thin shell, pinned blueprint version) + registration PR adding the pipeline action | `dry_run` first |
| `deployment_read` | Registration PR → pipeline stages → stack status, the whole chain | no |
| `deployment_update` | Turn file changes into a PR on a deployment repo — never a push | `dry_run` first |
| `deployment_health` | Stack health + failure events + cornell:* tag inventory audit | no |
| `deployment_restart` | Retry failed pipeline stage / re-run at current version. Never a version change | `dry_run` first |
| `deployment_delete` | Deregistration PR removing the pipeline action — never an AWS delete call; the platform removes the stack after merge | `dry_run` first |
| `spec_export` | Render the deployment spec for an audience: coder, narrative, security, transfer, user, offboarding | no |

Confirm-before-doing UX: mutating tools default to `dry_run=true` and return the full plan.
(MCP elicitation is unavailable on stateless transports, which AgentCore requires — the
dry-run pattern works everywhere.)

## Run locally

Server on its own — this is all you need to point an MCP client at it:

```sh
cd packages/builder-mcp
uv run builder-mcp                 # streamable HTTP on http://127.0.0.1:8000/mcp
```

Server **and** the browser console together, one command from the repo root:

```sh
tools/dev                          # then open http://127.0.0.1:8765
```

`tools/dev` is a bash script and needs Git Bash on Windows — `bash` on the PowerShell PATH is
the WSL launcher, not Git Bash. Per-platform instructions, the stop/cleanup rules, and the
ports are in [devtools/README.md](devtools/README.md#run-it).

Connect from Claude Code:

```sh
claude mcp add --transport http cornell-builder http://127.0.0.1:8000/mcp
```

Tests: `uv run pytest -q` (also run repo-level `tools/check` before pushing).

## Configuration (all env vars, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | *(unset)* | Server-side GitHub credential. Unset → write tools return dry-run plans. GitHub App installation is the P1 target (D3) |
| `BUILDER_MCP_DEPLOYMENT_MODE` | `folder` | Where `deployment_create` puts the deployment shell: `folder` = `outputs/<name>/` in the workshop repo, same PR as the pipeline action (testing phase — credential can't create repos); `repo` = new `deploy-<name>` org repo (target state, SPEC C2) |
| `BUILDER_MCP_GITHUB_ORG` | `cu-aaii` | Org for deployment repos |
| `BUILDER_MCP_WORKSHOP_REPO` | `ai-dlc-workshop` | Repo the pipeline tracks |
| `BUILDER_MCP_APPLICATION` / `BUILDER_MCP_ENVIRONMENT` | `aidlc` / `main` | Stack-name prefix `<app>-<env>-<name>` |
| `AWS_REGION` | `us-east-1` | All AWS reads |
| `BUILDER_MCP_REPO_ROOT` | auto-detected | Catalog source; unset off-repo → catalog is fetched from GitHub |
| `BUILDER_MCP_TRANSPORT` | `streamable-http` | `stdio` for local stdio use |
| `BUILDER_MCP_HOST` / `BUILDER_MCP_PORT` | `127.0.0.1` / `8000` | Bind address |
| `BUILDER_MCP_STATELESS` | off | Set `1` on AgentCore (no session affinity) |
| `BUILDER_MCP_LOG_LEVEL` | `INFO` | Stdlib logging level (configured in `main()` only); `DEBUG` adds per-operation detail |

## AWS access is read-mostly by design

The AWS surface is: CloudFormation describe*, CodePipeline get/state, Resource Groups
Tagging get-resources, plus exactly two writes — `StartPipelineExecution` and
`RetryStageExecution` — which can only re-run what the tracked branch already defines.
The server cannot create, update, or delete stacks; that permission belongs to the
pipeline's role, and the pipeline acts only on merge.

## Deploying to Bedrock AgentCore

**Merge deploys — same as every blueprint.** The pipeline's Build stage builds the
`builder-mcp` target of [`Dockerfile`](Dockerfile) in this directory (linux/arm64,
build context `builder-mcp/` via `CONTAINER_CONTEXT`) and the BlueprintDeploy
stage deploys [`infra/builder-mcp.yml`](infra/builder-mcp.yml) with the image pinned by
digest. Runbook and review points: [`deploy/HANDOFF.md`](deploy/HANDOFF.md); post-deploy
proof: `uv run python deploy/verify.py`.

## Validation harness

`deploy/validate_endpoints.py` exercises all eight tools iteratively (default 10 calls
each, mutating tools always `dry_run=true`) and reports ok/degraded/failed counts plus
min/median/p95/max latency per tool — the speed-check numbers for the BACKLOG
"Verification & performance" item (no targets yet; it measures, never asserts).
Local: `uv run python deploy/validate_endpoints.py`. Deployed:
add `--url <runtime endpoint> --bearer-env BUILDER_MCP_TOKEN` (env var holds the Entra
bearer token). `--markdown PATH` writes the same table as a report file.
