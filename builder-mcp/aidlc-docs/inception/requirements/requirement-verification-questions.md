# Requirement Verification Questions — builder-mcp

Answer by filling in the `[Answer]:` tag under each question (letter, or free text for
"Other"). Where a recommendation exists it's marked ⭐ with the reasoning; the mob decides.

Context already settled by the product proposal — **not** asked again below:

- **Whose repo?** A new repo in Cornell's GitHub org, created by the MCP server through a
  **GitHub App installation** (D3). The builder's identity never enters the credential chain;
  their harness gets no direct write access and proposes changes as diffs (`propose_change`).
- **What triggers a deploy?** Merge, and nothing else (D4). So the MCP has no "deploy now"
  button — "execute deployment" means *open the PR and report pipeline status after merge*.
- **Intent → blueprint matching**: whole catalog in model context (D2). Trivial this week
  with one blueprint.

---

## Q1 — Where does a created "repo" actually live this week?

The vision says the Builder creates a **new repo** from a template ("shown live", demo
beat 3). But Track 0's deploy path is *this* repo: one pipeline, `pipeline/stacks.yml`
registry, stack-name prefix scoping. A brand-new repo has no pipeline until one is
bootstrapped for it.

- A) ⭐ **New repo in the org + a registration PR to this repo.** `create_deployment` makes
  the repo from the template *and* opens a PR here adding the blueprint stack to
  `stacks.yml`/`pipeline.yml`. Demo beat 3 stays real (new repo appears live), and deploy
  still flows through the one existing gate. Cost: two artifacts per request.
- B) **Branch/PR in this repo only.** No new repo; a "deployment" is a PR adding an instance
  under `blueprints/`. Simplest wiring, but demo beat 3 ("a new repo appears") weakens.
- C) **New repo with its own bootstrapped pipeline.** Truest to the end-state, but
  bootstrapping CodePipeline + CodeConnections per repo in 6 build hours is high-risk
  (the CodeConnections handshake alone needs a human in the console).
- X) Other (describe below)

[Answer]: A

## Q2 — What is the MCP server's own runtime shape this week?

The brief says "registered in the AI Gateway, on the builder's API key" — a remote MCP.

- A) **Remote HTTP MCP behind the AI Gateway from day one.** Matches the vision and the
  demo narrative ("in your Claude Cowork"), but needs hosting, TLS, and gateway
  registration before Tuesday 2 PM.
- B) ⭐ **Local stdio MCP this week, remote later.** Runs on the presenter's laptop in
  Claude Code/Cowork; identical tool surface, zero hosting risk. The gateway registration
  becomes a P1 (Sep–Nov) item. Cost: demo says "this will be behind the gateway" instead
  of showing it.
- C) **Both**: build stdio first, lift to HTTP Tuesday morning if rehearsal is green.
- X) Other

[Answer]: X — HTTP MCP from the start: run local streamable-HTTP now, end **deployed on
AWS Bedrock AgentCore (MCP) by end of day**, verified and demo-ready ("snazzy"). Deploy
using the presenter's AWS CLI credentials (workshop expedient; the IaC/pipeline path is
the P1 target).

## Q3 — Which tools are in scope for Tuesday 2 PM?

Your starter list: search, create repo, execute deployment, health check, restart, modify.
The demo needs beats 2–4 (search → repo → PR → pipeline). Suggested split:

- A) ⭐ **MVP = `blueprint_search`, `create_deployment` (repo + PR), `deployment_status`
  (pipeline/stack state).** Backlog = `propose_change` (modify), `health_check`, `restart`.
- B) MVP also includes `propose_change` — modifying a deployment is part of the story
  ("they keep building against the running dev environment").
- C) MVP also includes `health_check` (read CloudFormation/pipeline state — cheap, and
  feeds demo beat 7's dashboard narrative).
- D) All six tools by Tuesday.
- X) Other

[Answer]: D — all six tools **today** (Monday), ahead of the Tuesday demo.

## Q4 — "Restart a deployment": what does it mean here?

Serverless stacks don't restart in the EC2 sense. Candidates:

- A) ⭐ **Re-run the pipeline / redeploy the stack at its current version** (retry a failed
  or wedged deployment). An empty-commit or `RetryStageExecution` through the server's AWS
  role.
- B) Roll back to the previous blueprint version (a revert PR — stays inside the D4 gate).
- C) Out of scope entirely; drop it from the tool list.
- X) Other

[Answer]: (not answered — proceeding on the ⭐ recommendation A: retry/redeploy at the
current version. Mob to confirm or override.)

## Q5 — What did "Playwright MCP" mean in the starter notes?

- A) **Smoke-testing the deployed app** — after deploy, the builder's agent uses Playwright
  to drive the running UI and confirm it works (a health check that proves beat 5).
- B) **Part of the review gate** — automated browser test evidence attached to the PR.
- C) A note-to-self about tooling for *building* the MCP, not a product requirement.
- X) Other

[Answer]: Skip — dropped from scope.

## Q6 — Authentication for the *future user* of the blueprint

Your input list distinguishes builder-MCP auth from blueprint-user auth. For the
course-chatbot, end-users authenticate via Teams/Entra (Track C's problem). What does the
*builder-mcp* need to do about it?

- A) ⭐ **Collect it as blueprint parameters only** — e.g. `audience: unit|cornell`,
  owner NetID — passed into the template; enforcement lives in the blueprint (per the
  `blueprint.yaml` `inputs:` contract), not in the MCP.
- B) The MCP must also *provision* identity resources (Entra app registrations etc.) —
  pulls the Terraform/Azure stage into scope this week.
- C) Defer entirely; hardcode audience for the demo.
- X) Other

[Answer]: A (tentative — "I think"; revisit if Track C surfaces an identity-provisioning need)

## Q7 — Guardrails as an input: where do they bind?

- A) ⭐ **In the deploy path, not the MCP** — the MCP validates parameters against the
  blueprint manifest and refuses malformed requests, but *governance* stays in the PR gate
  + pipeline checks (`tools/check`, cfn-lint, the platform's account guardrails). The MCP
  is untrusted by design; nothing it does can bypass the gate.
- B) The MCP also enforces policy pre-flight (e.g. refuses `data_classification: restricted`
  before ever creating a repo) — better UX, duplicate enforcement to maintain.
- X) Other

[Answer]: A (tentative — "I think")

## Q8 — Implementation stack for the server

- A) ⭐ **Python + the official MCP SDK (FastMCP)** — matches `pipeline/validate_stacks.py`
  and `uv` already being the repo's only toolchain prerequisite; Lambda-friendly later.
- B) TypeScript + the official MCP SDK — stronger typing for tool schemas; second toolchain
  in the repo.
- X) Other

[Answer]: A — Python, whatever is particularly AWS-friendly. Python + FastAPI already on
the build machine.

## Q9 — "Export" feature: export what?

- A) The conversation's deployment spec (chosen blueprint + parameters) as a reviewable
  artifact — effectively the manifest that seeds the repo/PR.
- B) An inventory/report of the builder's deployments.
- C) Defer; not needed for Tuesday.
- X) Other

[Answer]: A — a spec. Exports serve six purposes, in priority order:
1. Validation by another coder
2. A narrative of the business logic for a non-coder
3. Security / authentication review
4. Transfer — help someone else build this elsewhere
5. How to use the deployment as-is
6. (lower priority) Off-boarding: a faculty member leaving Cornell takes their system elsewhere

Follow-on requirement: a system for **releases and release notes**. See
`versioning-releases-and-recovery-options.md` for the options analysis the mob requested.
