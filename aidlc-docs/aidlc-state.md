# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (repo), but the unit of work is a new, self-contained blueprint
- **Start Date**: 2026-08-03
- **Current Stage**: **CONSTRUCTION** - NFR Requirements
- **Functional Design U-01 Approved**: 2026-08-03 — user response "Continue to next stage"
- **INCEPTION COMPLETE**: 2026-08-03
- **Units Approved**: 2026-08-03 — user response "Approve & Continue"
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

### Amendment A2 — monorepo reorganization, same day (27 commits, clean fast-forward, no rewrite)
| § | What changed | Effect here |
|---|---|---|
| A2.1 | `aidlc-rules/`→`docs/aidlc-rules/`, `builder-mcp/`→`packages/builder-mcp/`, design docs→`docs/aidlc/dashboard/design/` | Reference fixed in the story map. **`aidlc-docs/` did not move.** |
| A2.2 | **There is no root `Dockerfile`** — one per component directory, `CONTAINER_CONTEXT` + `CONTAINER_TARGET` | `unit-of-work.md` **corrected**: one `blueprints/dashboard/Dockerfile`, targets `collector` + `api`, context = blueprint root (forced, because both images need `core/`) |
| A2.3 | New enforced rule: a `blueprint.yaml` must name a **registered** template | Manifest names `dashboard.yml`; `dashboard-storage.yml` is registered but not the entry point |
| A2.4 | `observability/` exists — README only, "Nothing here yet" | Still not to be built. Its README names `cornell:deployment-id` as *the* join key, so this blueprint is the first consumer of a Track E contract |
| A2.5 | New gotchas: `--list` must emit LF; `uv` may pick 32-bit Python without a `.python-version` pin | Relevant at Code Generation |

**A2 changed no decision and no unit.** Path-and-packaging only. §6.4 still open — no commit touched the
pipeline's stage order.

## Functional Design U-01 — decisions and outputs
`construction/plans/u-01-domain-core-functional-design-plan.md` Part A2 (Q1-Q9, all **A**).
Artifacts: `construction/u-01-domain-core/functional-design/` — `domain-entities.md`,
`business-rules.md`, `business-logic-model.md`.

| Rule | Decision |
|---|---|
| BR-01 | Tag presence: exact key match **and** non-whitespace value. Empty or wrong-case ⇒ **missing**. One predicate, shared. |
| BR-02 | Malformed item skipped, counted in `skipped_count` + `skipped_reasons` — never silently |
| BR-03 | Global resources get region `"global"` |
| BR-04 | Duplicate ARNs deduped, last wins, collisions counted |
| BR-05 | Grouping: missing group `value=None`, omitted when empty; order count desc, value asc, missing last |
| BR-06 | Gap report lists **which** tags are missing, in `REQUIRED_TAGS` order |
| BR-07 | Freshness three-valued: FRESH / STALE / **INVALID**; `stale_after` = **3 × refresh_interval** |
| BR-08 | JSON, sorted keys, deterministic bytes; read requires major-version match; unknown top-level keys **ignored** |

**10 PBT properties identified** (P1-P10), up from 6. New: **P8** accounting identity
(`raw_returned == len(resources) + skipped + duplicates`), **P9** grouping/classification agreement,
**P10** freshness monotonic in `now`.

