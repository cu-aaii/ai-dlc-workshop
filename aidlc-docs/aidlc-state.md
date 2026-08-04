# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (repo), but the unit of work is a new, self-contained blueprint
- **Start Date**: 2026-08-03
- **Current Stage**: INCEPTION - Units Generation Part 1 (plan + 7 questions issued, awaiting answers)
- **Application Design Approved**: 2026-08-03 — user response "approved"
- **Execution Plan Approved**: 2026-08-03 — user response "Approve and Continue"
- **User Stories Approved**: 2026-08-03 — user response "approve stories"
- **Queued amendment (NOT blocking)**: 2026-08-03 — custom telemetry, answered in
  `inception/requirements/requirement-amendment-questions-telemetry.md` (Q1=A, Q2=C, Q3=B, Q4 free text).
  Q3=B routes it to a **second Requirements → Stories pass** after v1 stories are approved, so
  `requirements.md` and `stories.md` are unchanged by it and the v1 gate is no longer held.
  Resolved shape: blueprints emit business-level usage metrics, dashboard displays them joined on
  `cornell:deployment-id`; built inside `blueprints/dashboard/` with `observability/` as the eventual
  home, due when a second blueprint emits metrics.
- **Story Plan Approved**: 2026-08-03 — user response "approve plan"
- **Requirements Approved**: 2026-08-03 — user response "requirements approved"

## Workspace State
- **Existing Code**: Yes — CloudFormation (YAML), Python (`pipeline/validate_stacks.py`), shell (`tools/check`)
- **Programming Languages**: YAML (CloudFormation templates), Python
- **Build System**: None (uv-fetched cfn-lint + pyyaml, no package manifest)
- **Project Structure**: Single deploy-path repo with a `blueprints/<name>/` plugin structure (see `blueprints/README.md`)
- **Workspace Root**: /Users/jpi6/ai-workshop/ai-dlc-workshop
- **Reverse Engineering Needed**: No — see rationale below
- **Reverse Engineering Rationale**: `README.md` and `CLAUDE.md` already document the architecture, conventions
  (cornell:* tagging, stack naming, registry/pipeline wiring), and the target unit of work is a brand-new,
  self-contained blueprint directory (per `blueprints/README.md`, a blueprint is self-contained) rather than a
  modification of existing components. The only existing artifact under the target path
  (`blueprints/dashboard/infra/hello-world.yml`) is an unfinished, unregistered copy-paste of `hello-world`
  with no real logic to reverse-engineer. Full Reverse Engineering (business overview, API docs, component
  inventory, interaction diagrams) is treated as low-value for this addition and is skipped per the Adaptive
  Workflow Principle / "Simple changes may skip conditional INCEPTION stages". User may request it explicitly
  at any time.

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Prior Decisions (made before formal AI-DLC invocation)
- Blueprint scope: **Cost & usage dashboard** — surfaces `cornell:*` tag inventory and cost data (per
  README.md/CLAUDE.md references to "the cost and usage dashboard").
- Process: user explicitly opted into the formal AI-DLC workflow.

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| security-baseline | Yes | Requirements Analysis |
| property-based-testing | Yes | Requirements Analysis |
| resiliency-baseline | Yes | Requirements Analysis |

Full rule files loaded for all three (deferred rule loading, Step 5.1): `security-baseline.md`
(SECURITY-01..15), `property-based-testing.md` (PBT-01..10, full enforcement — answer A, not
partial), `resiliency-baseline.md` (RESILIENCY-01..15). All are blocking constraints.

### Resiliency decision points deferred to NFR/Application Design
Per the resiliency extension's own scoping, these user decisions are asked at NFR Design rather
than Requirements, and are NOT blocking requirements.md:
- RESILIENCY-04: CI/CD tooling, rollback mechanism, deployment style
- RESILIENCY-14: resiliency testing approach
- RESILIENCY-15: incident response process

## Execution Plan Summary
See `inception/plans/execution-plan.md`. Risk level **Medium**; rollback Easy-to-Moderate; testing
Moderate-to-Complex.
- **Total stages**: 13 (incl. the Operations placeholder)
- **Stages to execute**: Application Design, Units Generation, Functional Design, NFR Requirements,
  NFR Design, Infrastructure Design, Code Generation, Build and Test
- **Stages to skip**: Reverse Engineering only (rationale above). Every other conditional stage has
  at least one blocking requirement that would otherwise have no home — a consequence of opting into
  all three extensions.

### Finding raised at Workflow Planning — SUPERSEDED 2026-08-03
~~`pipeline/pipeline.yml` defines `ContainerRepository` and `ContainerBuildProject` but has only three
stages (Source, PipelineDeploy, BlueprintDeploy); **no stage invokes the container build**.~~
**No longer true** — see `inception/amendments/repo-baseline-2026-08-03.md` §A1.2. A branch rebase onto
`main` landed a `Build` stage invoking `ArmContainerBuildProject`, and `builder-mcp` proves
build → digest → deploy-by-digest end to end on arm64. The **x86** `ContainerBuildProject` is still
uninvoked, which is why Lambda architecture became a new open question (Q8).

Still true: US-15 does not cover adding the Build stage action or the Dockerfiles — a known
story-coverage gap carried by Infrastructure Design and Code Generation rather than a story amendment.
It is now cheaper to close, since the stage exists and the root `Dockerfile` target pattern is set.

