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

## The rules for this repo

Work in this repo follows **AI-DLC**, the methodology published at
<https://github.com/awslabs/aidlc-workflows/tree/main/aidlc-rules>. Treat that directory as the
authoritative rule set: `aws-aidlc-rules/` holds the core workflow (`core-workflow.md`) and
`aws-aidlc-rule-details/` holds the detail files the core rules pull in on demand
(`common/`, `inception/`, `construction/`, `extensions/`, `operations/`).

The rules are **not vendored into this repo** — read them from upstream when a task needs them,
and pin to a release rather than assuming `main` matches what you read last time.

What it changes about how a task runs:

- Activation is conversational — a request that starts with **"Using AI-DLC, ..."** runs the
  workflow; other requests are ordinary work.
- Phases are **Inception** (what and why) → **Construction** (how) → Operations (not used here).
  Only the stages that add value to the request get executed.
- Clarifying questions go in **files, as structured multiple choice** — not in chat.
- Every phase is **gated on human approval**: the agent proposes, the human approves. That lines
  up with this repo's PR-only rule, so nothing merges on the agent's own judgment.
- Generated artifacts land in `aidlc-docs/`.

Where AI-DLC and the constraints below disagree, **the constraints below win** — they come from
Cornell's platform design and from an AWS account other people share.

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
- **`main` is PR-only**, one human approval, enforced by branch protection.
- **All four `cornell:*` tags on every resource** (see below).

## How a merge becomes a deployment

```
approved PR merged to main
  └─ Source ............ webhook, starts within seconds
  └─ PipelineDeploy .... the pipeline deploys itself from pipeline/pipeline.yml
  └─ BlueprintDeploy ... one CloudFormation action per blueprint stack
```

`Environment` is the **branch name** — the Source stage tracks `BranchName: !Ref Environment`.
That is why `Environment=main` means "merges to main deploy". Deploying the pipeline with
`Environment=test` gives a parallel pipeline with its own `aidlc-test-*` stacks.

`Application` is `aidlc`. Its `AllowedPattern` caps it at 10 characters, which is why it isn't
the repo name.

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

CI runs that same script. `uv` is its only prerequisite — it fetches Python, pyyaml, and
cfn-lint on demand at pinned versions, so there is nothing else to install and no venv to
activate:

```sh
brew install uv                                    # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh    # Linux/macOS
irm https://astral.sh/uv/install.ps1 | iex          # Windows (PowerShell)
```

Never document or run the bare `cfn-lint` / `python pipeline/validate_stacks.py` forms — they
fail on a clean machine.

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
- **Nobody can approve their own PR**, so every change needs a second person.

## Deliberately not built

Scaffolding these early defeats the workshop's purpose. Don't pre-build them without being
asked:

- `blueprints/course-chatbot/` — managed Bedrock Knowledge Base, Teams bot, Strands agent
- `builder-mcp/` — the MCP server that searches blueprints and creates deployment repos
- the Terraform stage for Azure/Entra resources
- `observability/`

`ContainerBuildProject`, `ContainerRepository` and `pipeline/codebuild.yml` **are** defined and
known-good, but no stage invokes them yet because nothing needs an image. Wiring one is a Build
stage action plus a Dockerfile — see `pipeline/README.md`.
