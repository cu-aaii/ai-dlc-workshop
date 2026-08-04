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

## Where things live

A monorepo. `README.md` has the annotated tree; what matters when deciding where to put
something:

| | |
|---|---|
| `blueprints/<name>/` | the deploy surface — one self-contained blueprint each, `blueprint.yaml` + `infra/` (+ `src/`, `infra/azure/`) |
| `packages/<name>/` | a component that isn't a blueprint and isn't the deploy path, self-contained with its own `pyproject.toml` and lockfile |
| `pipeline/`, `bootstrap/` | the deploy path and the account baseline |
| `docs/aidlc-rules/` | vendored methodology, read-only |
| `docs/aidlc/` | this repo's own AI-DLC record — historical |
| `docs/decisions/` | one file per decision made on purpose |
| `<component>/Dockerfile` | one per component that ships an image, in that component's own directory, with a **named target** — there is no root `Dockerfile` |

**Two paths cannot move, and one of them cannot be moved even by a PR that also updates every
reference to it:**

- **`pipeline/pipeline.yml`.** The running pipeline's `PipelineDeploy` stage deploys the pipeline
  from that literal `TemplatePath`. A commit that relocates it makes that stage fail *before* it
  can pick up the new location, so the pipeline never self-updates and recovery is a by-hand
  `aws cloudformation deploy` from an account nobody here has. Blueprint templates move safely
  because `PipelineDeploy` runs first and `RestartExecutionOnUpdate` reruns from the top.
- **`blueprints/`.** Named in a `TemplatePath` in `pipeline.yml` and globbed by
  `catalog._load_local` in the builder-mcp package.

Anything else can be rearranged, provided `tools/check` still passes.

## The AI-DLC workflow rules

`docs/aidlc-rules/` is a **verbatim vendored copy** of the `aidlc-rules/` directory from
[awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows) — the AI-DLC methodology
the workshop teaches. Provenance and re-sync instructions are in `README.md`. Note the path is
under `docs/`, not the repository root where upstream ships it.

Keep it byte-identical to upstream — **do not edit anything under `docs/aidlc-rules/`**, including
to fix a lint or a typo. Local changes are what make the next upstream release impossible to take
cleanly, and the re-sync is a delete-and-replace that would silently discard them. Anything this
repo needs to say about the rules goes here or in `README.md`.

Not to be confused with `docs/aidlc/`, which is this repo's own record of how things here were
built — historical, editable, and not the methodology.

**When the user invokes AI-DLC, read and follow
`docs/aidlc-rules/aws-aidlc-rules/core-workflow.md`, and resolve its rule-detail references
against `docs/aidlc-rules/aws-aidlc-rule-details/`.** That second half is required:
`core-workflow.md` resolves rule details from four hardcoded paths
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

**A `blueprint.yaml` must name a registered template.** The manifest is the contract
`blueprint_search` hands a builder, so one pointing at an unregistered or nonexistent template
advertises a blueprint whose `deployment_create` opens a PR that cannot deploy. Write the manifest
in the same PR as the template, not before it — `validate_stacks.py` fails on the gap. A template
with no manifest is fine and normal: builder-mcp is platform infrastructure, not a catalog entry.

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
- **`validate_stacks.py --list` must emit LF, not the platform newline.** `tools/check`
  word-splits that output into cfn-lint's arguments, so on Windows a CRLF left a trailing
  carriage return on every path but the last and cfn-lint reported `E0003 <template> could not be
  processed by glob.glob` — which reads like a broken template, not a broken path, and made
  `tools/check` unable to pass on a Windows checkout at all while CI stayed green. The `--list`
  branch reconfigures stdout; don't undo it.
- **`uv` picks a 32-bit Python if that's what it finds.** `packages/builder-mcp/.python-version`
  pins the interpreter, so `uv run` fetches a 64-bit CPython. Without it, on a machine whose only
  Python is `x86`, `cryptography` has no wheel and the install disappears into a failing Rust
  build.
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
- **A managed-embedding Bedrock knowledge base rejects `ChunkingConfiguration`.** The
  CloudFormation schema accepts the block, so cfn-lint passes it clean and the deploy fails at
  `CREATE_FAILED` with *"A chunking strategy cannot be specified with a managed embedding model."*
  This cost a rolled-back rehearsal stack; on `main` it would have blocked every track's merges.
- **Verify a bucket's region before pointing anything at it.** `aidlc-kb-ingestion-bucket` is in
  **`us-east-2`** despite everything in this repo deploying to `us-east-1`, and the Bedrock managed
  S3 connector is same-region only. `aws s3api get-bucket-location` returning `null` means
  `us-east-1`. Use `aidlc-kb-ingestion-890349359349` instead.
