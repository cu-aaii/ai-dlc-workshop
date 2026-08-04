# Amendment A1 — Repo baseline changed under approved artifacts

**Date**: 2026-08-03
**Trigger**: `origin/dashboard` was force-pushed — the branch was **rebased** onto `main`, pulling in
15 commits of work merged elsewhere (`builder-mcp`, the Azure/Entra Terraform stage, a root
`Dockerfile`, `blueprints/hello-world/blueprint.yaml`).
**Status of the AI-DLC work**: fully intact. `git diff HEAD origin/dashboard -- aidlc-docs/` was empty
before syncing, so every byte of the inception artifacts survived the rebase with only new SHAs. The
pre-rebase tip is `f9d4d57`.

## Why this document exists rather than in-place edits

Four artifacts affected below are **approved**: `requirements.md`, `execution-plan.md`,
`application-design/application-design.md`, and `application-design/services.md`. Rewriting an
approved conclusion in place would destroy the record of what was actually approved and when. So each
affected passage keeps its original text and gains a pointer here. This document supersedes those
passages; it does not pretend they were never written.

Nothing here was caused by a defect in anyone's answers. The repo simply moved.

---

## A1.1 — The no-self-approval constraint no longer exists

**Was** (carried as a hard constraint from Workspace Detection onward): `main` is PR-only with one
mandatory human approval, and nobody can approve their own PR, so every change needs a second person.

**Now** (`CLAUDE.md`, current):

> **`main` is PR-only**, enforced by branch protection: a pull request is required and direct pushes
> are rejected, the `validate` check must pass, and only members of the `ai-dlc-workshop` GitHub team
> may merge. **Zero approving reviews are required** — a team member merges their own PR. That is a
> deliberate workshop-time relaxation of the original one-human-approval rule, and it means the
> `validate` check is the only automated gate between a branch and a deploy.

**Superseded passages**
| Artifact | Location | Original claim |
|---|---|---|
| `requirements.md` | §4.3 RESILIENCY-03 rationale | "changes are still gated — `main` is PR-only with one mandatory human approval and no self-approval (branch protection)" |
| `requirements.md` | §5 inherited constraint 4 | "`main` is PR-only, one human approval, no self-approval." |
| `execution-plan.md` | Success criteria | "`main` reaches deployment only via PR with one human approval, by someone other than the author" |
| `unit-of-work-plan.md` | Q6 premise | Rewritten in place — that plan is **not** approved, so it was corrected directly rather than annotated. |

**Consequence that matters.** RESILIENCY-03 was **exempted** (R5-Q2 = C) partly on the reasoning that
changes are gated in practice even without a formal change-record process. That reasoning is now
weaker: the human gate is gone and `validate` — a lint and registry check — is the only automated
thing between a branch and a shared-account deploy. The exemption itself is a recorded user decision
and is **not** being reopened here. What changes is that its stated compensating control no longer
exists, and this document says so rather than leaving the rationale reading as though it does.

---

## A1.2 — The container build now runs

**Was**: `pipeline.yml` defined `ContainerRepository` and `ContainerBuildProject` but had only three
stages (`Source`, `PipelineDeploy`, `BlueprintDeploy`), none invoking the build. This was cited as
corroborated by `CLAUDE.md`'s own text.

**Now**: `pipeline.yml` has a **`Build` stage** (line 677) whose `BuilderMcpContainer` action invokes
`ArmContainerBuildProject` with `CONTAINER_TARGET=builder-mcp`, and `BuilderMcpCloudFormation`
consumes `"ContainerImageUri": "#{BuilderMcpContainer.CONTAINER_DIGEST}"`. There is a root
`Dockerfile` with a named target per component. **Build → digest → deploy-by-digest is proven end to
end.** There is also a fifth stage, `Terraform`.

**Precision, because the distinction is load-bearing**: the **arm64** project
(`ArmContainerBuildProject`) has an invoker. The **x86** `ContainerBuildProject` still has none — it
was added alongside rather than modified, deliberately, so its known-good definition stays untouched
for future x86 Lambda images. So "no stage invokes the container build" is now false in general and
still true of the x86 project specifically.

**Superseded passages**
| Artifact | Location | Disposition |
|---|---|---|
| `application-design/application-design.md` | §6.1 | Finding largely **falsified**. The pattern is proven; it is no longer "the largest single unknown". |
| `application-design/services.md` | Deployment services table, container row | "no stage invokes them" no longer holds. |
| `execution-plan.md` | Change-impact table row; risk reason; container-build finding | Risk basis weakened — see A1.5. |
| `aidlc-state.md` | Finding raised at Workflow Planning | Corrected in place — a live state file, not an approved artifact. |
| `application-design-plan-clarification.md` | Q10 option A cost: "the pipeline gains a stage it has never run" | The stage now exists. Q10 = A is **less** work than approved: add an action to an existing stage. |

