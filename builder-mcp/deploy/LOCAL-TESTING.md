# Human-testing the Cornell Builder, locally

For the team to *use* the MCP conversationally before the AgentCore endpoint is live.
Nothing here needs AWS or org access.

## 1. Talk to it in Claude Code (30 seconds, zero setup)

`.mcp.json` at the repo root registers the server, so **opening Claude Code in this repo
is the whole setup** — it launches the server over stdio itself; no terminal, no port, no
token. Approve the server when prompted, then just talk:

> *"I want a chatbot my students can ask questions about my course material."*

Verified working — that exact query returns:

```
TOOLS (8): blueprint_search, deployment_create, deployment_delete, deployment_health,
           deployment_read, deployment_restart, deployment_update, spec_export

  30.0  tiny-chatbot   experimental  The world's tiniest chatbot: one Lambda container…
   2.0  hello-world    supported     Trivial tagged stack that proves the deploy path…
```

**Blueprint selection genuinely works** — the chatbot query ranks tiny-chatbot 15× above
hello-world. That is the demo's beat 2, running on a laptop.

Things worth trying, to see how it feels:
- *"what would it cost, and who has to approve it?"*
- *"actually create it, I'm tmf77"* → returns the full plan (see §2)
- *"is my hello-world deployment healthy?"* → degrades to a clear narrative without AWS
- *"explain this deployment to someone non-technical"* → `spec_export`, narrative audience

## 2. What `deployment_create` actually does — the honest answer

With **no GitHub credential** (default), it returns the plan and writes nothing:

```json
{ "blueprint": "tiny-chatbot v0.1.0 (experimental)",
  "stack": "aidlc-main-demo-bot",
  "estimated_cost": {"baseline_monthly_usd": 0, "scales_with": ["requests"]},
  "new_repo": "cu-aaii/deploy-demo-bot",
  "registration_pr": {"repo": "cu-aaii/ai-dlc-workshop",
                      "edits": "pipeline/pipeline.yml — one new BlueprintDeploy action"},
  "governance": "Deploys only when a human approves and merges the registration PR." }
```

That is real output from real code — not a mock. What it has *not* done is prove the
GitHub write path, because no token is configured.

## 3. Proving the write path for real — no org access needed

The write allowlist is **org-relative**, so pointing the server at your own GitHub account
exercises the identical code path that will run against `cu-aaii`:

```sh
# PowerShell, from builder-mcp/
$env:GITHUB_TOKEN = "<a fine-grained PAT on YOUR OWN account, repo scope>"
$env:BUILDER_MCP_GITHUB_ORG = "timothyfraser"
$env:BUILDER_MCP_WORKSHOP_REPO = "ai-dlc-workshop"   # your fork
uv run builder-mcp
```

Then ask it to create a deployment for real (`dry_run=false`). It will create
`timothyfraser/deploy-<name>` and open a registration PR **against your fork** — same
code, same contracts, your blast radius. Delete the repo afterwards.

This is the cheapest way to answer *"will it actually create?"* before anyone has org
credentials. Note the fork has no pipeline, so nothing deploys — the PR is the artifact.

## 4. Repeatable checks

```sh
uv run python deploy/validate_endpoints.py                 # 10 calls per tool + latency
uv run python deploy/verify.py --stack aidlc-main-builder-mcp   # against deployed AgentCore
```

## Why no separate chatbot UI

Claude Code (and Cowork on demo day) *is* the client — an MCP server has no UI of its
own by design, and building one would mean maintaining a second client that the demo
never uses. If we want a canned visual, the right artifact is a **recording** of a real
Claude session (BACKLOG "Demo"), not a bespoke web app.
