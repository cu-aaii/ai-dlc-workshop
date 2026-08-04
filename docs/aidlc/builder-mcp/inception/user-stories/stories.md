# User Stories — builder-mcp (Gate 2, Part 2)

Journey-organized per **Q-S1 = A**; four personas per **Q-S2 = B** (see
[personas.md](personas.md)); Given/When/Then criteria per story **plus** the
demo-readiness checklist at the end, per **Q-S3 = C**. Every story carries a coverage
mark per **Q-S4 = B**: **Served** (tool named) / **Partial** (tool + what's missing) /
**Not served**. The gap table applies **Q-S5 = B**: gaps that block a demo beat get
built; the rest are logged. Acceptance sign-off: whoever reviews the PR at the gate
(**Q-S6 = C**).

Tool names use the **noun_verb surface** (C3 rename in flight): `blueprint_search`,
`deployment_create`, `deployment_read`, `deployment_update`, `deployment_delete`,
`deployment_restart`, `deployment_health`, `spec_export`.

Every story was checked against INVEST; the story ↔ tool matrix and the reverse
tool-coverage check are in [story-tool-map.md](story-tool-map.md).

---

## Stage 1 — Discover

### ST-01 · Find a blueprint from plain-language intent
**Persona:** Builder.
As a Builder, I want to describe what I need in plain language and get matching
blueprints back, so that I can start without knowing the catalog or any AWS terms.

- **Given** a catalog with at least one blueprint, **When** I search with an intent
  phrase (e.g. "a place to host course files"), **Then** every blueprint is returned,
  ranked by relevance — never filtered out (D2).
- **Given** a query matching nothing well, **When** I search, **Then** I still see the
  whole catalog ranked, with summaries, so I can browse instead of dead-ending.
- **Given** the catalog source is unreachable, **When** I search, **Then** I get a
  plain-language error narrative, not a stack trace (NFR7).

**Coverage:** **Served** — `blueprint_search`.

### ST-02 · See what a blueprint really is before choosing
**Persona:** Builder (secondary: Reviewer).
As a Builder, I want each result to show the blueprint's summary, inputs, maturity,
data classification, and baseline cost, so that I can choose with eyes open.

- **Given** a search result, **When** I inspect a blueprint, **Then** I see the full C1
  manifest contract: summary, `inputs` (with enum values), `maturity`,
  `data_classification`, and `cost.baseline_monthly_usd` / `scales_with`.
- **Given** a `deprecated` blueprint, **When** it appears in results, **Then** its
  maturity is visible so I can avoid building on it.

**Coverage:** **Served** — `blueprint_search` (returns each blueprint with its full C1
contract).

### ST-03 · Be findable by how builders actually ask
**Persona:** Blueprint Author.
As a Blueprint Author, I want my `matches:` phrases and summary to drive intent
ranking, so that builders find my blueprint without knowing its name.

- **Given** a blueprint whose `matches:` includes "static website", **When** a builder
  searches "host a simple site", **Then** that blueprint ranks above unrelated ones.
- **Given** the whole catalog goes into model context (D2), **When** the catalog grows,
  **Then** ranking still returns every blueprint (revisit past ~75 blueprints).

**Coverage:** **Served** — `blueprint_search`.

### ST-04 · Know the cost before I commit
**Persona:** Builder (secondary: Platform Operator).
As a Builder, I want a cost estimate before creating anything, so that I don't discover
the price after the stack exists.

- **Given** a blueprint with a `cost` block, **When** I view it pre-create, **Then** I
  see `baseline_monthly_usd` and what it scales with.
- **Given** my chosen parameter values, **When** I ask what this deployment will cost,
  **Then** I get an estimate computed for *my* configuration, not just the baseline.
- **Given** platform overhead exists (AgentCore, CodeBuild, ECR), **When** costs are
  presented, **Then** the platform share is at least acknowledged, not silently zero.

**Coverage:** **Partial** — `blueprint_search` surfaces the manifest `cost` block
(criterion 1); no tool computes a parameter-aware estimate or platform overhead
(criteria 2–3; BACKLOG "Cost").

## Stage 2 — Configure

### ST-05 · Validate before anything is created
**Persona:** Builder.
As a Builder, I want a dry run that validates my parameters against the manifest and
shows exactly what would be created, so that mistakes cost seconds, not cleanup.

- **Given** `dry_run=true` (the default), **When** I call `deployment_create`, **Then**
  nothing is written to GitHub and I get the full plan: repo name, files, registration
  PR diff.
- **Given** a parameter missing or outside its enum `values`, **When** I dry-run,
  **Then** I get a specific validation error naming the input and its allowed values.
- **Given** a valid dry run, **When** I re-call with `dry_run=false`, **Then** exactly
  the previewed artifacts are created — no surprises between preview and execution.

**Coverage:** **Served** — `deployment_create` (dry-run-first is mandatory UX, C3).

*Refining dry-run as a confirm UX is deprioritized to the backlog (mob, 2026-08-03);
the criteria above stand as the mechanical contract (BACKLOG "UX").*

### ST-06 · Be guided through the inputs, not interrogated
**Persona:** Builder.
As a Builder, I want to be walked through required inputs with multiple-choice options
where enums exist, so that I never have to guess a free-text value (NFR6).

- **Given** an input of type `enum`, **When** I'm asked for it, **Then** I choose from
  its `values`, never type free text.
- **Given** a required input I omitted, **When** I dry-run, **Then** the response tells
  me what's missing and its description, so the conversation can collect it.

**Coverage:** **Partial** — manifest `inputs` (via `blueprint_search`) plus
`deployment_create` dry-run errors drive the conversation, but true MCP elicitation is
impossible on the stateless transport (GOTCHA-ELICITATION); the dry_run two-step is the
stand-in confirm UX (C4).

*Refining the dry-run two-step as a confirm UX is deprioritized to the backlog
(mob, 2026-08-03); the criteria above stand (BACKLOG "UX").*

### ST-07 · No deployment without an owner
**Persona:** Builder (secondary: Platform Operator).
As a Platform Operator, I want every deployment to require an owner NetID at creation,
so that every resource is attributable from birth.

- **Given** a create call without `owner_netid`, **When** it runs (dry or real),
  **Then** it is rejected with a clear message — a deployment cannot exist unowned.
- **Given** a valid owner, **When** the deployment is created, **Then** all four
  `cornell:*` tags are derived and present in the stack parameters (FR2).

**Coverage:** **Served** — `deployment_create`.

## Stage 3 — Create

### ST-08 · Create a governed deployment, not a deploy
**Persona:** Builder.
As a Builder, I want creating a deployment to produce a new repo and a registration PR
— and *never* a running stack — so that the human gate stays the only path to AWS.

- **Given** a valid non-dry create, **When** it completes, **Then** two artifacts
  exist: a new org repo (thin shell per C2: `deployment.yaml`, pinned version) and a
  registration PR to the workshop repo adding one BlueprintDeploy action (C6).
- **Given** the create succeeded, **When** I check AWS, **Then** no stack exists yet —
  merge, and nothing else, deploys (D4).
- **Given** the registration PR, **When** the pipeline validator runs, **Then**
  `validate_stacks.py` passes: the stack registered and its action present (no silent
  green-but-deploys-nothing).

**Coverage:** **Served** — `deployment_create`.

### ST-09 · Singletons can't be duplicated
**Persona:** Builder (secondary: Reviewer).
As a Builder, I want the tool to stop me deploying a second copy of a singleton
blueprint, so that I don't hit an opaque mid-pipeline collision instead.

- **Given** a blueprint with `singleton: true`, **When** I create with any deployment
  name, **Then** the name is forced to the blueprint name (e.g. stack
  `aidlc-main-hello-world`), per C3.
- **Given** the singleton is already registered, **When** I try to create it again,
  **Then** I get a clear "already deployed" narrative, not a duplicate PR.

**Coverage:** **Served** — `deployment_create`.

### ST-10 · Failures speak my language
**Persona:** Builder.
As a Builder, I want every failure returned as a plain-language narrative, so that an
unreachable service or a bad input never surfaces as a stack trace (NFR7).

- **Given** GitHub or AWS is unreachable, **When** any tool runs, **Then** it returns
  `{"error": ...}` with a narrative and a suggested next step — never raises to the
  transport.
- **Given** no GitHub credential is configured, **When** a write tool runs, **Then** it
  degrades to a dry-run plan and says so (C5).

**Coverage:** **Served** — all eight tools (C3 error contract).

## Stage 4 — Review / Approve

### ST-11 · A diff I can actually review
**Persona:** Reviewer.
As a Reviewer, I want the registration PR to be a minimal, convention-shaped insertion,
so that I can approve in minutes without diffing a regenerated file.

- **Given** a registration PR, **When** I open it, **Then** the pipeline.yml change is
  a single action inserted before `Outputs:` (text insertion, C6), named
  `<PascalCase(deployment)>CloudFormation`.
- **Given** the stack name in the action, **When** I check it, **Then** it matches
  `<application>-<environment>-<name>` — inside the role scope, so it can actually
  deploy.
- **Given** the blueprint's template is already registered, **When** a second
  deployment of it arrives, **Then** the PR touches only `pipeline.yml`, not
  `stacks.yml` (duplicate-template rule).

**Coverage:** **Served** — `deployment_create` (C6 PR shape is the deliverable the
reviewer consumes).

### ST-12 · Review the deployment, not just the diff
**Persona:** Reviewer.
As a Reviewer, I want a security-audience spec of the proposed deployment, so that I
can judge what it *does* — auth, data classification, exposure — not just what the diff
says.

- **Given** a deployment repo exists (created pre-merge), **When** I request
  `spec_export` with `audience=security`, **Then** I get blueprint + pinned version +
  parameters + repo + stack rendered for security review.
- **Given** the blueprint declares `data_classification`, **When** the spec renders,
  **Then** the classification is stated so the gate can block anything above policy.

**Coverage:** **Served** — `spec_export` (audience `security`).

### ST-13 · The tool provably can't skip me
**Persona:** Reviewer (secondary: Platform Operator).
As a Reviewer, I want a guarantee that no tool can merge, push to a tracked branch, or
call CloudFormation Create/Update/Delete, so that my approval is the only path to a
deploy.

- **Given** the full tool surface, **When** any tool runs with any input, **Then** no
  PR is merged, no tracked branch is pushed, and no CFN Create/Update/Delete is issued
  (C3 governance invariants — hold forever).
- **Given** the runtime role (C5), **When** its policy is inspected, **Then** its only
  AWS writes are `codepipeline:StartPipelineExecution` and `RetryStageExecution`.

**Coverage:** **Served** — surface-wide invariant across all eight tools, enforced by
the C5 role and covered by tests.

## Stage 5 — Observe deployment

### ST-14 · Watch the whole chain in one view
**Persona:** Builder (secondary: Platform Operator).
As a Builder, I want one status view spanning PR → pipeline → stack, so that "where is
my deployment?" has a single answer.

- **Given** a deployment with an open registration PR, **When** I call
  `deployment_read`, **Then** I see the PR state (open/merged), pipeline execution and
  stage states, and CloudFormation stack status, as one chain (FR3).
- **Given** the stack doesn't exist yet, **When** I read status, **Then** the view says
  which link of the chain it's waiting on (e.g. "PR open — awaiting review"), not
  "stack not found".

**Coverage:** **Served** — `deployment_read`.

### ST-15 · Know when it goes green without babysitting
**Persona:** Builder.
As a Builder, I want to be told when my PR merges and the pipeline goes green, so that
I don't have to poll.

- **Given** a merged registration PR, **When** the pipeline completes, **Then** I can
  learn the outcome (green or which stage failed) from my client.
- **Given** the pipeline is mid-run, **When** I ask, **Then** I see which stage is
  executing now.

**Coverage:** **Partial** — `deployment_read` answers both criteria on demand
(poll-based); no push notification exists, and the stateless server (C4) keeps no
subscription state. Polling satisfies the demo beat.

## Stage 6 — Operate

### ST-16 · Is it healthy, really?
**Persona:** Builder (secondary: Platform Operator).
As a Builder, I want a health check that goes beyond "stack exists", so that I can
diagnose problems without the console.

- **Given** a deployed stack, **When** I call `deployment_health`, **Then** I get stack
  existence + status, and on failure the relevant stack events (FR5).
- **Given** the tag requirement, **When** health runs, **Then** it audits all four
  `cornell:*` tags and reports any missing.
- **Given** the deployment doesn't exist, **When** I check health, **Then** I get a
  narrative pointing me to `deployment_read` for the chain view, not an exception.

**Coverage:** **Served** — `deployment_health`.

### ST-17 · Retry without redeploying the world
**Persona:** Builder.
As a Builder, I want to retry a failed pipeline stage or re-run the pipeline at the
current pinned version, so that a transient failure doesn't require a PR.

- **Given** a failed stage, **When** I call `deployment_restart` (after its dry run),
  **Then** the failed stage is retried or a fresh execution starts — at the current
  version only, never a version change (FR6; version changes go through
  `deployment_update`).
- **Given** `dry_run=true` (default), **When** I call it, **Then** I see what would be
  restarted before anything starts.
- **Given** a restart in progress, **When** the re-run has not gone green within
  **30 minutes**, **Then** that restart is treated as failed, counts against the cap
  of 3 (ST-20), and the narrative says so (mob, 2026-08-03).

**Coverage:** **Served** — `deployment_restart` (the 30-minute time box itself is the
same future guardrail as the cap — see ST-20).

### ST-18 · Every resource visible to inventory and cost
**Persona:** Platform Operator.
As a Platform Operator, I want every deployed resource to carry all four `cornell:*`
tags, so that inventory and the cost dashboard see everything.

- **Given** any deployment created through the surface, **When** its stack deploys,
  **Then** owner, blueprint, blueprint-version, and deployment-id tags are present on
  its resources (derived at create, FR2).
- **Given** a tag went missing (manual drift), **When** `deployment_health` runs,
  **Then** the audit flags it.

**Coverage:** **Partial** — `deployment_create` (derivation) + `deployment_health`
(per-deployment audit); no fleet-wide sweep exists — the operator must know each
deployment name (see ST-19).

### ST-19 · See everything that's deployed
**Persona:** Platform Operator (secondary: Builder).
As a Platform Operator, I want to list all deployments with owner, blueprint, version,
and status, so that inventory doesn't depend on remembering names.

- **Given** N deployments exist, **When** I ask for the list, **Then** I get all N with
  name, owner NetID, blueprint + pinned version, and current status.
- **Given** a Builder with several deployments, **When** they ask "what do I have?",
  **Then** they get their own subset.

**Coverage:** **Not served** — no `deployment_list` tool; every read tool requires a
known `deployment_name`.

### ST-20 · Retries can't run forever
**Persona:** Platform Operator.
As a Platform Operator, I want restarts capped per deployment per window, so that
unbounded retries can't mask real failures or burn pipeline runs.

- **Given** 3 restarts of one deployment within the window, **When** a fourth is
  requested, **Then** the tool refuses and directs the builder to open a PR or contact
  the platform team.
- **Given** the cap triggers, **When** the refusal is returned, **Then** it is a
  narrative with the count and window, not a bare error.
- **Given** a restart whose re-run has not gone green within **30 minutes**, **When**
  the time box expires, **Then** that restart is treated as failed, counts against the
  cap of 3, and the narrative says so (mob, 2026-08-03).

**Coverage:** **Not served** — agreed future guardrail (BACKLOG "Operations &
guardrails"); needs restart-count state the stateless server (C4) doesn't keep.

### ST-21 · Triage an incident from the chain, not the console
**Persona:** Platform Operator.
As a Platform Operator, I want to diagnose a failing deployment from status + health
alone, so that incident response doesn't require console archaeology.

- **Given** a red pipeline, **When** I call `deployment_read`, **Then** I see which
  stage failed on which execution.
- **Given** a stack in a failure state, **When** I call `deployment_health`, **Then** I
  see the failure events that explain why.

**Coverage:** **Served** — `deployment_read` + `deployment_health`.

## Stage 7 — Evolve

> **Scope: post-MVP** (mob, 2026-08-03). Stage 7 is marked post-MVP by the mob —
> stories retained for the roadmap, excluded from MVP acceptance. Stage 8 remains in
> MVP scope.

### ST-22 · Change it the same way it was born
**Persona:** Builder.
As a Builder, I want to propose a change as a PR on my deployment repo, so that every
change passes the same gate as creation — and nothing else deploys it.

- **Given** a files map + description, **When** I call `deployment_update` (after dry
  run), **Then** a branch and PR are created on the deployment repo — never a direct
  push (FR4, D3).
- **Given** the PR is open but unmerged, **When** I check AWS, **Then** nothing has
  changed — merge, and nothing else, deploys (D4).
- **Given** no GitHub credential, **When** I call it, **Then** I get the dry-run plan
  with a clear note (C5).

**Coverage:** **Served** — `deployment_update`.

### ST-23 · Release a new version without breaking anyone
**Persona:** Blueprint Author.
As a Blueprint Author, I want to release semver versions with release notes while
existing deployments stay pinned, so that evolution never becomes a forced upgrade.

- **Given** a new blueprint version releases, **When** existing deployments are
  inspected, **Then** each still pins its original version (C2) and nothing redeployed.
- **Given** a release, **When** a builder considers upgrading, **Then** release notes
  exist describing what changed (FR8).
- **Given** the manifest and template, **When** a version bumps, **Then**
  `metadata.version` and the template's `BlueprintVersion` default move in lockstep
  (C1 rule).

**Coverage:** **Partial** — pinning is served by the C1/C2 contracts
(`deployment_create` writes the pin); the release system and release notes (FR8) are
not built (options doc pending mob decision).

### ST-24 · Contribute a blueprint without tribal knowledge
**Persona:** Blueprint Author.
As a Blueprint Author, I want a validated contribution path — manifest + template +
registration — so that the catalog grows beyond the platform team (catalog starvation
is a HIGH risk).

- **Given** a new `blueprints/<name>/` with manifest and template, **When**
  `tools/check` runs, **Then** manifest rules (no CFN marker string — GOTCHA-MARKER),
  template lint, and `stacks.yml` registration are all verified.
- **Given** the blueprint merges, **When** a builder searches matching intent, **Then**
  it appears ranked in `blueprint_search` with its full C1 contract.

**Coverage:** **Partial** — the PR path + `tools/check` + C1 contract exist and
`blueprint_search` picks up merged blueprints; no MCP tool scaffolds or validates a
contribution conversationally (authors work in the repo by hand).

### ST-25 · Upgrade my deployment deliberately
**Persona:** Builder.
As a Builder, I want to move my deployment to a newer blueprint version via a PR, so
that upgrades are opt-in, reviewed, and reversible.

- **Given** a newer version exists, **When** I request the upgrade, **Then** a PR on my
  deployment repo bumps the pinned version in `deployment.yaml` — merge deploys it.
- **Given** the upgrade PR, **When** the reviewer opens it, **Then** the version delta
  and release notes are visible in the description.

**Coverage:** **Partial** — `deployment_update` can carry the version-bump PR
(criterion 1 mechanically), but nothing composes it (no version-diff awareness, no
release notes in the description); the upgrade-bot is P1 (BACKLOG "Platform").

## Stage 8 — Hand off

### ST-26 · Explain my deployment to the right audience
**Persona:** Builder (secondary: Reviewer).
As a Builder, I want a spec of my deployment rendered for a chosen audience, so that a
developer can validate it, a colleague can understand it, or a successor can run it.

- **Given** a deployment, **When** I call `spec_export` with an audience in `coder |
  narrative | security | transfer | user | offboarding`, **Then** I get blueprint +
  version + parameters + repo + stack rendered for that audience (FR7).
- **Given** an unknown audience value, **When** I call it, **Then** I get the list of
  valid audiences back, not a failure.

**Coverage:** **Served** — `spec_export`.

### ST-27 · Leave Cornell without leaving a mystery
**Persona:** Builder (secondary: Platform Operator).
As a departing Builder, I want a full offboarding package, so that my deployment
survives me or is retired cleanly.

- **Given** `audience=offboarding`, **When** the spec exports, **Then** it includes
  everything a successor needs: what it is, how it runs, who to contact, how to retire
  it.
- **Given** ownership transfers, **When** the new owner takes over, **Then** the
  `cornell:owner` tag and `deployment.yaml` owner can be updated through the governed
  change path (ST-22).

**Coverage:** **Partial** — `spec_export` accepts `offboarding` as an audience, but FR7
marks it "later": the full hand-off package content is not yet specified beyond the
common spec body.

### ST-28 · Tear it down as safely as it went up
**Persona:** Builder (secondary: Platform Operator).
As a Builder, I want to retire a deployment through a deregistration PR, so that
teardown passes the same human gate as creation and nothing is orphaned.

- **Given** a deployment, **When** I call `deployment_delete` (after its dry run),
  **Then** a deregistration PR is opened removing the deployment's pipeline action —
  the tool itself deletes no stack and no repo (C3 invariants hold).
- **Given** the PR is open but unmerged, **When** I check, **Then** the deployment
  still runs — merge is the only trigger, for teardown too.
- **Given** the blueprint declares authoritative `state`, **When** the dry run renders,
  **Then** the plan warns what data is at stake before I confirm.

**Coverage:** **Served** — `deployment_delete` (new in the noun_verb surface;
deregistration-PR flow).

---

## Demo-readiness checklist (per Q-S3 = C)

Demo beats, in order, with the story/tool that carries each and what must be true
before rehearsal:

- [ ] **Beat 1 — Intent**: builder states plain-language intent in the client
      (ST-01). *Pre-req:* client connected to the server (live AgentCore + OAuth token,
      or local fallback per BACKLOG "Demo").
- [ ] **Beat 2 — Blueprint match**: `blueprint_search` returns the catalog ranked with
      summaries and cost baseline (ST-01, ST-02, ST-04 criterion 1).
- [ ] **Beat 3 — Repo appears**: `deployment_create` dry-run shown, then real run
      creates the deployment repo (ST-05, ST-08). *Show the dry-run briefly as the
      tool's default mechanics — the confirm-UX polish is backlogged (mob,
      2026-08-03; BACKLOG "UX").* *Pre-req:* org-scoped GitHub
      credential in place — without it writes degrade to dry-run (GAP-D1).
- [ ] **Beat 4 — PR opened**: registration PR visible, one-action diff, convention
      stack name (ST-08, ST-11). *Pre-req:* same credential; a second person available
      to approve (nobody approves their own PR).
- [ ] **Beat 5 — Pipeline green**: after merge, `deployment_read` shows PR merged →
      pipeline stages → stack `CREATE_COMPLETE` (ST-14, ST-15 via polling).
- [ ] **Beat 6 — Status/health visible**: `deployment_health` shows healthy stack +
      four-tag audit passing (ST-16).
- [ ] **Fallback ready**: recorded end-to-end run exists in case live AgentCore/OAuth
      isn't ready (BACKLOG "Demo").
- [ ] **Failure narrative rehearsed**: one deliberate bad input shows the
      plain-language error path (ST-05, ST-10) — degradation is part of the demo story
      (NFR7).

## Gap table (per Q-S4 = B / Q-S5 = B)

Demo-blocking = blocks one of beats 1–6 above. Per Q-S5 = B, demo-blocking gaps get
**built/resolved before the demo**; the rest are **logged**.

| Gap | Stories | Blocks a beat? | Disposition |
|---|---|---|---|
| GAP-D1 · Org-scoped GitHub credential in Secrets Manager (writes currently degrade to dry-run) | ST-08, ST-11, ST-22, ST-28 | **Yes — beats 3–4** | **Build/resolve for demo** (operational: credential provisioning, C5) |
| GAP-D2 · Deployed AgentCore endpoint + OAuth token for live client | all (transport) | **Yes — beat 1 (live)** | **Resolve for demo**; recorded run is the agreed fallback (BACKLOG "Demo") |
| GAP-01 · `deployment_list` — fleet/own-deployments inventory | ST-19, ST-18 | No | Log (new BACKLOG item; C3 contract change) |
| GAP-02 · Parameter-aware cost estimate + platform overhead | ST-04 | No (baseline shown at beat 2 suffices) | Log (BACKLOG "Cost", exists) |
| GAP-03 · Restart cap (3 per window) | ST-20 | No | Log (BACKLOG "Operations & guardrails", exists) |
| GAP-04 · Release system + release notes (FR8) | ST-23, ST-25 | No | Log — **post-MVP** (Stage 7 scope, mob 2026-08-03; versioning options doc awaiting mob decision) |
| GAP-05 · Conversational blueprint-contribution/scaffold tool | ST-24 | No | Log — **post-MVP** (Stage 7 scope, mob 2026-08-03; C3 contract change) |
| GAP-06 · Push notification on pipeline state change | ST-15 | No (polling covers beat 5) | Log (needs state the C4 stateless server doesn't keep) |
| GAP-07 · Offboarding package content spec | ST-27 | No | Log (FR7 marks it "later") |
| GAP-08 · Upgrade composition (version-diff aware PR, release notes in body) | ST-25 | No | Log — **post-MVP** (Stage 7 scope, mob 2026-08-03; upgrade-bot is P1, BACKLOG "Platform") |

**Not-served stories:** ST-19 (`deployment_list`), ST-20 (restart cap). Neither blocks
a demo beat; both are logged above. Every other story is Served or Partial.
