# CLAUDE.md

Context for Claude Code sessions in this repo. `README.md` is the human onboarding doc; this
file is the set of things that are easy to get wrong and expensive to get wrong.

## What this repo is

The deploy path for Cornell's AI-DLC workshop (Aug 3–4, 2026), and the blueprints it deploys.
Cornell's AI Platform is building a **blueprint layer**: reusable, governed building blocks that
campus builders compose into working applications *without touching AWS*. A builder describes
what they want in Claude Code, and the pipeline deploys it into an AWS account the platform
team controls. Builders get PR-only write access — no AWS account, no console.

Everyone works in this one repo during the workshop, so `main` staying green matters more than
usual: **every merge to `main` deploys to a shared AWS account.**

## The AI-DLC workflow rules

`aidlc-rules/` is a **verbatim vendored copy** of that directory from
[awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows) — the AI-DLC methodology
the workshop teaches. Provenance and re-sync instructions are in `README.md`.

Keep it byte-identical to upstream — **do not edit anything under `aidlc-rules/`**, including to
fix a lint or a typo. Local changes are what make the next upstream release impossible to take
cleanly, and the re-sync is a delete-and-replace that would silently discard them. Anything this
repo needs to say about the rules goes here or in `README.md`.

**When the user invokes AI-DLC, read and follow `aidlc-rules/aws-aidlc-rules/core-workflow.md`,
and resolve its rule-detail references against `aidlc-rules/aws-aidlc-rule-details/`.** That
second half is required: `core-workflow.md` resolves rule details from four hardcoded paths
(`.aidlc/aidlc-rules/aws-aidlc-rule-details/`, `.aidlc-rule-details/`, `.kiro/…`, `.amazonq/…`)
and **none of them exists here**, so without that mapping every `common/…` and `inception/…`
reference in it dangles.

Do **not** load it otherwise. It opens by asserting priority over all other instructions, and
loading it for ordinary work here — editing `pipeline.yml`, adding a blueprint — would override
the constraints below with rules that know nothing about them. It is invocation-gated on
purpose; that also keeps ~340K of rules out of sessions that don't need them.

The constraints in this file still bind during an AI-DLC workflow. The vendored rules have no
concept of `cornell:*` tags, the stack-naming convention, `pipeline/stacks.yml`, or the fact
that a merge to `main` deploys to a shared account — so a workflow that produces AWS resources
still has to satisfy everything below.

## Hard constraints

These come from the platform design, not from preference. Don't relax them to make something
work; ask instead.

- **Everything is IaC and deploys through GitHub.** No click-ops. AWS resources are
  CloudFormation deployed via CodePipeline → CodeBuild. Non-AWS resources (Azure/M365 only)
  are Terraform executed from CodeBuild.
- **Serverless-first, region `us-east-1`.** Lambda means container images.
- **Secrets live only in AWS Secrets Manager.** Blueprints are configured to *use* credentials
  without ever containing them. **This repo is public and has no secret scanning** (an enforced
  org security configuration disables it), so nothing stops a committed key — never write one.
  A secret's *resource* is declared in CloudFormation; its *value* is injected once by CLI and
  is never in git. See `AzureCredentialsSecret` in `pipeline/pipeline.yml` for the pattern,
  including why it must not use `SecretString`.
- **`main` is PR-only**, enforced by branch protection: a pull request is required and direct
  pushes are rejected, the `validate` check must pass, and only members of the
  `ai-dlc-workshop` GitHub team may merge. **Zero approving reviews are required** — a team
  member merges their own PR. That is a deliberate workshop-time relaxation of the original
  one-human-approval rule, and it means the `validate` check is the only automated gate between
  a branch and a deploy.
- **All four `cornell:*` tags on every resource** (see below).

## How a merge becomes a deployment

```
approved PR merged to main
  └─ Source ............ webhook, starts within seconds
  └─ PipelineDeploy .... the pipeline deploys itself from pipeline/pipeline.yml
  └─ BlueprintDeploy ... one CloudFormation action per blueprint stack
  └─ Terraform ......... one CodeBuild action per Azure/Entra module, plan then apply
```

