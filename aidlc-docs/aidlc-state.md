# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (repo), but the unit of work is a new, self-contained blueprint
- **Start Date**: 2026-08-03
- **Current Stage**: INCEPTION - Requirements Analysis

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
- **security-baseline**: Pending opt-in (asked in Requirements Analysis)
- **property-based-testing**: Pending opt-in (asked in Requirements Analysis)
- **resiliency-baseline**: Pending opt-in (asked in Requirements Analysis)

## Stage Progress
- [x] Workspace Detection
- [ ] Reverse Engineering (SKIPPED — see rationale above)
- [ ] Requirements Analysis (IN PROGRESS)
- [ ] User Stories
- [ ] Workflow Planning
- [ ] Application Design
- [ ] Units Generation
- [ ] Per-Unit Construction
- [ ] Build and Test
