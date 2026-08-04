# Component Inventory

This repository is not organized into build packages. There is no `pom.xml`, `package.json`,
`build.gradle` or `pyproject.toml` anywhere. "Package" below therefore means **directory of
related, independently deployable or independently runnable artifacts** — the closest honest
mapping onto this repository's structure.

## Application Packages

| Package | Purpose |
| --- | --- |
| `blueprints/hello-world/` | The reference blueprint. Infrastructure only — no runtime application code. Deploys an S3 bucket and an SSM deployment marker recording the source commit. Its business value is proving the deploy path end to end, and being the shape a real blueprint copies. |

**Note**: no package in the repository contains runtime application code of any kind. No
Lambda handler, no service, no container entrypoint, no Dockerfile. Every deployed artifact to
date is storage, IAM, or pipeline plumbing.

## Infrastructure Packages

| Package | Technology | Purpose |
| --- | --- | --- |
| `bootstrap/` | CloudFormation | One-time, manually deployed account foundation: the `cloudformation-deploy-role` (AdministratorAccess, referenced by name from the pipeline), the versioned artifact bucket, the GitHub CodeConnections connection, and the SSM parameter publishing the connection ARN. |
| `pipeline/` | CloudFormation + CodeBuild buildspec | The deploy path itself: the three-stage pipeline, its IAM roles, the ECR repository, and the container build project. Self-deploying. |
| `blueprints/hello-world/infra/` | CloudFormation | The reference blueprint's template. |

**Terraform**: none. `CLAUDE.md` states that non-AWS resources (Azure/M365) are Terraform
executed from CodeBuild, and lists that stage under "deliberately not built". No `.tf` file
exists and the pipeline has no Terraform stage. This matters for the Teams chatbot, whose
identity chain (Entra app registration, Azure Bot Service resource, Teams app manifest) lives
entirely outside AWS.

## Shared Packages

| Package | Type | Purpose |
| --- | --- | --- |
| `pipeline/stacks.yml` | Configuration | The registry of every CloudFormation template and how each is deployed. The single source of truth the validator reconciles against. |

No shared library, model package, or client package exists. There is no code to share — the
repository contains exactly one Python file.

## Test Packages

| Package | Type | Purpose |
| --- | --- | --- |
| `tools/check` | Validation entry point | The only pre-push and CI command. Runs `cfn-lint` across all templates (with the mandatory literal `--` separator) and then the registry validator, both through `uv`. |
| `pipeline/validate_stacks.py` | Static consistency check | Reconciles registry, filesystem and pipeline definition in both directions. Turns the silent "registered but never deployed" failure into a review-time error. |
| `.github/workflows/pr-checks.yml` | CI harness | Installs `uv` and runs `tools/check` on every pull request. Constrained by an org allowed-actions policy to github-owned actions plus `hashicorp/setup-terraform@*`. |

**No unit tests, no integration tests, no load tests.** There is no test framework, no test
runner, and no test directory. `validate_stacks.py` — the one piece of executable logic — has
no tests of its own. Validation is entirely static: lint the templates, reconcile the
registry. Nothing verifies deployed behaviour.

## Vendored Content

| Package | Purpose |
| --- | --- |
| `aidlc-rules/` (34 files) | Verbatim copy of that directory from `awslabs/aidlc-workflows` — the AI-DLC methodology the workshop teaches. Inert: no code imports it, no pipeline stage reads it, and it is loaded into an AI session only on explicit invocation. Must stay byte-identical to upstream, including known typos and lint failures, because the re-sync is a delete-and-replace that would silently discard local edits. |

## Untracked Working Content

Present in the working tree, not committed. Recorded for completeness because it is the domain
input for this workflow.

| Path | Status | Purpose |
| --- | --- | --- |
| `docs/teams-chatbot-docs/` (4 files) | Untracked, **not gitignored** | Teams bot research: initial research, consolidated findings, in-tenant setup research, channel thread replies research. **One file contains live credentials** — see `audit.md`. |
| `docs/WORKING-WITH-AIDLC.md` | Untracked, not gitignored | Repository guidance on driving AI-DLC well. |
| `docs/teams bot exploration.json` | Untracked, not gitignored | Exported n8n workflow. Checked and clean of credentials. |
| `.mcp.json` | Untracked, **not gitignored** | MCP server configuration. **Contains a live GitHub personal access token** — see `audit.md`. |

## Total Count

Counting tracked, non-vendored files and treating directories as packages per the definition
above.

- **Total Packages**: 6
- **Application**: 1 (`blueprints/hello-world/`)
- **Infrastructure**: 3 (`bootstrap/`, `pipeline/`, `blueprints/hello-world/infra/`)
- **Shared**: 1 (`pipeline/stacks.yml` as configuration)
- **Test**: 1 (`tools/` plus the validator and CI workflow, which form a single gate)

File-level counts:

- **Tracked files total**: 50
- **Tracked, excluding vendored rules**: 16
- **Vendored rule files**: 34
- **CloudFormation templates**: 4 (`account-bootstrap.yml`, `pipeline.yml`, `hello-world.yml`,
  and `codebuild.yml` as a buildspec rather than a template)
- **Python files**: 1
- **Shell scripts**: 1
- **GitHub Actions workflows**: 1
- **Dockerfiles**: 0
- **Test files**: 0

## Components Defined But Not Invoked

Worth calling out separately, because they look like dead code and are not — they are
deliberately staged capability awaiting the first blueprint that needs them.

| Component | Location | State |
| --- | --- | --- |
| `ContainerRepository` (ECR) | `pipeline/pipeline.yml` | Defined. `ScanOnPush` enabled; lifecycle policy expiring untagged images after one day and keeping at most three `commit-` tagged images. |
| `ContainerBuildProject` (CodeBuild) | `pipeline/pipeline.yml` | Defined. `PrivilegedMode: true`, buildspec `pipeline/codebuild.yml`. |
| `ContainerBuildRole`, `ContainerBuildLogs` | `pipeline/pipeline.yml` | Defined. |
| Container buildspec | `pipeline/codebuild.yml` | Defined. Exports `CONTAINER_DIGEST`; requires `CONTAINER_TARGET` and `DATE_TAG` from the invoking stage. |

No pipeline stage invokes any of them, because nothing needs a container image yet. Wiring one
in is a Build stage action plus a Dockerfile — the recipe is in `pipeline/README.md`. Since
Lambda in this repository means container images, this is on the critical path for any
Lambda-based Teams bot.

## Deliberately Not Built

From `CLAUDE.md`. Scaffolding these early defeats the workshop's purpose; they are absent by
decision, not by oversight.

- `blueprints/course-chatbot/` — managed Bedrock Knowledge Base, Teams bot, Strands agent.
  **The current work item falls inside this boundary**, which is why an explicit invocation
  was required to begin it.
- `builder-mcp/` — the MCP server that searches blueprints and creates deployment repositories.
- The Terraform stage for Azure/Entra resources. **Directly relevant**: the Teams bot's
  identity chain is entirely non-AWS.
- `observability/`.
