---
name: diagnose-deploy
description: Diagnose a failed or misleading deployment in this repo — a green PR that produced no stack, an opaque CloudFormation authorization error, a Source stage permissions failure, a GitHub Actions startup_failure with no logs, or cfn-lint passing when it should not. Use when a merge did not deploy what was expected, or when a pipeline stage or PR check fails for a non-obvious reason.
---

# Diagnosing a deployment

Most failures in this repo present as **something other than their cause**. Match the symptom
first; the obvious reading is usually wrong.

## Symptom → cause

| Symptom | Actual cause |
|---|---|
| PR green, all pipeline stages `Succeeded`, **no stack exists** | `deployed_by: pipeline` in `stacks.yml` with no matching action in `pipeline.yml`. Nothing was asked to deploy, so nothing failed. |
| Opaque CloudFormation **authorization** failure on deploy | Stack name outside `<application>-<environment>-<name>`. `BuildPipelineRole` scopes to `stack/${Application}-${Environment}*`. It is a naming bug reported as a permissions bug. |
| Source stage fails with a **permissions** error | The CodeConnections connection is still `PENDING`. It needs a human browser handshake in the console; the error never mentions it. |
| GitHub Actions run fails as **`startup_failure`, no job logs** | A `uses:` referencing a non-github-owned action. Org policy allows only github-owned actions plus `hashicorp/setup-terraform@*`. Reads like a broken workflow file. |
| `cfn-lint` exits 0 having linted **nothing** | `--region` takes `nargs='+'`, so `cfn-lint --region us-east-1 <paths>` parses the paths as region names. A literal `--` before the paths is mandatory. `tools/check` handles this. |
| Deploy succeeded but the resource is **missing from inventory / cost dashboard** | Missing one or more of the four `cornell:*` tags. Untagged resources are invisible to the observability work. |
| `AllowedPattern` failure on `Environment` before anything is created | `Environment` is `[a-z0-9]{1,4}` — four chars, no hyphens. `staging` and `feature-x` fail validation. |
| Stack deploys by pipeline but **not** by hand, or vice versa | Parameters left to template defaults instead of being passed explicitly from the pipeline. Defaults are for hand-debugging, not real values. |
| Second deployment of a blueprint collides on resource names | The blueprint hardcodes its names to `<app>-<env>-<name>` and is a singleton (`hello-world` is, deliberately). Real blueprints need a `DeploymentName` parameter. |
| Container-backed stack runs a **stale image** | Deployed by tag rather than by `#{<Namespace>.CONTAINER_DIGEST}`, or the Build action lacks a `Namespace` so the digest resolved to nothing. |
| Unregistered-template error for a file you never meant to deploy | `validate_stacks.py` rglobs the whole repo for `*.yml` containing `AWSTemplateFormatVersion`; its `SKIP_DIRS` is only `.git`, `.github`, `node_modules`, `.venv`, `__pycache__`. A scratch template anywhere else trips it. |

## First move, always

```bash
tools/check
```

CI runs this exact script, so green here means green on the PR. Its registry output prints
`<- deployed by a pipeline action` next to each wired template — **a missing marker is the
silent no-stack failure**, visible before merge.

Never run bare `cfn-lint` or `python pipeline/validate_stacks.py`; both fail on a clean
machine and neither is the real check.

## Reading the pipeline

```
Source ............ webhook on the branch named by Environment, starts within seconds
PipelineDeploy .... the pipeline deploys itself from pipeline/pipeline.yml
Build ............. container images, digest exported
BlueprintDeploy ... one CloudFormation action per blueprint stack
```

`Environment` **is the branch name** — the Source stage tracks `BranchName: !Ref Environment`.
So `Environment=main` is what makes "merges to main deploy". If a merge did not trigger
anything, check which branch the pipeline you are looking at actually tracks; a pipeline
deployed with `Environment=test` only ever watches `test`.

`PipelineDeploy` deploys the pipeline over itself, and `RestartExecutionOnUpdate` reruns from
the top under the new definition. A PR that edits `pipeline.yml` therefore takes effect on the
same run that deployed it — which is normal, not a loop.

## Before concluding "the pipeline is broken"

Check in this order — cheapest first:

1. `tools/check` locally. Most of the table above is caught here.
2. Is the template registered in `stacks.yml`, **and** is there an action in `pipeline.yml`?
   Both directions are required; `validate_stacks.py` checks both.
3. Does the stack name match `<application>-<environment>-<name>` exactly?
4. Is the connection `AVAILABLE`, or still `PENDING` from a fresh bootstrap?
5. Is the branch the pipeline tracks the branch you merged to?

## Constraints that are not negotiable while debugging

Do not relax these to make a deploy work — ask instead:

- **No click-ops.** Never fix a broken stack in the console; the repo is the source of truth
  and the next pipeline run will revert it anyway.
- **Never commit a credential.** This repo is public and secret scanning is **disabled** by an
  enforced org security configuration, so nothing will stop you. Secrets live only in AWS
  Secrets Manager.
- **`main` is PR-only** with one human approval, and **nobody can approve their own PR** — a
  fix always needs a second person.
- **Every merge to `main` deploys to a shared AWS account.** A speculative "let's see if this
  works" merge is a change to everyone's environment. Test with a short-named parallel branch
  and its own `Environment` instead.