## ⚠️ Repo baseline amendment — 2026-08-03
`origin/dashboard` was force-pushed (rebased onto `main`), pulling in 15 commits merged elsewhere. All
inception artifacts survived byte-identical; pre-rebase tip `f9d4d57`. Four facts underpinning approved
artifacts changed. Full record: **`inception/amendments/repo-baseline-2026-08-03.md`**.

| § | What changed | Approved artifacts annotated |
|---|---|---|
| A1.1 | **No-self-approval rule removed.** Zero approving reviews required; `validate` is the only automated gate before a shared-account deploy | `requirements.md` §4.3 RESILIENCY-03 + §5 constraint 4; `execution-plan.md` success criteria |
| A1.2 | **Container build now runs** (arm64, via `builder-mcp`). x86 still uninvoked | `application-design.md` §6.1; `services.md` deployment table; `execution-plan.md` risk reason 4 |
| A1.3 | **New decision**: arm64 vs x86 Lambda architecture | none — asked as Q8 in `unit-of-work-plan.md` |
| A1.4 | **`blueprint.yaml` is a parsed contract** (`builder_mcp/catalog.py`); needs `DeploymentName`, `state`, `data_classification`, `cost` values | none — asked as Q3/Q9 |
| A1.5 | Risk stays **Medium** on a partly different reason set — container unknown shrank, change-control gate weakened | `execution-plan.md` |
| A1.6 | `tools/check` now needs `terraform` **and** `uv`; neither installed here | — |

Approved conclusions were **not** rewritten — each affected passage keeps its original wording and
gains a pointer. No user decision was reopened. `CLAUDE.md`'s own closing paragraph still contradicts
its `pipeline.yml` on the container build; flagged for its owner, not edited here.

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [ ] Reverse Engineering (SKIPPED — see rationale above)
- [x] Requirements Analysis
- [x] User Stories
- [x] Workflow Planning
- [x] Application Design
- [ ] Units Generation — EXECUTE (Part 1 planning in progress)

### 🟢 CONSTRUCTION PHASE
- [ ] Functional Design — EXECUTE (PBT-01 identifies properties here)
- [ ] NFR Requirements — EXECUTE
- [ ] NFR Design — EXECUTE (RESILIENCY-04, -14, -15 user decisions are due here)
- [ ] Infrastructure Design — EXECUTE (SECURITY-01, -06, -14 SRI, RESILIENCY-08, container build)
- [ ] Code Generation — EXECUTE (ALWAYS)
- [ ] Build and Test — EXECUTE (ALWAYS)

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

## Application Design decisions (Q1–Q11, all resolved)
See `inception/plans/application-design-plan.md` Part A2 (Q1–Q8) and Part A3 (Q9–Q11).

| # | Decision | Answer |
|---|---|---|
| Q1 | Snapshot store | Single versioned encrypted JSON object in S3 |
| Q2 | Aggregation timing | Read time; snapshot holds raw inventory only |
| Q3 | API front door | API Gateway HTTP API |
| Q4 | Distribution topology | One CloudFront distribution, two origins, `/api/*` to the API |
| Q5 | API surface | Distinct path per view |
| Q6 | Health endpoint | Same Lambda, same API |
| Q7 | UI build | A framework with a build step |
| Q8 | Degraded-state signalling | HTTP status code **and** body status field |
| Q9 | Framework and bundler | React + Vite |
| Q10 | How built files reach S3 | New Build stage action in the pipeline |
| Q11 | SECURITY-10 over npm | Pinning yes; scanning and SBOM no |

### Open but NOT blocking
- **Q12/Q13** in `inception/plans/application-design-plan-clarification-2.md` — whether
  `requirements.md` §4.6 gains a fifth accepted exception for Q11 = B, and whether US-09's fourth
  acceptance criterion is narrowed to name the ecosystems it applies to. Both are **approved**
  artifacts, so amending them is a user decision. The design is complete and consistent either way.

### Deferred to Infrastructure Design by this stage
- `aws s3 sync` targets the site bucket, but the Build stage precedes the stack that creates it.
  Three resolutions exist (split the bucket into its own stack / sync after BlueprintDeploy / resolve
  the name by convention). Recorded rather than guessed — `application-design.md` §6.4.

## Current Status
- **Lifecycle Phase**: INCEPTION
- **Current Stage**: Units Generation Part 1 (Planning) — Steps 1-5 complete. Application Design is
  complete and approved; all five mandatory artifacts are in `inception/application-design/`
  (`components.md`, `component-methods.md`, `services.md`, `component-dependency.md`,
  `application-design.md`)
- **Next Stage**: Units Generation Part 2 (Generation), after the plan is approved
- **Status**: Awaiting answers in `inception/plans/unit-of-work-plan.md` — **9 questions, 22
  `[Answer]:` tags** (Q9 has four sub-tags). Amended 2026-08-03: Q6 rewritten (false premise), Q3
  corrected (omitted `blueprint.yaml`), Q8 and Q9 added. Q1, Q2, Q4, Q5, Q7 unaffected.

### What Units Generation actually decides here
This blueprint deploys as one CloudFormation stack behind one CloudFront distribution, so the
vendored rules' "each unit becomes an independently deployable service" framing does not apply.
The decomposition decides **how many times the CONSTRUCTION stages run** — Functional Design, NFR
Requirements, NFR Design, Infrastructure Design, Code Generation, and Build and Test are per-unit.
The one boundary that changes *how work is verified* rather than how it is organised: C-04 and C-05
have empty dependency rows and no AWS SDK, so they can be property-tested on a laptop with no
account and no pipeline. Everything else needs the never-yet-run container build.
