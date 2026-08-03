# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (repo), but the unit of work is a new, self-contained blueprint
- **Start Date**: 2026-08-03
- **Current Stage**: INCEPTION - Workflow Planning
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

### Finding raised at Workflow Planning
`pipeline/pipeline.yml` defines `ContainerRepository` and `ContainerBuildProject` but has only three
stages (Source, PipelineDeploy, BlueprintDeploy); **no stage invokes the container build**. Lambda
means container images, so this blueprint is the first to need one. US-15 does not cover adding the
Build stage action or the Dockerfiles — recorded as a known story-coverage gap, carried by
Infrastructure Design and Code Generation rather than by a story amendment.

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [ ] Reverse Engineering (SKIPPED — see rationale above)
- [x] Requirements Analysis
- [x] User Stories
- [x] Workflow Planning
- [ ] Application Design — EXECUTE
- [ ] Units Generation — EXECUTE

### 🟢 CONSTRUCTION PHASE
- [ ] Functional Design — EXECUTE (PBT-01 identifies properties here)
- [ ] NFR Requirements — EXECUTE
- [ ] NFR Design — EXECUTE (RESILIENCY-04, -14, -15 user decisions are due here)
- [ ] Infrastructure Design — EXECUTE (SECURITY-01, -06, -14 SRI, RESILIENCY-08, container build)
- [ ] Code Generation — EXECUTE (ALWAYS)
- [ ] Build and Test — EXECUTE (ALWAYS)

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

## Current Status
- **Lifecycle Phase**: INCEPTION
- **Current Stage**: Workflow Planning complete
- **Next Stage**: Application Design
- **Status**: Awaiting execution-plan approval
