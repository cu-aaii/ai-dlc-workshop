---
name: builder-mcp
description: How to deploy Cornell AWS infrastructure using the Cornell Builder MCP tools (blueprint_search, deployment_create, deployment_read, deployment_health, deployment_update, deployment_restart, deployment_delete, spec_export). Use whenever someone asks to deploy, provision, stand up, spin up, tear down, or check the health of AWS infrastructure at Cornell; asks what infrastructure they can deploy or what blueprints exist; asks why a deployment failed or is stuck; or asks for a written spec of an existing deployment. Also use when someone asks what the builder can do.
---

# Cornell Builder

Turns a plain-language infrastructure request into a **pull request** against the AI-DLC
workshop repo. A human reviews and merges; merging is what deploys.

Understand this before calling anything: **the builder never deploys.** It opens PRs and
reads status. That is a permanent governance guarantee, not a limitation of the current
version — see "Invariants" below. When a tool appears not to have deployed anything, it
is working correctly.

## The eight tools

The tool surface is frozen at exactly eight. There are no others.

**Read**

- `blueprint_search(query)` — rank the whole blueprint catalog against a plain-language
  need. Returns every blueprint with its full contract: inputs, cost, data
  classification, maturity. **Start here** for any new deployment.
- `deployment_read(deployment_name)` — the chain view for one deployment: registration
  PRs → pipeline stages → CloudFormation stack status. Use to answer "where is it?"
- `deployment_health(deployment_name)` — stack status, failure events, and an audit of
  the required `cornell:*` tags. Use to answer "why is it broken?"
- `spec_export(deployment_name, blueprint, audience="coder")` — render a written spec of
  a deployment. `audience` is one of `coder`, `narrative`, `security`, `transfer`,
  `user`, `offboarding`. Pick from what the user is actually doing: `security` for a
  review, `transfer` or `offboarding` for a handover, `narrative` for a stakeholder.

**Write** — every one of these takes `dry_run` and defaults it to `True`.

- `deployment_create(blueprint, deployment_name, owner_netid, parameters=None, dry_run=True)`
  — the deployment shell plus a registration PR.
- `deployment_update(repo, title, description, files, dry_run=True)` — a file map becomes
  a branch and a PR. Never a direct push.
- `deployment_restart(deployment_name, dry_run=True)` — retry a failed stage or re-run
  the pipeline at the current version.
- `deployment_delete(deployment_name, dry_run=True)` — a *deregistration PR*. It never
  calls AWS delete. The stack goes away when the PR merges.

## `dry_run` is a confirmation step, not a debug flag

This is the single most common mistake. The server is stateless and cannot open an
interactive prompt, so the two-step call **is** the confirmation UX.

Always:

1. Call the write tool with `dry_run=True` (the default).
2. **Show the returned plan to the user** — what it will create, which repo, which PR,
   what it costs. Do not summarize it away.
3. Wait for the user to confirm.
4. Only then call again with `dry_run=False`.

Never skip to `dry_run=False` because the plan "looked fine". The user has not seen it
until you show it.

If a write returns a plan when you expected a PR, the server has **no GitHub token**.
That is the designed degradation, not an error — say so plainly and tell the user a token
is needed to open the PR for real.

## A normal deployment, in order

1. `blueprint_search` with the user's actual words. Show the ranked options with their
   cost and data classification; let the user pick.
2. Collect the blueprint's required `inputs` — they are in the search result. Every
   deployment needs an `owner_netid`.
3. `deployment_create(..., dry_run=True)` → show the plan → confirm → `dry_run=False`.
4. Tell the user the PR must be **reviewed and merged** by a human. Nothing deploys until
   then.
5. After merge, `deployment_read` to follow the chain; `deployment_health` if it fails.

## Invariants — permanent, not current limitations

- **No merge.** Ever.
- **No push to a tracked branch.** Changes arrive as PRs from a new branch.
- **No CloudFormation Create, Update, or Delete.** Merge is the only deploy trigger.
- The client holds **no credential**. The server holds the GitHub token and AWS role.

Do not offer to work around any of these, and do not apologize for them. They are the
security model.

## Reading errors

Tools return `{"error": ...}` rather than raising — an `error` key is a normal result and
you should read and relay it, not retry blindly.

Two failures worth recognizing on sight:

- **Catalog error mentioning a rate limit** — anonymous GitHub access allows only about
  six catalog searches per hour per IP. The fix is configuring a GitHub token in the
  plugin's settings, not retrying.
- **A write silently returning a plan** — no token configured. See above.
