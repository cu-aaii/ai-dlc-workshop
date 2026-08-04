# Upstream Reconciliation — 2026-08-04

**Trigger**: `team-c-wip` was 28 commits behind `upstream/main`. Merged at `318e92f`; merge-base was
`416891b` (PR #6), so everything between was unseen while INCEPTION was being written.

**Why this document exists**: the artifacts describe a repository that no longer exists. Several
recorded *decisions* are now contradicted by merged work — in two cases by the reviewer who was
supposed to approve this blueprint. Facts have been corrected in place. **Decisions are collected
here rather than silently rewritten**, because they were user decisions and are the user's to revise.

**Units Generation Part 2 should not run until D1, D2 and D5 below are settled.** Generating units now
would re-plan work already merged and would specify a Dockerfile layout the repo no longer uses.

---

## 1. Facts corrected in place — no decision needed

| Artifact claim | Reality after merge |
| --- | --- |
| "Critical path steps 1-4 have never executed; ECR holds zero images" | **Done.** `pipeline.yml` has a `Build` stage, `ARM_CONTAINER`, `amazonlinux2-aarch64-standard:3.0`, `CONTAINER_TARGET` **and** a new `CONTAINER_CONTEXT`. |
| D-5 "does another team also need the Build stage?" — open, owner Marty | **Answered: yes, and they built it.** |
| `builder-mcp/` "deliberately not built" | **Built.** Full Python package, tests, `infra/builder-mcp.yml`, deployed by the pipeline. |
| D-4 `KnowledgeBaseId` — open, blocks Tier B | **Resolved.** `blueprints/knowledgebase/infra/knowledgebase.yml` exports `KnowledgeBaseId`. |
| "Whether a **managed** KB is CloudFormation-deployable was NOT verified" — flagged as the KB team's risk | **Retired by direct evidence.** `AWS::Bedrock::KnowledgeBase` with `Type: 'MANAGED'` and `EmbeddingModelType: 'MANAGED'` is deployed from a template. |
| "No Terraform stage exists" | **Exists.** `pipeline/terraform.yml`, a `Terraform` pipeline stage, `blueprints/entra-probe/infra/azure/` as the worked example. |

**New conventions our artifacts predate**, all of which `teams-bot` must satisfy:

- **`blueprints/<name>/blueprint.yaml`** — a manifest the Builder MCP reads (`apiVersion`,
  `matches`, `inputs`, `template`, `pipeline_parameters`, `cost`, `data_classification`, `state`).
  Deliberately *not* a CloudFormation template so `validate_stacks.py` and cfn-lint skip it.
- **`validate_stacks.py` now cross-checks Terraform too** — every `blueprints/*/infra/azure/`
  directory containing `.tf` files must match a `TF_WORKING_DIR` in `pipeline.yml`, both directions.
- **The secret pattern is settled and documented**: declare the secret *resource* in CloudFormation
  with a `GenerateSecretString` placeholder, `DeletionPolicy: Retain`, and inject the real value once
  by CLI. See `AzureCredentialsSecret` in `pipeline/pipeline.yml`. This is the pattern the
  `teams-bot` Entra client secret should follow.
- **`AWS::Bedrock::KnowledgeBase` takes tags as a map**, not a list — same shape as
  `AWS::SSM::Parameter`, and now a second instance of that trap.
- **Entra objects cannot take key/value tags.** Graph `application` takes `tags` as a flat string
  list, so the four `cornell:*` values are encoded `"cornell:owner=..."`.
- **`tools/check` now requires `terraform`** as well as `uv`.
- **`main` merge rules changed**: zero approving reviews required; only members of the
  `ai-dlc-workshop` GitHub team may merge. `validate` is the sole automated gate.

---

## 2. Contradicted decisions — these need the user

### D1. "Do not build a Terraform stage" is dead, and it reshapes U0

**Recorded**: turnover §10 "Do not build a Terraform stage"; `requirements.md` §9 argues against it
at length; U0 is "a script in `blueprints/teams-bot/scripts/`, run by a person."

**Reality**: the stage exists and `CLAUDE.md` now makes it the *required* path — "AWS is
CloudFormation. Terraform exists here solely because CloudFormation cannot reach an Entra tenant."
Azure/Entra resources belong in `blueprints/<name>/infra/azure/`, applied by the pipeline.

**The secret-in-state objection is answered, not merely overruled.** Our argument was that
`azuread_application_password` writes the generated secret into Terraform state. The repo's pattern
avoids that entirely: declare the secret resource in CloudFormation, inject the value out of band,
never generate it in Terraform.

**But the research already establishes Terraform cannot do all of U0**, so U0 splits along a line
that is now well evidenced:

| U0 step | Provider | Can it be Terraform? |
| --- | --- | --- |
| Entra app + service principal + credential | `azuread` | **Yes** — matches the new convention |
| Azure Bot Service + MsTeams channel + endpoint | `azurerm` | **Yes in principle — blocked today**, see below |
| Publish to org catalog | none | **No** — delegated-only, app-only "Not supported" |
| Availability scoping to an Entra group | none | **No** — conclusively closed 2026-08-04 |

**The `azurerm` half is blocked by something `CLAUDE.md` states plainly**: *"`azurerm` will not work
yet. It needs an Azure subscription in the tenant **and** an Azure RBAC assignment for the service
principal. A Global Administrator directory role grants neither — it is a directory role, not
resource-plane access. `azuread` needs only the tenant."* Azure Bot Service is an ARM resource, so it
is `azurerm`, so it is blocked until someone provisions a subscription and an RBAC role.

This compounds with the cross-tenant finding already on record: the existing Bot Service resource
lives in **Cornell's** tenant under the *JCB IT NSS* subscription, while the Entra app is pinned to
the **dev** tenant. Two tenants, and the Terraform credentials in Secrets Manager are one service
principal.

**Also newly relevant**: `CLAUDE.md` warns the Terraform stage **applies unattended** — no approval
action, so a merge reaches the Azure/Entra tenant with whatever rights the stored principal holds.
That is a materially different risk posture from "a person runs a script," and it argues for keeping
the destructive-ish parts of U0 out of the pipeline even where Terraform *could* do them.

**Options:**

- **D1-a — split U0 along the evidence.** `azuread` resources as a Terraform module now; Bot Service
  stays scripted until the subscription/RBAC blocker clears; publish and scoping stay human.
  Follows the repo convention as far as it can actually reach.
- **D1-b — keep all of U0 as the human script**, and note the divergence from the new convention.
  Least churn, and the whole of U0 is one-time-per-bot anyway.
- **D1-c — full Terraform** for both provider halves, accepting a blocked module until Azure RBAC
  exists.

### D2. The Dockerfile decision no longer matches the repo

**Recorded**: Application Design Q11 — "one multi-stage Dockerfile, two named targets (`lambda`,
`agent`)", at `blueprints/teams-bot/Dockerfile`.

