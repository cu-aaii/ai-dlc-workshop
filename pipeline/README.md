# pipeline/

The deploy path, adapted from the AI Innovation Lab reference pipeline. Its mechanics are
known-good and were preserved deliberately; what changed is its shape — it deploys stacks
from blueprint subdirectories rather than one application.

| File | What it is |
|---|---|
| `pipeline.yml` | CodePipeline, both CodeBuild projects, ECR repository, Terraform state bucket, Azure credentials secret, and the IAM roles for all of it. |
| `stacks.yml` | Registry of every CloudFormation template in the repo. |
| `validate_stacks.py` | Enforces that `stacks.yml`, the filesystem and `pipeline.yml` agree — for CloudFormation templates and Terraform modules both. Run by PR checks. |
| `codebuild.yml` | Buildspec for container image builds. Ready, not yet wired to a stage. |
| `terraform.yml` | Buildspec for Azure/Entra Terraform. Wired to the `Terraform` stage. |

## How a merge becomes a deployment

```
merge to main
  └─ Source ............ CodeStarSourceConnection, BranchName = Environment ("main"),
  │                      DetectChanges registers a webhook → starts within seconds
  └─ PipelineDeploy .... deploys pipeline/pipeline.yml over itself
  │                      (so a PR that edits the pipeline takes effect on merge;
  │                       RestartExecutionOnUpdate reruns from the top under the new definition)
  └─ BlueprintDeploy ... one CloudFormation action per blueprint stack
  └─ Terraform ......... one CodeBuild action per Azure/Entra module; plan, then apply
                         the saved plan. No approval action — applies unattended.
```

`Environment` is the branch name, and the Source stage tracks the branch of that name. So
`Environment=main` is what makes "merges to main deploy", and a `test` branch deployed with
`Environment=test` gets its own parallel pipeline and its own `aidlc-test-*` stacks.

`Environment` has `AllowedPattern: '[a-z0-9]{1,4}'` — **four characters, no hyphens**, because
it is a component of every stack name and of the `stack/${Application}-${Environment}*` prefix
that `BuildPipelineRole` scopes to. `test` fits with nothing to spare; `staging` or
`feature-x` fail CloudFormation's parameter validation before anything is created. Pick a short
branch name for a parallel environment, or widen the pattern in both `pipeline.yml` and every
blueprint template together.

Note what CodePipeline does *not* give you: the GitHub side is what makes "a merge" mean "an
approved PR". Without branch protection this pipeline happily deploys a direct push to main.

## Deploy the pipeline for the first time

Requires `bootstrap/` to be deployed and the connection to read `AVAILABLE`.

```sh
aws cloudformation deploy \
  --profile ai-dlc-workshop \
  --region us-east-1 \
  --stack-name aidlc-main-pipeline \
  --template-file pipeline/pipeline.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --role-arn arn:aws:iam::<account>:role/cloudformation-deploy-role \
  --parameter-overrides Application=aidlc Environment=main Owner=ai-sei \
                        RemoteGitRepository=cu-aaii/ai-dlc-workshop
```

After this, never deploy it by hand again — edit `pipeline.yml` in a PR and let the
`PipelineDeploy` stage apply it.

## Stack naming is load-bearing

Stacks are `<application>-<environment>-<name>`, e.g. `aidlc-main-hello-world`.
`BuildPipelineRole` scopes its CloudFormation permissions to
`arn:...:stack/${Application}-${Environment}*`, so a stack named outside the convention
cannot be deployed by the pipeline. Same for the CodeBuild project name prefix.

## Adding a blueprint stack

1. Write the template under `blueprints/<name>/infra/`, with the four `cornell:*` tags on
   every resource.
2. Register it in `stacks.yml` — that is what makes PR checks lint it.
3. Add a `BlueprintDeploy` action in `pipeline.yml` modelled on `HelloWorldCloudFormation`.
   Pass every parameter the template needs explicitly; do not rely on template defaults, so
   the stack deploys identically by hand and by pipeline.
