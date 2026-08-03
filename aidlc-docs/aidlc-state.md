# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (repo), but the unit of work is a new, self-contained blueprint
- **Start Date**: 2026-08-03
- **Current Stage**: INCEPTION - User Stories (Part 2: Generation complete — awaiting approval of `inception/user-stories/stories.md` and `personas.md`)
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

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [ ] Reverse Engineering (SKIPPED — see rationale above)
- [x] Requirements Analysis
- [ ] User Stories (WILL EXECUTE — new user-facing UI, multiple personas, multiple components)
- [ ] Workflow Planning
- [ ] Application Design
- [ ] Units Generation
- [ ] Per-Unit Construction
- [ ] Build and Test
