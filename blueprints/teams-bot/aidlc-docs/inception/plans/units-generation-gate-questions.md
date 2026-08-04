# Units Generation Part 2 — Gate Questions

**Created**: 2026-08-04
**Stage**: INCEPTION — Units Generation (gate between Part 1 and Part 2)
**Status**: 🛑 **Part 2 generation blocked pending these answers.**

Part 1 (planning) is complete and approved. `upstream-reconciliation-2026-08-04.md` named three
decisions as gating Part 2: **D1**, **D2** and **D5**. Two have since closed:

| Gate | State |
| --- | --- |
| **D1** — Terraform's scope in U0 | **Closed.** Settled by the track structure, not by us: Track C's Azure side is Terraform at `infra/azure/`. What survives is where the boundary falls — `azuread` yes, `azurerm` blocked on an Azure subscription RBAC assignment, catalog publish and availability scoping never. |
| **D5** — `aidlc-docs/` tracked or untracked | **Closed.** Per-component placement; 33 files tracked under `blueprints/course-chatbot/aidlc-docs/` as of `fe7d336`. |
| **D2** — one Dockerfile or one per component | **Open — Question 2 below.** |

Two further blockers surfaced when the repository was checked against the artifacts, and both change
what the unit artifacts say. They are **Question 1** and **Question 3**.

**How to answer**: put the letter after the `[Answer]:` tag under each question. If none of the options
fit, choose the last option (**Other**) and describe what you want. A blank answer will be treated as
accepting the stated recommendation, and recorded as such.

---

## Research finding — why two blueprint names exist

Folded in at the user's request, 2026-08-04. This is the evidence behind Question 1.

### There are not two directories. There is one scaffold and one name that was never built.

`git log --all --diff-filter=A -- 'blueprints/teams-bot/*'` returns nothing. **No commit on any
branch, local or upstream, has ever added a file under `blueprints/teams-bot/`.** That path exists
only as a *name* inside Track C's own INCEPTION artifacts, from the Q2 requirements decision
recorded as "generic and reusable, not course-specific."

So there is no competing implementation to reconcile and no other track's work to strand.

### `course-chatbot` is a facilitator decision recorded in the workshop brief

It is not an improvisation. `docs/Participant Brief — Vision & Workshop MVP.html` §3 states it
directly:

> "One honest simplification: in the diagram in §1, the Builder composes multiple blocks into one
> deployment. This week each request deploys one blueprint — **the course-chatbot template bundles
> the Teams frontend, document pipeline, and database together.** Composition of separate blocks is
> the very next thing on the roadmap; tracks B–D exist to make those seams real."

Created by **Ernest Francis** (`BlackFenix2`) in `adfd31b` — the same commit that added that brief,
rewrote `CLAUDE.md`, and moved `aidlc-rules/` under `docs/`. It arrived as workshop scaffolding, on
authority.

**That is why two names exist.** Q2 optimised for the brief's **§1** — the long-term catalog, whose
own diagram shows three *separate* blocks ("Teams bot", "Document ETL", "Database").
`course-chatbot` implements the brief's **§3** — the two-day simplification. Both are in the same
document. Our INCEPTION was written against the vision; the scaffold was built for the demo.

### Nobody else is using it, and Track B has already left the bundle

Every commit that has ever touched `blueprints/course-chatbot/`:

| Commit | Author | What |
| --- | --- | --- |
| `adfd31b` | Ernest Francis | the scaffold — three READMEs, `src/handler.py`, `requirements.txt` |
| `ae5fcdd` | Pete Stergion | the ten requirements answers, **still unmerged** in PR #21 |
| `fe7d336` | Fermin Romero | Track C's AI-DLC artifacts |

No template, no `blueprint.yaml`, no Dockerfile target, no `pipeline/stacks.yml` entry, no pipeline
action. **Track C would be its first real occupant.**