**Reality**: upstream *relocated* Dockerfiles into their components and added `CONTAINER_CONTEXT` so
each build action names its own context directory. `blueprints/tiny-chatbot/Dockerfile` and
`builder-mcp/Dockerfile` are separate files with their own contexts.

One shared Dockerfile with two targets still works mechanically, but it cuts against the grain of a
convention that was deliberately changed. **Recommend revisiting Q11 toward one Dockerfile per
component**, which also makes each build's context smaller.

### D3. The delivery and review plan is void

**Recorded**: "One PR to `main`, reviewed by **Marty Sullivan**"; "Nobody can approve their own PR."

**Reality**: zero approving reviews are required, and **only `ai-dlc-workshop` team members may
merge**. Separately, `ferminromeroiii` has `push: false` on `cu-aaii` and is not a collaborator, so
it cannot open a same-repo branch or merge anything. Work now proceeds as a **cross-fork PR** from
`ferminromeroiii/ai-dlc-workshop`, which someone with team membership merges.

No decision needed on the mechanism — it is forced. Recorded because three artifacts state the old
model as fact.

### D5. `aidlc-docs/` is gitignored upstream; ours are tracked

Upstream `.gitignore` now carries `aidlc-docs/` alongside `SCRATCHPAD.md` and `PARTICIPANT_BRIEF.md`
— the team treats AI-DLC artifacts as **local working notes**. That is why `upstream/main` has zero
such files. `builder-mcp/aidlc-docs/` is tracked only because it predates the ignore.

Our branch committed **32** files under `aidlc-docs/` in `45c1ae6`. A `.gitignore` entry never
untracks, so they remain tracked and a PR would add all 32 to a repo that decided not to carry them.

- **D5-a — untrack them** (`git rm -r --cached aidlc-docs/`), keeping the files on disk. Matches the
  team convention; the PR carries only `blueprints/teams-bot/` and pipeline wiring.
- **D5-b — keep them tracked** and argue the case: this blueprint's INCEPTION is unusually
  substantial and is the workshop's teaching artifact.

### D6. Tier B is now cheap enough to reconsider for v1

Recorded as "a plausible stretch goal." With `KnowledgeBaseId` real and the managed-KB
CloudFormation risk retired, Tier B is one parameter, one IAM statement for `Retrieve`, and prompt
assembly. **The design requirement stands**: `Retrieve`, never `AgenticRetrieveStream`, because
`Retrieve` makes no FM invocation and so keeps all generation on the gateway.

---

## 2a. Addendum — the track structure, discovered from PR #21

Everything above was written before `blueprints/course-chatbot/` appeared on `main`. That changed
the framing more than any single decision did.

**`course-chatbot` is the workshop MVP blueprint, and this work is one third of it.** Its README
assigns tracks explicitly:

| Track | Owns | Where it goes |
| --- | --- | --- |
| B | Bedrock Knowledge Base: ingestion, chunking, retrieval tuning | `infra/` + retrieval in `src/` |
| **C — this work** | **Microsoft Teams chatbot: Azure Bot Framework front end, AWS backend** | **`infra/azure/` (Terraform) + `infra/`** |
| D | the seam between the three pieces | `docs/decisions/` + a working example |