### Corrections recorded at this stage
1. **My Q1 text claimed skipping weakens FR-1.1. It does not.** Checked the approved text: FR-1.1 says
   nothing about totality, and US-02 is phrased in terms of *silence* ("no resource is **silently**
   omitted", "never presented as complete"). Q1 = A satisfies both exactly. **No amendment warranted** —
   a fabricated amendment is as much a defect as a missing one.
2. **Q9's option text was ambiguous ("preserved-or-ignored") — my error, resolved not re-asked.**
   Resolved to **ignore**, because **no code path reads a snapshot and writes it back** (collector always
   constructs fresh + single PutObject; API only reads), so key loss is unobservable by construction.
   P1 is correspondingly **scoped to the same major version**, stated rather than hidden.

### ⚠️ Cross-unit obligations flowing to U-02
- `Freshness.INVALID` needs a **sixth row** in C-03's degraded-state table: **503 / `error`**, not 200
- `skipped_count`, `duplicates_removed`, `raw_returned` must reach the UI, or Q1 = A's "surface the
  count" half is never delivered

### ⚠️ Flagged for the user, not decided
`CLAUDE.md` now says `docs/aidlc/` is "this repo's own AI-DLC record," and builder-mcp's record was
relocated to `docs/aidlc/builder-mcp/`. By that convention this blueprint's record belongs at
`docs/aidlc/dashboard/`. But **the vendored rules hardcode `aidlc-docs/` paths in every stage file**, so
relocating puts the repo convention in direct conflict with the methodology. ~30 files. A decision, not a
cleanup — deliberately not done.

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [ ] Reverse Engineering (SKIPPED — see rationale above)
- [x] Requirements Analysis
- [x] User Stories
- [x] Workflow Planning
- [x] Application Design
- [x] Units Generation (2 units: U-01 Domain Core, U-02 Dashboard Platform)

**🔵 INCEPTION PHASE COMPLETE — 2026-08-03**

### 🟢 CONSTRUCTION PHASE
- [ ] Functional Design — **U-01 complete (awaiting approval)**; U-02 pass follows
      - [x] U-01 Domain Core — 3 artifacts, BR-01..BR-08, **10 PBT properties** (PBT-01 satisfied) — **APPROVED 2026-08-03**
      - [ ] U-02 Dashboard Platform — incl. `frontend-components.md` for C-06
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
- **Current Stage**: Units Generation — Parts 1 and 2 complete (Steps 1-15). All three mandatory
  artifacts generated in `inception/application-design/`: `unit-of-work.md`,
  `unit-of-work-dependency.md`, `unit-of-work-story-map.md`
- **Next Stage**: **CONSTRUCTION** — Functional Design for U-01, after units are approved
- **Status**: Awaiting explicit user approval of the units. This is the **last INCEPTION stage**.

## Units of Work (approved decisions Q1-Q9, all "A")
See `inception/plans/unit-of-work-plan.md` Part A2 and `inception/application-design/unit-of-work.md`.

| Unit | Owns | Stories | Verifiable without AWS |
|---|---|---|---|
| **U-01 Domain Core** | C-04 Inventory Model, C-05 Aggregation Core | US-03, US-04, US-05, US-10 (4) | **Yes, entirely** |
| **U-02 Dashboard Platform** | C-01, C-02, C-03, C-06, C-07, C-08, C-09, both templates, `blueprint.yaml`, pipeline/registry edits | the other 13 | No |

One dependency edge: U-02 imports U-01 in-process. Acyclic. U-01 is on the critical path and nothing
blocks it. Decisions: two units, enablers assigned with spillover recorded, group-by-kind layout with an
enforceable no-`boto3` `core/` boundary, two CloudFormation templates, depth-first construction, human
review requested though not required, **arm64**, and `blueprint.yaml` = `internal` /
`singleton: false` + `DeploymentName` / snapshot `derived` / cost estimated (~$10-15/mo, WAF-dominated).

### Correction recorded at this stage
**Q4 = A does not resolve `application-design.md` §6.4, and my Q4 text wrongly said it would.** The
pipeline order is `Source → PipelineDeploy → Build → BlueprintDeploy`, and `PipelineDeploy` deploys only
the pipeline's own stack — so a storage stack registered as a BlueprintDeploy action still deploys after
the Build stage's `s3 sync`. Splitting the template changes which stack owns the bucket, not when it
exists. Q4 = A stands on its independent merit (stateful buckets stay out of the stack app updates
replace). §6.4 remains **open, owner U-02, decided at Infrastructure Design**; likely resolution is Build
emitting the bundle as a CodePipeline artifact with a `SiteSync` action at `RunOrder: 2` inside
BlueprintDeploy. Options tabled in `unit-of-work-plan.md` Part A2 Interaction 1.

### What Units Generation actually decides here
This blueprint deploys as one CloudFormation stack behind one CloudFront distribution, so the
vendored rules' "each unit becomes an independently deployable service" framing does not apply.
The decomposition decides **how many times the CONSTRUCTION stages run** — Functional Design, NFR
Requirements, NFR Design, Infrastructure Design, Code Generation, and Build and Test are per-unit.
The one boundary that changes *how work is verified* rather than how it is organised: C-04 and C-05
have empty dependency rows and no AWS SDK, so they can be property-tested on a laptop with no
account and no pipeline. Everything else needs the never-yet-run container build.