More telling: **the bundle is already half-dissolved.** `blueprints/course-chatbot/README.md`
assigns Track B `infra/` plus retrieval in `src/` — but Axel Stevens shipped
`blueprints/knowledgebase/` as its own standalone blueprint (PR #13) with its own template, manifest
and pipeline action. `blueprints/README.md:41` has already caught up and lists course-chatbot as
**"Tracks C and D"**, B dropped; the blueprint's own README still says B/C/D. Track D
(`upstream/team-d`) and Track E (`upstream/dashboard`) both work in workspace-root `aidlc-docs/` and
touch no course-chatbot file.

**Consequence that simplifies the decision**: because `knowledgebase` is a standalone blueprint
exporting `KnowledgeBaseId`, retrieval is reachable by parameter or SSM from *either* location. The
bundle is not what gets us the knowledge base. So Question 1 is largely about **naming and file
placement, not architecture** — either answer requires the same template, manifest, `stacks.yml`
entry, `Build` action and `BlueprintDeploy` action.

### Two stale references in the scaffold, which bear on Question 2

`blueprints/course-chatbot/README.md:22` and the `src/handler.py` module docstring both state the
image is built as *"the root Dockerfile target `course-chatbot`"*. **There is no root Dockerfile.**
It was removed when `builder-mcp` moved to `packages/` in PR #15, and `CLAUDE.md` now states plainly
that there is none. All four Dockerfiles in the repository are per-component. The scaffold documents
a layout the repository has already abandoned — the same drift Question 2 is about.

---

## Question 1
Where does Track C's deliverable live, and therefore what do the unit artifacts name?

Every one of the ten units in `unit-of-work-plan.md` names paths under `blueprints/teams-bot/`.
Whichever way this goes, the unit artifacts are written against the answer rather than against the
withdrawn path.

A) **`blueprints/course-chatbot/`** — Track C's slice of the shared MVP blueprint: `infra/azure/`
for the Terraform, `infra/` for the CloudFormation, `src/` for the handler code. The location the
brief designates for the demo. Beat 6 ("someone opens Teams, messages the bot, and it answers from
the actual course documents") is Track C's beat. Collides with nobody. Costs: the name is
course-specific, which contradicts Q2's reuse rationale; `U2` ("blueprint skeleton") becomes shared
rather than solely ours, so its completion criteria and dependency edges change.

B) **`blueprints/teams-bot/`** — a new standalone blueprint, following the brief's §1 composable
model and the precedent Track B set with `knowledgebase`. Keeps Q2's "generic and reusable" intact
and keeps `U2` entirely ours. Costs: it additionally depends on Track D's composition seam to reach
the knowledge base, and that seam is still undecided; and it diverges from the brief's §3 on demo
day.

C) **A now, B on the roadmap** — build into `blueprints/course-chatbot/` for this week, and record
the extraction to a reusable `teams-bot` block as an explicit follow-up in the unit artifacts. Gets
the demo without discarding Q2's reasoning.

X) Other (please describe after [Answer]: tag below)

[Answer]: C

**Recommendation: C.** A's location is right for today — the brief designates it, nobody else is in
it, and the knowledge base is reachable from there anyway. But Q2's reuse argument is sound and
survives this week, so recording the extraction costs one paragraph now and preserves the decision
rather than silently overwriting it. **The leadership demo is Tuesday 2:00 PM and today is Tuesday,
August 4**, which argues hard for the lowest-friction path.

## Question 2
One Dockerfile with named targets, or one Dockerfile per component? (**D2**)

Application Design Q11 recorded "one multi-stage Dockerfile, two named targets (`lambda`, `agent`)".
Upstream then relocated Dockerfiles into their components and added `CONTAINER_CONTEXT` so each
Build action names its own context directory. `blueprints/tiny-chatbot/Dockerfile`,
`blueprints/aisei-site/Dockerfile` and `packages/builder-mcp/Dockerfile` are separate files.

A) **One Dockerfile per component**, each in its own directory, each with its own
`CONTAINER_CONTEXT` and named target. Matches `CLAUDE.md`, matches all four existing Dockerfiles,
and makes each build's context smaller. Supersedes Q11.

B) **One multi-stage Dockerfile with named targets**, as Q11 recorded. Still works mechanically —
one context, two targets — but cuts against a convention that was deliberately changed, and against
the `CONTAINER_CONTEXT` mechanism added to support the other way.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

**Recommendation: A.** It is the repository's current convention with three worked examples, and
`CLAUDE.md` states there is no root Dockerfile — so B would also require correcting the scaffold's
two stale references rather than just replacing them.

**This question partly depends on Question 3.** If Question 3 lands on **B** (no AgentCore), there
is only **one** image to build, and Question 2 becomes moot — one component, one Dockerfile, no
targets to name. Q11's two-target design only exists because the agent ships as a second image.

## Question 3
Does the agent run on Bedrock AgentCore, or as Strands inside one Lambda?

Two records conflict, and this one defines whether `U6` exists at all. Our artifacts record
**AgentCore as MANDATED** by Team E ("it should be CloudFormation" — Marty Sullivan). PR #21
answers Q3 as **"A, one Lambda"** with the basis recorded as *time*, timeout risk noted with a
mitigation. `U6` is *"real agent container, `GatewayClient`, AgentCore Runtime + Endpoint + Memory"*.