The `Terraform` stage **applies unattended**. There is no approval action, so a merge reaches
the Azure/Entra tenant with whatever rights the stored service principal holds. Treat a change
under `blueprints/*/infra/azure/` as a change that takes effect on merge.

`Environment` is the **branch name** — the Source stage tracks `BranchName: !Ref Environment`.
That is why `Environment=main` means "merges to main deploy". Deploying the pipeline with
`Environment=test` gives a parallel pipeline with its own `aidlc-test-*` stacks.

`Environment` is capped at `[a-z0-9]{1,4}` — four characters, no hyphens — in `pipeline.yml`
and in every blueprint template, because it is part of each stack name and of the
`stack/${Application}-${Environment}*` prefix `BuildPipelineRole` scopes to. A parallel
environment therefore needs a short branch name; `staging` fails parameter validation. Widening
it means editing every template that declares the parameter, not just the pipeline.

`Application` is `aidlc`. Its `AllowedPattern` caps it at 10 characters, which is why it isn't
the repo name.

## Terraform, for Azure/Entra only

AWS is CloudFormation. Terraform exists here solely because CloudFormation cannot reach an
Entra tenant. Don't reach for it for anything with an AWS resource type.

Modules live at `blueprints/<name>/infra/azure/`, alongside the blueprint's `infra/`
CloudFormation. One CodeBuild project — `TerraformProject` in `pipeline/pipeline.yml` — runs all
of them; each `Terraform` stage action supplies `TF_WORKING_DIR` and `TF_STATE_KEY`, the way
`CONTAINER_TARGET` parameterizes the container build. Adding a module means adding an action, not
adding a project.

- **State** is S3 (`TerraformStateBucket`), one key per module, locked with `use_lockfile=true`.
  S3-native locking, so there is no DynamoDB table.
- **Credentials** are the three `ARM_*` variables, resolved from
  `<app>/<env>/azure/terraform-credentials` as CodeBuild `SECRETS_MANAGER` env vars. The
  `azuread`/`azurerm` providers read them natively, so no credential reaches a `.tfvars`, a
  Terraform variable, or state. Never pass one as `-var`.
- **`backend "s3" {}` stays empty** in the module. Every value arrives via `-backend-config`, so
  a module is environment-agnostic and the repo holds no bucket or account names.
- **Entra objects can't take key/value tags.** Graph `application` takes `tags` as a flat string
  list, so the four `cornell:*` values are encoded `"cornell:owner=..."`. That divergence is
  forced by the API — see `blueprints/entra-probe/README.md`.
- **`azurerm` will not work yet.** It needs an Azure subscription in the tenant *and* an Azure
  RBAC assignment for the service principal. A Global Administrator directory role grants
  neither — it is a directory role, not resource-plane access. `azuread` needs only the tenant.

## Conventions that are load-bearing

Not style. Breaking these produces failures that look like something else.