**`CLAUDE.md` is now internally stale** and this is not mine to fix: its closing paragraph still says
"no stage invokes them yet because nothing needs an image," which the same commit's `pipeline.yml`
contradicts. Flagged for whoever owns that file.

---

## A1.3 — A new decision exists that did not exist at Application Design time

Lambda architecture. The approved design says only "container images" because at the time there was
one container path and it had never run. Now there are two, with asymmetric evidence:

- **arm64** — proven end to end by `builder-mcp`. Also cheaper per Lambda GB-second.
- **x86** — `ContainerBuildProject` is known-good by inspection but has still never been invoked.

This is a genuine new choice, not a detail. Asked as **Q8** in `unit-of-work-plan.md` rather than
decided here.

---

## A1.4 — `blueprint.yaml` is now a real, parsed contract

`blueprints/hello-world/blueprint.yaml` exists and `builder_mcp/catalog.py`
(`Blueprint.from_manifest`) parses it. It is loaded into model context by the Cornell Builder MCP, so
a blueprint without one is invisible to the tool that is supposed to find it. The dashboard blueprint
needs one, and no approved artifact mentions it.

Fields with direct consequences for this design:

| Field | Consequence |
|---|---|
| `singleton: true` + the comment "**Real blueprints should take a `DeploymentName` parameter instead**" | The approved design has **no `DeploymentName` parameter**. hello-world hardcodes its bucket name and deployment id, allowing one deployment per app/environment. Following this guidance changes resource naming across every dashboard template. |
| `state: []` with the vocabulary `stateless \| derived \| authoritative` | C-02's snapshot is **`derived`** — reconstructible by re-running the collector, so it needs no backup. That is a real backup/recovery contract value, previously unstated. |
| `data_classification: [public]` | The dashboard exposes account inventory: ARNs, owner NetIDs, deployment ids. Almost certainly **not** `public`. Needs a deliberate value. |
| `cost: baseline_monthly_usd`, `scales_with` | Needs real values; interacts with the deferred FR-8 cost work. |
| `inputs:` | The builder-facing input contract — the MCP surface for this blueprint. |
| `matches:` | Intent phrases the Cornell Builder matches on. |

Asked as **Q9** in `unit-of-work-plan.md`, and folded into **Q3**'s directory-layout options, which
previously omitted the file entirely.

---

## A1.5 — Net effect on the execution plan's risk rating

The approved rating is **Medium**, on four stated reasons. Two changed:

| Original reason | Now |
|---|---|
| Shared-account deploys during the live Aug 3–4 workshop | **Unchanged, and slightly worse** — the human approval gate is gone (A1.1) |
| The registry-without-action silent-failure mode | **Unchanged** — `validate_stacks.py` still catches it in both directions |
| Deny-by-default lockout looking like an outage | **Unchanged** |
| The never-run container build | **Largely resolved** for arm64; still open for x86 (A1.2, A1.3) |

**Assessment: still Medium, for a partly different reason set.** The container-build unknown shrank;
the change-control gate weakened. Not proposing a re-rating — one reason improved and another
degraded, and inventing a precise new number from that would be false precision. Recorded so the
rating is not read as resting on a finding that no longer holds.

---

## A1.6 — Smaller changes, no artifact impact

- **`tools/check` now requires `terraform` as well as `uv`.** Neither is installed on this machine, so
  the check still cannot run here. Previously reported as `uv`-only.
- **`validate_stacks.py` gained a bidirectional Terraform cross-check** (`blueprints/*/infra/azure/`
  against `TF_WORKING_DIR` values). No effect on this blueprint, which is AWS-only.
- **The `Terraform` stage applies unattended** to the Azure/Entra tenant on merge, with no approval
  action. Outside this blueprint's scope; it does change the merge-to-`main` risk profile the
  execution plan describes.
- **`.terraform.lock.hcl` is committed deliberately**, and `AWS::SecretsManager::Secret` must not use
  `SecretString` (it is re-enforced on every `PipelineDeploy`, resetting the live credential). Both
  are new `CLAUDE.md` gotchas; neither touches the dashboard.

---

## What this amendment does not do

- **Does not reopen any user decision.** Q1–Q11, the RESILIENCY-03 exemption, and the four §4.6
  exceptions all stand.
- **Does not rewrite approved text.** Each superseded passage keeps its original wording and gains a
  pointer to the row above.
- **Does not amend `stories.md`.** No story's text depends on either changed fact. US-15 is still
  silent on the Build stage action and the Dockerfiles — the known coverage gap is unchanged, only
  cheaper to close now that the stage exists.
- **Does not edit `CLAUDE.md`.** Its stale paragraph is flagged, not fixed.

---

# Amendment A2 — Monorepo reorganization, same day

**Trigger**: a second sync, hours after A1. **Not** a force-push this time — `git merge-base
--is-ancestor HEAD origin/dashboard` confirmed a clean fast-forward, so no history was rewritten and
nothing needed recovery. 27 incoming commits reorganized the repository.