4. Write `blueprints/<name>/blueprint.yaml` — the manifest that puts the blueprint in the
   Cornell Builder MCP's catalog. Steps 1–3 make it deploy; this is what makes a builder able
   to find it. See "Required of every blueprint" in `blueprints/README.md`.

Stages are static CloudFormation, so `stacks.yml` and the pipeline actions are mirrored by
hand. That is on purpose — generating stages from the registry would be the framework the
workshop spec says not to build.

Mirrored by hand, but **not** unchecked. Skipping step 3 used to be invisible: the PR went
green, all three pipeline stages reported `Succeeded`, and no stack appeared, because nothing
had been asked to deploy one. `validate_stacks.py` now fails a `deployed_by: pipeline` entry
that no action deploys, and an action whose template is unregistered. If a template genuinely
should not be pipeline-deployed, register it `deployed_by: manual` and say why in its
`description`.

Skipping step 4 has the same shape one layer up: the stack deploys, and the blueprint is absent
from `blueprint_search` with no error anywhere. `validate_stacks.py` fails a blueprint directory
with no manifest too; a blueprint that genuinely should not be in the builder catalog goes in
`MANIFEST_EXEMPT` with the reason.

## Adding a Terraform module

Terraform is for **Azure/Entra only** — anything with an AWS resource type is CloudFormation.
`TerraformProject` and `terraform.yml` are generic, so adding a module does not mean adding a
CodeBuild project.

1. Write the module under `blueprints/<name>/infra/azure/`. Declare `backend "s3" {}` empty —
   values arrive from `-backend-config`. Take credentials from the provider's native `ARM_*`
   environment variables, never as a Terraform variable, so nothing lands in the plan or in state.
2. Commit `.terraform.lock.hcl` (`terraform init -backend=false` generates it). It is *not*
   gitignored, on purpose — it is what pins provider versions across a laptop, CI and CodeBuild.
3. Add a `Terraform` stage action modelled on `EntraProbeTerraform`, setting `TF_WORKING_DIR` to
   the module directory and `TF_STATE_KEY` to a key nothing else uses.

Nothing goes in `stacks.yml` — that registry is for CloudFormation templates. The mirroring is
still enforced: `validate_stacks.py` cross-checks module directories against `TF_WORKING_DIR`
values in both directions, so a module with no action fails PR checks rather than silently
applying nothing, and an action naming a missing directory fails before it can fail after merge.

### One-time: the credential

The `Terraform` stage cannot succeed until the real credential is injected. `pipeline.yml`
creates the secret with a *placeholder* — `GenerateSecretString`, never `SecretString`, because
`SecretString` would be reapplied on every merge and overwrite the live value. So the first run
after the secret is created fails on authentication, expectedly. Then, once:

```sh
umask 077 && cat > /tmp/az.json <<'EOF'
{"tenant_id":"...","client_id":"...","client_secret":"..."}
EOF
aws secretsmanager put-secret-value \
  --profile ai-dlc-workshop --region us-east-1 \
  --secret-id aidlc/main/azure/terraform-credentials \
  --secret-string file:///tmp/az.json
rm -f /tmp/az.json
```

`file://` rather than an inline string keeps the value out of shell history and out of `ps`.
Rotating the credential later is this command again and nothing else — no code references it.

## Adding a container image build

`ContainerBuildProject`, `ContainerRepository` and `codebuild.yml` are defined and ready but
no stage invokes them, because `hello-world` is pure CloudFormation with nothing to build.
When a blueprint needs a Lambda image:

1. Add a `Dockerfile` in the component's own directory (e.g. `builder-mcp/Dockerfile`)
   with a named target for the component. The build context is that directory, so COPY
   paths are relative to it.
2. Add a `Build` stage action before `BlueprintDeploy` that runs `ContainerBuildProject` with
   `CONTAINER_TARGET`, `CONTAINER_CONTEXT` (the component directory containing the
   Dockerfile) and `DATE_TAG` set (see the reference pattern in `codebuild.yml`).
3. Pass `#{<Namespace>.CONTAINER_DIGEST}` into the blueprint's CloudFormation action and
   deploy by digest, not by tag.