A) **AgentCore stands.** The agent ships as its own ARM64 container on AgentCore Runtime, with an
Endpoint and Memory. `U6` stays as written, two images, ARM64 build on the critical path.
Conversation history stays in AgentCore Memory, so the Application Design Q9 decision holds
unchanged.

B) **Strands in one Lambda.** No AgentCore. `U6` dissolves into the worker, one image, the ARM64
critical path disappears. Costs: it overrides a mandate recorded from Team E, and it **reopens Q9**
— conversation history was placed in AgentCore Memory, so state needs a new home. Fastest path to a
working demo.

C) **Hold Part 2 and escalate to Marty** before generating any unit artifacts, since the mandate is
not Track C's to overrule.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — user's words: "MUST use Agent Core"

**Recommendation: B, with the escalation raised in parallel rather than blocking on it.** On
time-to-demo grounds B is clearly faster and PR #21 already chose it on Track C's behalf. But it
does override a recorded mandate, so this should be said out loud to Marty today rather than
discovered in rehearsal — which is why C is a real option and not a stalling tactic. Choosing B also
requires answering **where conversation state lives**; if B is chosen without that, I will raise it
as a clarification question rather than assume.

## Question 4
How do PR #21's ten answers get into our checkout?

PR #21 is **still open**, so its file —
`blueprints/course-chatbot/aidlc-docs/inception/requirements/requirements-questions.md` — is not on
this branch. Locally we have only the older `requirement-verification-questions.md`, a different
file. Four of those ten answers rewrite unit content: the gateway constraint, Q6 (sideload rather
than catalog publish), Q5 (read config from SSM because `deployment_create` silently drops `inputs`),
and Q3 above.

A) **Copy the file in from the PR branch** (`git checkout upstream/c/inception-requirements-answers
-- <path>`), so the unit artifacts cite a file that is actually present. Small risk of a trivial
duplicate when PR #21 merges, since the content would be identical.

B) **Generate from the reconciliation summary** and cite PR #21 by URL. No merge risk; the citation
points at something not in the tree.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

**Recommendation: A.** The summary in §2a of the reconciliation document is a paraphrase, and the
unit artifacts will be quoting these answers as settled requirements. Having the source file present
makes those citations checkable.

---

## Not a question — one mechanical item that needs no decision

**`.gitignore:38` will silently swallow every artifact Part 2 creates.** The `aidlc-docs/` pattern
has no leading slash, so it matches at every depth. Verified: `git check-ignore` already claims
`unit-of-work.md` and `unit-of-work-dependency.md` before they exist. The 33 currently-tracked files
survive only because ignore rules do not apply to already-tracked files — which is exactly the
failure mode PR #20 describes: *"A track can believe its artifacts are committed when nothing was
ever staged."*

**Handling**: every file Part 2 creates gets `git add -f`, and the staged list is verified with
`git status --short` before any commit. No decision needed; recorded so it is not forgotten. **This
file needed it too.**

## Also cleared since Part 1

- **`terraform` was not installed locally**, so `tools/check` aborted before linting anything.
  Installed 2026-08-04 at version **1.15.8**, matching the CI pin in
  `.github/workflows/pr-checks.yml:53` and satisfying `required_version = "~> 1.15"`. `tools/check`
  now passes end to end: 8 templates registered, cfn-lint clean, 1 Terraform module wired,
  `fmt`/`validate` clean, 77 builder-mcp tests passing.
- **No new upstream drift.** `team-c-wip` is 0 behind and 11 ahead of `upstream/main`, so the
  2026-08-04 reconciliation is still current.

---

## After answers

I will check the four answers for contradictions and ambiguities — Question 2 against Question 3 in
particular, since one can moot the other — raise a clarification file if any appear, then generate
the three unit artifacts:

| Artifact | Content |
| --- | --- |
| `application-design/unit-of-work.md` | unit definitions, responsibilities, code organisation strategy |
| `application-design/unit-of-work-dependency.md` | dependency matrix between units |
| `application-design/unit-of-work-story-map.md` | **requirement**-to-unit map, since User Stories was skipped |

Then mark the Part 1 plan checkboxes, verify Security Baseline compliance across the decomposition,
update `aidlc-state.md`, append to `audit.md`, and present the Step 16 completion message.

---

## Answer analysis — 2026-08-04 (rule: units-generation Step 7)

**Answers received**: **1=C, 2=A, 3=A, 4=A.** All four questions answered; no `[Answer]:` tag left blank.

