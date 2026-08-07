# Design — The Observability Contract (concrete draft)

**Status**: Draft for review. Grounds the abstract contract in
`aidlc-docs/design/composable-dashboards.md` §2 against artifacts that already exist on other
branches. No code implied; a spec to be ratified before the queued telemetry Requirements pass
(FR-9) authors against it.
**Date**: 2026-08-03
**Companion**: `composable-dashboards.md` is the *why* (two dashboards, one contract). This is the
*what* — the concrete shape, derived from real files rather than invented.

---

## 0. What changed the inputs to this draft

Earlier drafts designed the telemetry convention in a vacuum, on the stated basis that no second
emitter existed. A branch survey (2026-08-03) shows that is no longer the whole story:

| Branch | What it contributes to this contract |
|---|---|
| `origin/main` | `builder-mcp` is merged and **already parses `blueprints/*/blueprint.yaml`** (`builder_mcp/catalog.py`). A per-blueprint manifest contract exists, is loaded into model context, and has a defined schema. |
| `origin/b-knowledgeBase` | A `knowledgebase` blueprint with a **`Lambda::Function`** — the first blueprint with compute. But see §4: it is a deploy-time *ingestion verifier*, not a runtime usage path, so it is a weak emitter. |
| `origin/team-d` | **Track D — inter-block communication and deployment isolation**, at Reverse Engineering. This is the track the `cornell:deployment-id`-under-composition decision must be made *with*, not on the dashboard branch alone. |
| `origin/add-terraform-stage` | The Azure/Entra Terraform stage now exists (`entra-probe` + `pipeline/terraform.yml`), so a blueprint can have **non-AWS resources** — the contract cannot assume everything is CloudFormation-tagged. |

**Consequence for the design:** the contract should *extend the existing `blueprint.yaml` manifest*,
not introduce a parallel mechanism, and it must not assume a blueprint has a runtime usage path.

---

## 1. The manifest already exists — extend it, don't reinvent it

`blueprints/hello-world/blueprint.yaml` on `main` is the real, parsed contract
(`Blueprint.from_manifest` in `builder_mcp/catalog.py`). Its current shape:

```yaml
apiVersion: builder.cornell.edu/v1
kind: Blueprint
metadata: { name, version, maintainer, maturity }
summary: >- ...
matches: [ ... ]                 # intent-matching phrases for the Cornell Builder
inputs: { <name>: {type, required, description} }
template: blueprints/<name>/infra/<name>.yml
pipeline_parameters: { SourceCommitId: "#{GitRepository.CommitId}" }
singleton: true|false
cost: { baseline_monthly_usd, scales_with: [] }     # <-- already here
data_classification: [ public | ... ]
state: []                        # stateless | derived | authoritative  <-- already here
```

Two of the contract's concerns are **already declared here**: `cost` and `state`. The manifest is
therefore the natural home for the observability contract's *declarative* half. The MCP already
reads it, `validate_stacks.py` already ignores it by design (it declares no
`AWSTemplateFormatVersion`), and the version is kept in lockstep with the template's
`BlueprintVersion`. Adding telemetry declarations here costs no new plumbing.

---

## 2. The contract has three parts, not two

`composable-dashboards.md` framed two *layers* (tags, telemetry). Grounding it against real
artifacts splits the telemetry layer by *who acts*, giving three concrete parts:

### Part A — Tag contract (exists, enforced)
The four `cornell:*` tags on every **AWS** resource. Pull-based, read from outside via the
Resource Groups Tagging API. Already enforced repo-wide. **Gap surfaced by `add-terraform-stage`:**
Azure/Entra resources created via Terraform are not reachable by the AWS Tagging API, so the tag
contract is AWS-only. Non-AWS resources need either an equivalent tag convention in their own
provider or an explicit "not inventoried" declaration in the manifest (§5, open #7).

### Part B — Manifest declaration (extend `blueprint.yaml`)
A blueprint *declares*, statically, what it emits and how it should be read. Proposed additions to
the manifest, alongside the existing `cost` / `state`:

```yaml
telemetry:
  emits: true|false              # does this blueprint emit runtime usage at all?
  # when emits: true --
  namespace: "Cornell/Blueprints/<name>"      # CloudWatch namespace (candidate mechanism, §3)
  key: cornell:deployment-id                   # the join key; see §6 for composition caveat
  counters:                                    # business-level usage counters this blueprint reports
    - name: queries_answered
      unit: Count
      description: chatbot queries served
    - name: documents_indexed
      unit: Count
      description: documents added to the knowledge base
```

`emits: false` is a first-class, honest state — a blueprint with no runtime usage (e.g. `hello-world`,
or the KB verifier per §4) declares it and is *inventoried and cost-attributed but reports no usage*,
exactly as the graceful-degradation principle in `composable-dashboards.md` §2.3 requires. A missing
`telemetry:` block is treated as `emits: false`.

### Part C — Runtime emission (the code convention)
When `emits: true`, the blueprint's compute emits the declared counters at runtime, keyed by its
`cornell:deployment-id`, via the mechanism in §3. This is the only part that requires blueprint
*code*, and it is the part that does not exist for any blueprint yet (§4).

**Why three, not two:** Parts A and B are *declarative and checkable statically* — a PR check can
verify the manifest declares what its template tags, without deploying anything. Part C is
*runtime and only verifiable live*. Separating them means conformance is mostly enforced at PR
time (cheap, like `stacks.yml`), and only the emission itself needs a live check.

---

## 3. Emission mechanism (recommendation, for ratification)

**Recommendation: CloudWatch EMF (Embedded Metric Format) to the blueprint's own log group,
namespaced per blueprint and dimensioned by `cornell:deployment-id`.** Rationale against the
constraints in `composable-dashboards.md` §8:

- **Serverless-first / no new infra:** every Lambda already writes to CloudWatch Logs; EMF is a
  log-line format that CloudWatch extracts into metrics with zero additional resources. The KB
  Lambda already has `logs:PutLogEvents` (§4).
- **Write-own / no-read-peer (Track D isolation, §6):** a deployment writes only to its own log
  group and its own metric dimension; it has no read path to another deployment's metrics. This
  satisfies the isolation guarantee Track D is defining, which a shared EventBridge bus would
  complicate.
- **Central read without central coupling:** the central view reads the `Cornell/Blueprints/*`
  namespace by dimension; a blueprint never learns the central account's internals.

Alternatives considered and why not (now): a shared **EventBridge bus** (richer routing, but a
cross-deployment surface that fights Track D isolation); a **metrics endpoint** (another service to
run, deploy, and secure — against serverless-first). Ratify or overrule at review (open #2).

---

## 4. Honest status of the "second emitter" trigger

The telemetry amendment set the `observability/` extraction trigger at *"when a second blueprint
emits metrics."* Grounding that against `b-knowledgeBase`:

- The KB blueprint **has compute** (`AWS::Lambda::Function`, `python3.13`), so it is closer to a
  real emitter than `hello-world` (which has none).
- **But that Lambda is a deploy-time ingestion verifier** — its description: *"Ingests the
  knowledgebase data source and fails the stack unless the documents are indexed and answerable."*
  It runs during deployment, not on user requests. It has **no ongoing usage to count** — no
  queries served, no sessions. It is not a runtime usage path.

So the honest reading: **the trigger is nearer but has not fired.** A blueprint that genuinely emits
*usage* (the Teams chatbot's queries-answered, a document pipeline's docs-ingested) still does not
exist on any branch surveyed. The first real emitter will be the chatbot when it lands.

**What to build now, given that:** Parts A and B (tags + manifest declaration) are buildable and
checkable today against real blueprints. Part C (runtime emission) should be **proven against a
deliberately trivial emitter** — e.g. teach the KB verifier to emit one `documents_indexed` counter,
or add a token counter to `hello-world` — so the contract has an end-to-end proof before the chatbot
depends on it, rather than shipping a reader with nothing to read. This matches the amendment's own
"contract plus a reader proven against a trivial emitter, not a populated usage dashboard."

---

## 5. Where each part lives, and the `observability/` move

- **Parts A + B (declarative):** in the repo already — tags in each template, manifest in each
  `blueprint.yaml`. A PR check extension (in `pipeline/validate_stacks.py` or beside it) verifies
  manifest ↔ template agreement, the same way registration is checked today.
- **Part C reader (aggregation across blueprints):** starts inside `blueprints/dashboard/` per the
  telemetry amendment's Q2 = C, and **moves to `observability/` when a second blueprint actually
  emits usage** (the real trigger, §4 — not merely "has compute"). At that point the dashboard
  becomes a *consumer* of `observability/` rather than the owner of collection.
- **The contract spec itself (this document, once ratified):** should become a linkable, checkable
  artifact — candidate `contracts/observability.md` at repo root — referenced from every blueprint
  README, mirroring how `pipeline/stacks.yml` is the checkable registry (open #5).

---

## 6. The composition caveat — coordinate with `team-d`, do not decide alone

`composable-dashboards.md` §5.1 and §8#3 flagged that `cornell:deployment-id` is treated as a single
flat key (one deployment = one id), which the dashboard's Application Design has now baked in, and
that this may not survive Track D composition. **`team-d` exists and is doing exactly Track D**
(inter-block communication + isolation), currently at Reverse Engineering.

This means the join-key-under-composition decision is no longer a lone dashboard-branch concern:

- The contract's Part C keys emission on `cornell:deployment-id`. If Track D gives a composed
  deployment a parent id with per-block sub-ids, the emission key must carry the sub-id or telemetry
  from two composed blocks collapses into one bucket.
- Track D's **isolation** requirement (one block cannot read another's data) is the same property
  the §3 emission mechanism must honour — so the mechanism choice and the isolation model should be
  agreed *together*.

**Recommended action:** raise the id-semantics + emission-isolation decision as a joint item between
the `dashboard` and `team-d` tracks before either hardens its assumption. This is the one item with
active cost-of-delay (dashboard is in Units Generation; team-d is early enough to shape).

---

## 7. Open decisions (delta from `composable-dashboards.md` §8)

> **📌 Pointer added 2026-08-07 by the AI-DLC telemetry pass — content below unchanged.**
> The queued FR-9 pass has now run and **answers four of the items below**, so they should not be
> re-litigated: **#2 emission mechanism** → CloudWatch EMF to the blueprint's own log group,
> *ratified as recommended*. **#3 deployment-id under composition** → resolved as an `agent_id`
> dimension that defaults to `deployment_id`, so the multi-agent case is a change of values rather
> than a migration; `origin/team-d` had no composition-id decision recorded to coordinate with
> (checked at `e7edca0`, reverse-engineering artifacts only). **§4's "second emitter" trigger** →
> still not fired, and the pass deliberately declines to instrument one (decision T6). **§2 Part B
> manifest shape** → adopted essentially as drafted.
> See `aidlc-docs/inception/amendments/telemetry-fr9-2026-08-07.md` and the decision record at
> `aidlc-docs/inception/requirements/requirement-amendment-questions-telemetry-round-2.md`.
>
> **One finding in that pass materially affects §2 of this document** and is worth reading before
> building anything here: `blueprints/teams-bot` routes all generation through Cornell's LiteLLM
> gateway rather than Bedrock, so the `AWS/Bedrock` namespace in this account is **empty** for chat
> traffic and Cost Explorer shows **no model spend**. The pull-based CloudWatch source this document
> and `dashboard-sources.md` §4.1 both propose therefore reads zeros for model usage today; those
> metrics are reachable only by the push path. #7 and #8 remain genuinely open.

Resolved or narrowed by this grounding:
- **#1 contract shape** → proposed concretely in §2 (three parts) — ratify.
- **#2 emission mechanism** → recommended CloudWatch EMF in §3 — ratify or overrule.
- **#3 deployment-id under composition** → now a **joint `dashboard` × `team-d`** decision (§6), not
  solo; still the time-sensitive item.
- **#5 contract artifact location** → propose `contracts/observability.md` + a manifest-schema check
  extending `validate_stacks.py`.

Newly surfaced by the branch survey:
- **#7 Non-AWS resources (from `add-terraform-stage`).** The tag contract (Part A) is AWS-only; the
  Resource Groups Tagging API cannot see Azure/Entra resources. Decide whether non-AWS resources get
  an equivalent provider-side tag convention, a manifest `data_classification`-style declaration, or
  an explicit "not centrally inventoried" status.
- **#8 Manifest adoption is not yet universal.** `hello-world` has a `blueprint.yaml`; the KB
  blueprint on `b-knowledgeBase` does **not**. Before the manifest can carry the telemetry contract,
  decide whether a `blueprint.yaml` is *required* of every blueprint (a PR check), and backfill the
  ones missing it.