- **`AWS::Bedrock::KnowledgeBase` takes `Tags` as a map**, like `AWS::SSM::Parameter` and unlike
  everything else here. Copying a `Key`/`Value` tag block onto it fails cfn-lint.
- **`AWS::Bedrock::DataSource` has no `Tags` property at all**, so the four-tag rule is impossible
  on it. `blueprints/knowledgebase` mirrors its id into SSM so inventory has a join key; that is
  the pattern for any future untaggable resource.
- **`ConnectorParameters` on a Bedrock data source is free-form `Json`.** cfn-lint validates
  nothing inside it, so a misspelled key passes `tools/check` and fails at deploy — in the shared
  account. Treat edits in that block as untested code.
- **A bad Bedrock data source HANGS the deploy instead of failing it.** Bedrock marks the data
  source `FAILED` in under a second and CloudFormation keeps reporting `CREATE_IN_PROGRESS` —
  observed for over twenty minutes. On the shared pipeline that stalls `BlueprintDeploy` and blocks
  every other track's merges, which is strictly worse than a red pipeline. Rehearse any
  `ConnectorParameters` edit as an `Environment=test` stack and read the status from
  `aws bedrock-agent list-data-sources`, not from the stack.
- **`connectionConfiguration.bucketOwnerAccountId` is required, always.** The AWS connector
  reference marks it "Conditional — required for cross-account access"; that is wrong. Omitting it
  for a same-account bucket fails validation with *"Member must not be null"* — and it fails via
  the hang above, not via a red stack. Every AWS example includes it.
- **CloudFormation never ingests through a Bedrock data source.** `CREATE_COMPLETE` is compatible
  with an entirely empty knowledge base, and Bedrock has no native scheduled sync. Something in
  the stack has to start the job, and on this repo's no-CLI deploy path it should also assert the
  result — see `blueprints/knowledgebase/docs/decisions.md`.
- **`"secret has an invalid format or missing values"` usually is not about the secret.** Bedrock
  emits it both for wrong secret key names *and* for attaching a SharePoint data source to a
  customer-managed knowledge base — a path it cannot service at all. Check the knowledge base type
  before rewriting a correct secret; that mistake costs hours.
- **A SharePoint data source cannot be purged in place.** No document-level deletion
  (*"Invalid data source type [SHAREPOINTV3] provided"*), and narrowing scope does not retroactively
  delete what is already indexed — the connector can no longer see it to diff it. Delete and
  recreate the data source, which only clears the index if its `DataDeletionPolicy` is `DELETE`.
  That is why `blueprints/knowledgebase` sets `DELETE` there and `RETAIN` on its S3 source.

## Scaffolded but not built

Each of these has a directory and a README describing what goes in it and how to wire it. The
README is the deliverable; the contents are the workshop's work, and filling them in
unprompted defeats the point. **None of them deploys anything** — no template, no image target,
no `pipeline/stacks.yml` entry, no pipeline action — which is what keeps a merge to `main` from
creating resources nobody asked for:

- `blueprints/course-chatbot/` — the Lambda handler exists; the Teams frontend, the template
  and the image target do not. Deliberately has **no `blueprint.yaml`** until its template
  exists, so the Builder cannot offer a blueprint that can't deploy. Its knowledge base is no
  longer a gap: `blueprints/knowledgebase/` deploys one and hands off the identifiers through
  SSM and a retrieval managed policy.
- `blueprints/course-chatbot/infra/azure/` — Terraform for the Bot Framework side, still just
  a README. The pipeline does now have a Terraform stage (added for `entra-probe`), and
  `validate_stacks.py` cross-checks modules against it in both directions — but a directory
  only counts as a module once it holds a `.tf` file, so the first `.tf` here has to arrive in
  the same PR as its Terraform action.
- `observability/` — the dashboard, and the harder question of serving a unit its own view
  without giving it AWS access.
- `docs/decisions/` — empty but for the format. Track D's inter-block protocol decision is the
  first one due.

`packages/builder-mcp/` **is** built: seven tools, 41 tests, an AgentCore stack, registered and
wired to both a Build and a `BlueprintDeploy` action. It is the worked example for everything
above — read its `SPEC.md` and `infra/builder-mcp.yml` before writing a second one.

`ContainerBuildProject` and `ArmContainerBuildProject` are both live; `pipeline/codebuild.yml`
handles the ECR login and the digest export. Adding an image is a Build stage action plus a
`Dockerfile` with a named target in the component's own directory — the action sets
`CONTAINER_CONTEXT` to that directory and `CONTAINER_TARGET` to the target, so **the two must
agree with where the component actually lives**; a stale `CONTAINER_CONTEXT` fails the build with
a missing-path error that says nothing about the move that caused it. See `pipeline/README.md`.
