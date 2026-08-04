# tiny-chatbot — completion plan

What is left before a builder can say *"I want a chatbot"* to the Cornell Builder and get a
running one, in dependency order. Written 2026-08-04 from a real end-to-end test of the
Builder against this blueprint; every blocker below was reproduced, not predicted.

The blueprint itself is **finished**: template, `Dockerfile`, handler, manifest and
`pipeline/stacks.yml` entry all exist and `tools/check` passes on them. Everything remaining
is in the *path* between the Builder and the pipeline.

Reproduce the current state with:

```sh
cd packages/builder-mcp
uv run python devtools/preview_deploy.py tiny-chatbot --owner <netid>
```

That prints the blockers below and writes the artifacts a registration PR would carry to
`outputs-preview/tiny-chatbot/` (gitignored). It exits non-zero while any blocker remains, so
it doubles as the acceptance check for each step here.

## Order matters

A and B are `builder-mcp` defects that affect *every* blueprint. C and D are `tiny-chatbot`
wiring. Doing C/D first produces a PR that cannot merge, so resist it.

---

## A — Actions land in the wrong pipeline stage

**Blocker for every blueprint. Do this first.**

`patching._insertion_point` anchors the insertion on the `Outputs:` block "that follows the
last stage". That was the end of `BlueprintDeploy` when it was written. `pipeline.yml` has
since grown a `Terraform` stage after it (for `entra-probe`), so stage order is now:

| lines | stage |
|---|---|
| 701–835 | `BlueprintDeploy` |
| 836–858 | `Terraform` |
| 859 | `Outputs:` |