**Tag every resource with all four:** `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. These feed inventory and the cost
dashboard, so an untagged resource is invisible to the observability work. Owner and deployment
id arrive as stack parameters; blueprint name and version belong to the template — hardcode the
name, bump the version default in the PR that changes the blueprint.

**Name stacks `<application>-<environment>-<name>`**, e.g. `aidlc-main-hello-world`.
`BuildPipelineRole` scopes its CloudFormation permissions to
`arn:...:stack/${Application}-${Environment}*`, so a stack named outside the convention
**cannot be deployed by the pipeline** — you get an opaque authorization failure, not a naming
complaint. Same for the CodeBuild project name prefix.

**Register every CloudFormation template in `pipeline/stacks.yml`.** That registry is what PR
checks lint, and `pipeline/validate_stacks.py` fails the build on an unregistered template as
well as a registered one that doesn't exist. Add the entry in the same PR as the template.

**Terraform modules are not in that registry** — it is a CloudFormation registry, and Terraform
is not CloudFormation. They get the equivalent protection from a different direction:
`validate_stacks.py` cross-checks every `blueprints/*/infra/azure/` directory holding `.tf`
files against the `TF_WORKING_DIR` values in `pipeline.yml`, in both directions. A module with
no action, or an action naming a directory that isn't there, fails PR checks.

**A `deployed_by: pipeline` entry needs a matching action in `pipeline.yml`.** Registering a
blueprint is only step 2 of three — without the action the stack deploys nothing, and it fails
*silently*: green PR, all stages `Succeeded`, no stack. `validate_stacks.py` now fails on this
in both directions, so it is a review-time error rather than a mystery, but the mirroring is
still done by hand on purpose.

**Pass every parameter explicitly from the pipeline.** Template defaults exist so a stack can be
deployed by hand for debugging — they are not the real values. A blueprint should deploy
identically by hand and by pipeline.

**Preserve the pipeline's mechanics.** `pipeline/pipeline.yml` and `pipeline/codebuild.yml` were
adapted from a known-good reference pipeline. Change their *shape* when a blueprint needs
something; don't "improve" the source stage, artifact handling, role assumptions, or the digest
export.

## Before you push

```sh
tools/check
```

CI runs that same script. Prerequisites are `uv` **and `terraform`** — uv fetches Python,
pyyaml and cfn-lint itself; terraform has to be a real install (`brew install hashicorp/tap/terraform`),
and CI gets it from `hashicorp/setup-terraform`. Never document or run the bare `cfn-lint` /
`python pipeline/validate_stacks.py` / `terraform validate` forms — they fail on a clean machine.

## Gotchas that have already cost time

- **`cfn-lint --region` takes `nargs='+'`.** `cfn-lint --region us-east-1 <paths>` parses your
  template paths as region names, lints **nothing**, and exits 0. A literal `--` before the
  paths is mandatory. `tools/check` handles this.
- **`AWS::SSM::Parameter` takes `Tags` as a map**, not the usual list of `Key`/`Value` pairs.
  Every other resource here uses the list form.
- **CodeConnections connections need a human browser handshake.** CloudFormation creates them
  `PENDING`; until someone completes it in the console the Source stage fails with a
  permissions error that never mentions the handshake. Connections are per-account and cannot
  be shared across accounts.
- **The org allowed-actions policy permits only github-owned actions plus
  `hashicorp/setup-terraform@*`.** Any other `uses:` fails the whole run as `startup_failure`
  with no job logs, which reads like a broken workflow file. Install tools via `pip`/`run:`
  instead of reaching for a marketplace action.
- **`AWS::SecretsManager::Secret` must not use `SecretString` here.** That property is enforced
  on every stack update, and `PipelineDeploy` redeploys the pipeline stack on every merge — so a
  placeholder in the template resets the live credential to the placeholder several times a day.
  Use `GenerateSecretString` (evaluated only at create) and inject the real value with
  `put-secret-value`. Editing the `GenerateSecretString` block later *does* clobber it.
- **Terraform state must not live in the artifact bucket.** `deployment-artifacts-*` expires
  objects after 30 days, which would delete state and orphan everything Terraform manages.
  `TerraformStateBucket` is separate, versioned, lifecycle-free and `Retain`-on-delete.
- **`.terraform.lock.hcl` is committed, deliberately.** It was in `.gitignore` originally.
  Committing it is what makes a laptop, PR checks and CodeBuild resolve identical provider
  versions; ignoring it lets them drift silently.
- **`terraform_wrapper: false`** in `hashicorp/setup-terraform`. The wrapper replaces the binary
  with a script that captures output, and `tools/check` depends on real exit codes.

## Deliberately not built

Scaffolding these early defeats the workshop's purpose. Don't pre-build them without being
asked:

- `blueprints/course-chatbot/` — managed Bedrock Knowledge Base, Teams bot, Strands agent
- `builder-mcp/` — the MCP server that searches blueprints and creates deployment repos
- `observability/`

`ContainerBuildProject`, `ContainerRepository` and `pipeline/codebuild.yml` **are** defined and
known-good, but no stage invokes them yet because nothing needs an image. Wiring one is a Build
stage action plus a Dockerfile — see `pipeline/README.md`.