## A2.1 — Paths moved

| Was | Now |
|---|---|
| `aidlc-rules/` | **`docs/aidlc-rules/`** — still verbatim vendored, still do not edit |
| `builder-mcp/` | **`packages/builder-mcp/`** |
| `aidlc-docs/design/*.md` | **`docs/aidlc/dashboard/design/`** |
| — | **`packages/<name>/`** is now the home for non-blueprint components |
| — | **`docs/decisions/`**, one file per deliberate decision |

`aidlc-docs/` at the repo root — this blueprint's entire inception record — **did not move.** Fixed
reference in `unit-of-work-story-map.md`.

**Unresolved, flagged not decided**: `CLAUDE.md` now says `docs/aidlc/` is "this repo's own AI-DLC
record," and `builder-mcp`'s record was relocated to `docs/aidlc/builder-mcp/`. By that convention this
blueprint's record belongs at `docs/aidlc/dashboard/`. But the **vendored rules hardcode `aidlc-docs/`
paths** in every stage file, so moving it puts the repo convention and the methodology in direct
conflict. Roughly 30 files, and it is a decision, not a cleanup — **left for the user.** Doing it
silently mid-stage would also invalidate every path in this amendment.

## A2.2 — There is no root `Dockerfile` any more

`CLAUDE.md` now states it outright: one Dockerfile **per component directory** with a named target.
The Build stage action supplies `CONTAINER_CONTEXT` (the component directory) **and** `CONTAINER_TARGET`.
Real examples now in the repo: `blueprints/tiny-chatbot/Dockerfile`, `blueprints/aisei-site/Dockerfile`,
`packages/builder-mcp/Dockerfile`.

This directly contradicts what `unit-of-work.md` said hours earlier — it had the dashboard adding two
targets to a root Dockerfile. **Corrected**: one `blueprints/dashboard/Dockerfile` with targets
`collector` and `api`, and `CONTAINER_CONTEXT: blueprints/dashboard`.

**The context choice is forced, not stylistic.** Both images need `core/` (U-01). A context of
`collector/` cannot `COPY` it. So the single-Dockerfile-two-targets shape is what the U-01 → U-02
dependency requires, and a future reader who "tidies" it into two per-directory Dockerfiles will break
both builds.

## A2.3 — New enforced rule: a `blueprint.yaml` must name a registered template

`validate_stacks.py` now fails when a manifest points at an unregistered or nonexistent template, on the
grounds that the manifest is the contract `blueprint_search` hands a builder — so a bad one advertises a
blueprint whose `deployment_create` opens a PR that cannot deploy. `CLAUDE.md` also clarifies that a
template with **no** manifest is fine and normal (builder-mcp is platform infrastructure, not a catalog
entry).

Consequence under Q4 = A's two templates: the manifest names **`dashboard.yml`**, the application stack,
because that is what a builder deploys. `dashboard-storage.yml` is registered in `stacks.yml` but is not
the manifest's entry point. Recorded in `unit-of-work.md`'s `blueprint.yaml` table.

## A2.4 — `observability/` now exists

It was on `CLAUDE.md`'s "deliberately not built" list and now has a `README.md` — which says **"Nothing
here yet."** So it is a documented placeholder for Track E, not an implementation, and the instruction
not to pre-build it still stands.

It matters anyway, because its README states that the four `cornell:*` tags "exist for this track and
nothing else" and names `cornell:deployment-id` as **the join key**. That is the same conclusion the
telemetry amendment reached independently from the other direction. **This blueprint is the first
consumer of a contract Track E owns**, which strengthens the existing recommendation that the queued
telemetry pass not be run as a dashboard-local decision.

## A2.5 — Two new gotchas worth knowing before Code Generation

- **`validate_stacks.py --list` must emit LF, not the platform newline.** `tools/check` word-splits that
  output into `cfn-lint`'s arguments; a CRLF left a trailing carriage return on every path but the last,
  and `cfn-lint` reported `E0003 <template> could not be processed by glob.glob` — which reads as a
  broken template rather than a broken path, and made `tools/check` unable to pass on a Windows checkout
  while CI stayed green.
- **`uv` will pick a 32-bit Python if that is what it finds.** `packages/builder-mcp/.python-version`
  pins the interpreter for that reason. Relevant when U-01 gets its own package metadata: without a pin,
  a machine whose only Python is `x86` has no `cryptography` wheel and the install disappears into a
  failing Rust build.

## A2.6 — What A2 does not change

The unit decomposition, every Q1–Q9 answer, all three artifacts' substance, the story map, and the
dependency graph are unaffected. A2 is a **path-and-packaging** amendment: two concrete corrections
(§A2.2 Dockerfile, §A2.1 doc reference), one new constraint to satisfy (§A2.3), and one flagged decision
left to the user (§A2.1, whether `aidlc-docs/` relocates). **§6.4 remains open and unchanged** — none of
these commits altered the pipeline's stage order.