**Question 3 was answered in words, not a letter** — "MUST use Agent Core". That maps to option **A**
("AgentCore stands") exactly and exclusively; the raw text is preserved above and in `audit.md`. No
clarification requested, because there is no second reading of it.

### Contradictions: none found

| Pair checked | Verdict |
| --- | --- |
| **3=A vs 2=A** | **Consistent, and 2 is no longer at risk of being moot.** Question 2 was flagged as dependent on Question 3: had 3 landed on one Lambda there would be one image and nothing for two targets to be. 3=A keeps **two images** (Lambda pair + AgentCore agent), so per-component Dockerfiles is a real choice and it is the repository's convention. |
| **3=A vs 1=C** | **Consistent.** AgentCore in CloudFormation inside a shared blueprint is already proven here — `packages/builder-mcp/infra/builder-mcp.yml` deploys an AgentCore runtime from a template. Nothing about `course-chatbot` as the location constrains the runtime choice. |
| **3=A vs Application Design Q7/Q9** | **Consistent, and this is the important one.** Conversation history was placed in **AgentCore Memory**. Choosing A means **Q9 does not reopen** and the recorded state design stands unchanged. The clarification question I committed to raising if B were chosen is therefore not needed. |
| **1=C vs FR-5** | **Divergence, resolved by 1=C rather than contradicted.** FR-5 names the blueprint `teams-bot`, stack `aidlc-main-teams-bot`, template `blueprints/teams-bot/infra/teams-bot.yml`. Answer C supersedes the *location* while preserving the *intent*: build into `course-chatbot`, record the extraction to a reusable block as a roadmap item. **FR-5 is amended, not deleted** — recorded in the unit artifacts. |
| **4=A vs 3=A** | **A real divergence from another track's document, not an internal contradiction.** PR #21's Question 3 answers "A) Inside the Bot Framework Lambda handler", basis recorded as time. Track C has now ratified the opposite. See below. |

### The one divergence that needs saying out loud

Answering **4=A** brings PR #21's file into this checkout, and that file states Q3 as "one Lambda".
Track C's answer is AgentCore. Both now sit in the same tree.

**Handling**: Pete's file is left **byte-identical** so PR #21 merges cleanly — Track C does not edit
another track's artifact to make it agree. The override is recorded in Track C's own artifacts
(`unit-of-work.md`, `aidlc-state.md`) with the reason: `requirements.md` FR-21 records AgentCore as
**mandated** by Team E, and a mandate is not Track C's to set aside on time grounds.

**This still needs a sentence to Marty today** rather than in rehearsal, because
`upstream-reconciliation-2026-08-04.md` §2a recorded it as "raised with Marty rather than decided" and
it is now decided in the direction of the mandate. Confirming costs nothing; discovering a
disagreement during the demo costs the demo. **Owner: the user. Not a blocker for generation** — the
answer aligns with the standing mandate, so proceeding is the conservative choice either way.

### Ambiguity resolved by documented assumption, not by another question

**Where Track C's code sits inside `blueprints/course-chatbot/src/`, given `handler.py` already
exists there.** That file is Ernest's scaffold stub; it reaches Bedrock with the execution role, which
violates FR-23 (the gateway mandate).

**Assumption recorded rather than asked**, because no answer to it changes a unit boundary:

- Track C **adds** `src/frontdoor/`, `src/worker/`, `src/agent/` and `src/shared/` alongside the
  existing `src/handler.py`.
- **Track C's units do not depend on removing or rewriting `handler.py`.** Whether it is retired is
  Track B's and Track D's call — Track B has moved to `blueprints/knowledgebase/`, so it may already
  be dead code, but deleting another track's file on demo day is not a risk worth taking for tidiness.
- Its FR-23 violation is **recorded as a finding against the scaffold**, not adopted as Track C debt.

Raising this as a fifth question would have cost a round trip and changed nothing about the ten units.

### Consequences carried into generation

1. **`U6` stays**, in full: agent container, `GatewayClient`, AgentCore Runtime + Endpoint + Memory.
2. **Two images, two Dockerfiles**, each in its component's directory with its own
   `CONTAINER_CONTEXT` — superseding Application Design Q11's single-file/two-target design and the
   `components.md` package layout that documents it.
3. **The ARM64 build path is back on the critical path for `U6`** — but as *"add an action modelled on
   `builder-mcp`"*, not *"prove the path"*, since R-1 is retired.
4. **`U9`'s `uv.lock` requirement hardens**: AgentCore's `uv sync --frozen` needs it (SECURITY-10).
5. **FR-5 amended**; **Q9/Q7 state design unchanged**; **Q11 superseded**.