Every action `deployment_create` generates is therefore appended to the **`Terraform`**
stage, while the plan it returns to the builder still says `BlueprintDeploy`. CodePipeline
permits mixed action types in a stage, so this misplaces the deploy *silently* rather than
failing — the failure mode this repo cares most about. `patching.py`'s own module docstring
predicted exactly this ("if pipeline.yml grows a stage after BlueprintDeploy, revisit
`_insertion_point`"); the stage was added and it was not revisited.

- **Fix**: anchor on the end of the `BlueprintDeploy` stage — the next stage header at the
  same indent, falling back to `Outputs:` — instead of on `Outputs:` unconditionally.
- **Also fix the test.** `tests/test_patching.py::test_insert_places_action_inside_blueprint_deploy_stage`
  asserts only that the action lands between the previous action and `Outputs:`. The
  `Terraform` stage is inside that window, so the test passes while the property in its name
  is false. Assert *stage bounds*, not ordering. Without this the fix has no regression net
  and the next stage added re-breaks it.
- **Verify**: `preview_deploy.py` stops reporting `the generated action lands in the
  'Terraform' stage`; `uv run pytest` green.
- **Est**: ~30 min.

## B — Declared inputs never reach the template

**Blocker for multi-instance blueprints. Deferrable for the demo — see triage.**

`deployment_create` builds its overrides as `Application`, `Environment`, `Owner` plus the
manifest's `pipeline_parameters`, and nothing else. Any other declared input is collected
from the builder, validated, written into `deployment.yaml` — and then dropped.

Two live consequences:

- **`tiny-chatbot`** advertises `deployment_name`, and its template declares
  `DeploymentName` (default `tiny-chatbot`) which names the Lambda, the role and the log
  group. A deployment named `my-bot` gets stack `aidlc-main-my-bot` containing a function
  named `aidlc-main-tiny-chatbot` — colliding with the first deployment. The blueprint's
  whole reason for taking a `DeploymentName` (`singleton: false`) does not work.
- **`notify-topic`** advertises `notification_email`, and the hand-written action's own
  comment says email is *"a per-deployment choice a builder makes through the Cornell
  Builder"*. The Builder never passes it, so setting it yields a topic with no subscription
  and no error. The comment describes an intent the code does not implement.

This also breaks CLAUDE.md's *"Pass every parameter explicitly from the pipeline."*

- **Design decision needed**: how a manifest input maps to a CFN parameter. Deriving it
  (`pascal_case(input_name)`) is implicit and silently wrong when names diverge; an explicit
  `parameter_map` in `blueprint.yaml` is safer and self-documenting. **Recommend explicit**,
  because the failure mode of the implicit version is another silent drop. This is a SPEC C1
  manifest change either way, so it wants a `docs/decisions/` entry.
- **Verify**: `preview_deploy.py` reports no `collected but never reaches the template`
  finding, and `aws/parameters.json` shows `DeploymentName` under `resolved` rather than
  `template_defaults_used`.
- **Est**: 1–2 h including the decision.

## C — Wire the container build

`blueprint.yaml` passes `ContainerImageUri: "#{TinyChatbotContainer.CONTAINER_DIGEST}"`, but
no action in `pipeline.yml` declares `Namespace: 'TinyChatbotContainer'` — the Build stage has
exactly one action, `BuilderMcpContainer`. Nothing exports that variable, so the reference
cannot resolve.

- **Fix**: add a Build stage action per `pipeline/README.md` → "Adding a container image" and
  the `add-container-build` skill. `CONTAINER_TARGET=tiny-chatbot`,
  `CONTAINER_CONTEXT=blueprints/tiny-chatbot`, `Namespace: 'TinyChatbotContainer'`.
- **Use the arm64 project.** The template and `Dockerfile` are arm64
  (`public.ecr.aws/lambda/python:3.13`, `Architectures: [arm64]`), so this is
  `ArmContainerBuildProject`, not `ContainerBuildProject`. Building x86 here produces an
  image the function cannot run, and the error surfaces at invoke time, not build time.
- **Deploy by digest, not tag** — `codebuild.yml` exports the digest for exactly this.
- **Verify**: `preview_deploy.py` stops reporting the undefined namespace.
- **Est**: ~30 min.

## D — Flip the registration and add the deploy action

Only after A–C. `pipeline/stacks.yml` registers `tiny-chatbot` as `deployed_by: 'manual'`;
`validate_stacks.py` fails a `manual` entry that the pipeline deploys, so doing this early
gives an unmergeable PR.

- Flip `deployed_by` to `'pipeline'` **and** add the `BlueprintDeploy` action in the same PR —
  `validate_stacks.py` checks both directions, so either alone fails.
- `deployment_create` does **not** do the flip. Until it does, the first deployment of a
  parked blueprint needs this by hand; see the `add-blueprint` skill for the three-file
  mirror.
- **Verify**: `tools/check` green (needs `terraform` installed, not just `uv`);
  `preview_deploy.py` exits 0.
- **Est**: ~15 min.

## E — Rehearse on `Environment=test`, not `main`

Do not let the first run of this be on `main`. A merge to `main` deploys to the shared
account and stalls every other track if it hangs.

- Deploy the pipeline with a ≤4-char branch name (`Environment` is capped `[a-z0-9]{1,4}`,
  so `test` fits and `staging` fails parameter validation) and merge there first.
- **What to check**: the stack reaches `CREATE_COMPLETE`; the Function URL returns the chat
  page on `GET`; a `POST` returns a canned reply. The template's `HasImage` condition means
  an empty `ContainerImageUri` deploys a stack with **no function at all** and still reports
  `CREATE_COMPLETE` — so a green stack is not evidence the chatbot exists. Fetch the URL.
- **Est**: ~1 h, mostly waiting.

---

## Triage, if there is not time for all of it

**Minimum for a working demo: A → C → D → E.** That yields one working chatbot at the
default name.

**B is the one to cut.** It only bites on a *second* deployment of the same blueprint, so a
single demo instance is unaffected. If cut, say so out loud rather than leaving it implicit:
note in `blueprints/tiny-chatbot/README.md` that only one instance is currently safe, and
keep the BACKLOG entry open. Do not cut A — it is 30 minutes and it silently misplaces every
deploy action the Builder writes, for every blueprint, including ones the workshop tracks add.

## Out of scope

`deployment_create` opening a PR that cannot merge (the `manual` flip in D, the missing Build
action in C) is a Builder gap, not a blueprint gap: it plans a single-edit registration for
every blueprint regardless of what that blueprint needs. Tracked in
`packages/builder-mcp/BACKLOG.md` under "Deploy-path correctness". The cheapest durable fix is
a third cross-check in `validate_stacks.py` — it already does this for CloudFormation and
Terraform actions in both directions — so a manifest referencing a namespace no action exports
fails PR checks instead of reaching a builder as a plan.