Three consequences:

1. **A standalone `blueprints/teams-bot/` is withdrawn.** The deliverable is the Teams front end
   *of* `course-chatbot`. Artifacts in this directory still say "the `teams-bot` blueprint"
   throughout; read that as "Track C's part of `course-chatbot`" until they are rewritten.
2. **D1 is settled, and not by us.** Track C's Azure side is designated Terraform at
   `infra/azure/`. The options in D1 are moot; what survives from that analysis is the evidence for
   *where the Terraform boundary falls* — `azuread` yes, `azurerm` blocked on RBAC, catalog publish
   and availability scoping never.
3. **Track D owns the seam**, which is what the channel-agnostic `Envelope` design addressed. That
   is now someone else's decision to make, and ours to supply evidence to.

### D5 is resolved, and the earlier reading in this document was wrong

This document previously recorded that upstream "treats AI-DLC artifacts as local working notes."
**That was a misreading of a bug.** PR #20 establishes that the `aidlc-docs/` pattern was added with
**no leading slash**, so it matched at every depth and silently ignored every track's artifacts.
Track A's tree survived only because ignore rules do not apply to already-tracked files — which is
precisely what hid the bug, since the one tree everyone had read was the one the rule could not
touch.

The real convention is **per-component placement**: `packages/builder-mcp/aidlc-docs/` for Track A,
`blueprints/course-chatbot/aidlc-docs/` for Track C. These artifacts have been moved here to match,
and force-added past the still-unmerged ignore rule the same way PR #21 did.

The cost of the misreading was one commit that untracked 33 files, and a stretch where the only copy
of this document was on a single disk. PR #20 describes that failure mode better than the earlier
draft of this section did: *"A track can believe its artifacts are committed when nothing was ever
staged."*

### PR #21 — ratified, with one blocking objection

Ten Track C requirements questions were answered by Pete on Track C's behalf and
[ratified](https://github.com/cu-aaii/ai-dlc-workshop/pull/21#issuecomment-5179947956). Q1–Q10 all
stand. Four things came back the other way:

- **The gateway constraint is blocking and non-negotiable.** `course-chatbot/src/handler.py`
  constructs `AnthropicBedrock`/`AnthropicBedrockMantle` and calls Bedrock with the execution role,
  bypassing the gateway. Q26 makes **all** model traffic route through Cornell's LiteLLM gateway —
  reaffirmed 2026-08-04 as absolute, no exceptions. The fix is small because the SDK is already the
  right one: the gateway is Anthropic-compatible, so `.messages.create()` is unchanged and only the
  client construction differs. Consequences: gateway-native model IDs, the execution role trades
  `bedrock:InvokeModel` for `secretsmanager:GetSecretValue`, the gateway key needs the
  `GenerateSecretString` + one-time `put-secret-value` treatment, and `extra_body` effort
  passthrough needs testing.
- **Q6 (sideload rather than catalog publish) inverts one of our own findings.** The research
  previously called the app-only automation of Setup Policies useless here, because publishing to
  the catalog makes sideloading moot. Under Q6 it is the opposite: sideload is the **only** Teams
  distribution path that is fully automatable end to end, since catalog publish is delegated-only by
  Microsoft's design and availability scoping has no unattended path at all. **The one interactive
  login dissolves for v1.**
- **Q5 exposes a defect that breaks the Tier A parameter surface.** `deployment_create` passes only
  `Application`, `Environment`, `Owner` and the manifest's `pipeline_parameters`; values declared
  under `inputs` are collected and dropped, silently (#15 finding 2). `SystemPrompt`, `ModelId`,
  `GreetingText` and `TeamsScopes` would all have arrived empty. Read them from SSM at runtime.
- **Q3 versus the AgentCore mandate is unresolved.** Q3 puts Strands in one Lambda; our record has
  AgentCore mandated by Team E. Raised with Marty rather than decided.

Two further facts worth carrying: **a `SecretString` is reset to its placeholder by `PipelineDeploy`
on the next unrelated merge to `main`**, so any secret needs `GenerateSecretString` plus a one-time
`put-secret-value`; and **SharePoint ingestion into the knowledge base has never succeeded** (#18),
so Tier B cannot assume the knowledge base has content in it.

## 3. What did not change

Worth stating so nothing is reopened unnecessarily:

- The **gateway mandate** (Q26) and medium-risk data handling — untouched by any of this.
- **Teams response streaming** as the delivery mechanism, and the delivery seam for multi-party.
- The whole **Microsoft-side CLI picture** — publish is delegated-only, scoping has no unattended
  path. Upstream's Terraform stage does not change that; no provider covers those two endpoints.
- The **two prototype defects** (the `serviceurl` claim read with the wrong casing; the undocumented
  trailing slash) — still the most valuable findings and still easy to reintroduce.
- **Stack naming, the four `cornell:*` tags, and `stacks.yml` registration** — unchanged, and now
  with a Terraform equivalent in the same validator.
