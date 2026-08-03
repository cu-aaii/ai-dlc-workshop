# Requirements — builder-mcp (Cornell Builder, Track A)

## Intent analysis

- **Request**: Build the Cornell Builder MCP server — the conversational front door that
  turns plain-language intent into a governed deployment through the existing deploy path.
- **Type**: New project (greenfield component in a brownfield repo)
- **Scope**: Multiple components — MCP server, GitHub integration, pipeline/CloudFormation
  integration, blueprint catalog
- **Complexity**: Complex. Compressed to one day by the mob's decision: **all six tools
  today, deployed to Bedrock AgentCore and verified by end of day.**

## Functional requirements

### FR1 — Blueprint search (`blueprint_search`)
Return catalog blueprints matching a plain-language intent. Whole catalog goes into model
context (D2); matching happens against each manifest's `matches:` phrases and summary.
Catalog source: `blueprints/` in this repo, each with a `blueprint.yaml` manifest
(the contract from the product proposal §04).

### FR2 — Create a deployment (`create_deployment`)
Per Q1-A, creating a deployment produces **two artifacts**:
1. A **new repo** in the Cornell GitHub org, generated from the blueprint template, holding
   a thin shell: manifest reference, parameter values, pinned blueprint version (D1).
2. A **registration PR to this repo** adding the deployment's stack to `pipeline/stacks.yml`
   (and its action in `pipeline/pipeline.yml`) so the existing pipeline deploys it.

Parameters are validated against the blueprint manifest `inputs:` before anything is
created. Required tags (`cornell:owner`, `cornell:blueprint`, `cornell:blueprint-version`,
`cornell:deployment-id`) are derived from the parameters — a deployment cannot be created
without an owner.

### FR3 — Deployment status (`deployment_status`)
Report the full chain for a deployment: registration PR state → pipeline execution state →
CloudFormation stack status, via read-only AWS API calls.

### FR4 — Modify a deployment (`propose_change`)
Accept a diff + description; commit to a branch and open a PR on the deployment repo.
The builder's harness never holds a git credential (D3). Merge — and nothing else —
deploys the change (D4).

### FR5 — Health check (`health_check`)
Stack existence + status, resource-level health where cheap (stack events on failure),
and required-tag presence. Read-only.

### FR6 — Restart a deployment (`restart_deployment`)
**Assumed (Q4 unanswered, ⭐A)**: retry/redeploy at the current pinned version — retry a
failed pipeline stage or re-trigger the pipeline. Never a version change (that's FR4 + a
PR). Mob to confirm.

### FR7 — Export a spec (`export_spec`)
Generate a reviewable spec of a deployment (blueprint + version + parameters + repo +
stack), rendered for a chosen **audience**, in priority order:
1. `coder` — validation by another developer
2. `narrative` — business-logic story for a non-coder
3. `security` — security/authentication review
4. `transfer` — rebuild-elsewhere guide
5. `user` — how to use the deployment as-is
6. `offboarding` (later) — faculty leaving Cornell, full hand-off package

### FR8 — Releases and release notes
Blueprints carry semver versions; deployments pin them. A release system with release
notes is required — options and recommendation in
[versioning-releases-and-recovery-options.md](versioning-releases-and-recovery-options.md).

## Non-functional requirements

- **NFR1 Transport/runtime**: MCP over **streamable HTTP**. Runs locally today for
  development; **deployed to Amazon Bedrock AgentCore and verified by end of day**
  (Q2). Server must be stateless so the same code runs in both places.
- **NFR2 Language/stack**: Python, official MCP SDK (FastMCP), AWS-friendly (Q8).
  `uv` toolchain, matching the repo's existing prerequisite.
- **NFR3 Credential boundary**: The MCP server holds the GitHub credential (GitHub App in
  P1; a scoped token today) and an AWS role. The **builder's client holds neither**.
  Secrets come from AWS Secrets Manager or environment — never from the repo (public,
  no secret scanning).
- **NFR4 Governance**: The server cannot bypass the gate. No tool merges PRs, pushes to
  `main`, or calls CloudFormation `CreateStack`/`UpdateStack` on blueprint stacks.
  Deploys happen only via merge (D4). Guardrails bind at the gate and pipeline, not in the
  MCP (Q7-A); the MCP only validates manifest inputs for UX.
- **NFR5 End-user auth**: Collected as blueprint parameters (`audience`, owner NetID) and
  passed through; enforcement lives in the blueprint (Q6-A).
- **NFR6 Elicitation UX**: Use MCP elicitation for parameter gathering — multiple choice,
  confirm-before-create. No free-text where an enum exists.
- **NFR7 Demo-critical**: Rehearsable end-to-end for Tuesday 2:00 PM; every tool degrades
  gracefully (a clear error narrative, not a stack trace) if AWS/GitHub is unreachable.

## Out of scope (this week)

- Playwright/browser smoke-testing (Q5 — dropped)
- Composition of multiple blocks per deployment (P2)
- GitHub App plumbing (P1 — token stands in today)
- AI Gateway registration (AgentCore endpoint stands in today)
- Automated review agent at the gate (human review this week)

## Traceability

| Requirement | Source |
|---|---|
| FR1–FR6 | Mob starter notes (function list) + Q1/Q3/Q4 answers |
| FR7 | Q9-A + the six export purposes (mob, 2026-08-03) |
| FR8 | Mob: "We should probably have a system for releases, and release notes" |
| NFR1 | Q2 answer (AgentCore by EOD) |
| NFR3, NFR4 | Product proposal D3, D4; CLAUDE.md hard constraints |
| Out-of-scope | Participant brief §3 "one honest simplification"; Q5 |
