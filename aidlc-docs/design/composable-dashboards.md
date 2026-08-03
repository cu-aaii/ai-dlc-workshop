# Design — Composable Dashboards and the Observability Contract

**Status**: Draft for review. No code implied by this document; it exists to be reviewed before
any template or blueprint work proceeds.
**Date**: 2026-08-03
**Scope**: Cross-cutting. Spans the platform (Track E), the dashboard blueprint, and the
contract every blueprint conforms to. Deliberately **not** under `inception/`, which is scoped
to the single cost & usage dashboard.
**Relationship to active AI-DLC work**: The in-progress `dashboard` blueprint
(`aidlc-docs/inception/`) is the *first implementation* of one half of what this document
describes. This document is the wider frame that work sits inside; see §7 for what it changes and
what it leaves untouched.
**Independent convergence (2026-08-03)**: While this document was being drafted, the AI-DLC
workflow — via a separate custom-telemetry amendment
(`inception/requirements/requirement-amendment-questions-telemetry.md`) — reached the same central
conclusion from the other direction: that custom telemetry is *"a cross-blueprint contract, not a
dashboard feature ... the metric equivalent of the four `cornell:*` tags — plus a reader. A
blueprint that doesn't implement the convention is invisible to it, exactly as an untagged resource
is invisible to inventory today."* That is this document's two-layer contract (§2) arrived at
independently. This draft has been reconciled to that committed decision; where they differed, the
committed AI-DLC decision governs (see §2.2 and §4.1).

---

## 1. Problem and vocabulary

Cornell units build tools ad hoc, in different places, with inconsistent governance, and the
central team finds out late. Blueprints replace that with one sanctioned path that is *faster*
than going it alone. For that path to also give the central team visibility, every deployment has
to be observable in a uniform way — which is only possible if "observable" means the same thing
for a chatbot, a document pipeline, and a dashboard.

This document uses the platform's own vocabulary, because two of these terms are routinely
conflated and the conflation produces bad architecture:

| Term | Definition (as used on this platform) |
|---|---|
| **Blueprint** | A pre-approved, reusable *pattern for a category* of software (Teams chatbot, document pipeline, event-driven automation, SSO-protected dashboard). It is the vetted design + baked-in guardrails, not the running code. |
| **Template** | The concrete GitHub *repository* that implements a blueprint. The Cornell Builder stamps a new repo *from* a template when a builder picks a blueprint. |
| **Builder** | The person making the request — explicitly "not an engineer" (e.g. an instructor). Never touches AWS or, ideally, GitHub. |
| **Component / block** | An independently developed, independently maintained unit that a *future* deployment composes with others through a defined protocol (Track D). The workshop still ships each blueprint as one bundled thing; composition is the roadmap step after. |
| **Contract** | The standard *interface* a blueprint conforms to so the platform can treat all deployments uniformly. This document is mostly about one contract: **observability**. |

### 1.1 There are two dashboards, and they are not the same thing

The single most important distinction in this document. "The dashboard" has meant two different
artifacts in prior conversations, and they sit at opposite ends of the architecture:

| | **Central observability dashboard** | **Dashboard blueprint** |
|---|---|---|
| Also called | Track E; "the cost and usage dashboard" | "SSO-protected dashboard" category |
| Who owns it | The platform / AI Platform team | A campus unit (the builder who requested it) |
| Who requests it | Nobody — it is platform infrastructure | A builder, via the Cornell Builder |
| How many exist | **One**, for the whole org | **Many** — one per unit that wants one |
| What it shows | *All* deployments: owner, health, cost | Whatever that unit's data is |
| Relationship to the contract | **Consumes** it, across every deployment | **Emits** it (like every blueprint) *and*, as its function, **consumes** some view of it |
| Current status | The active AI-DLC `dashboard` work is its v1 | Not started; a peer to the chatbot blueprint |

The interesting design is not either dashboard in isolation. It is the **contract** that lets the
dashboard blueprint be a fully self-contained block a unit owns, while *also* being visible in the
one central view — without the central view knowing anything blueprint-specific, and without the
blueprint knowing anything central-specific. Get the contract right and both dashboards, plus
every other blueprint, fall out of it. Hardcode the cost dashboard to the platform's internals and
neither composition nor a second dashboard is possible without a rewrite.

---

## 2. The observability contract (the load-bearing idea)

Every blueprint — chatbot, doc-pipeline, dashboard, automation — conforms to one contract so the
platform can treat them uniformly. The contract has **two layers**, and only the first exists
today.

### 2.1 Layer 1 — the tag contract (exists)

Already enforced repo-wide (`CLAUDE.md`, `blueprints/README.md`): every resource carries all four
`cornell:*` tags.

| Tag | Meaning | Source |
|---|---|---|
| `cornell:owner` | Who owns this deployment | Stack parameter |
| `cornell:blueprint` | Which blueprint pattern produced it | Hardcoded in the template |
| `cornell:blueprint-version` | Version of that blueprint | Template default, bumped per PR |
| `cornell:deployment-id` | The unique deployment instance; the **join key** across everything | Stack parameter / derived |

This layer answers **"what exists and who owns it"** and is discoverable with zero cooperation
from the blueprint's own code — the Resource Groups Tagging API reads it from the outside. It is
the foundation the current cost & usage dashboard is built on, and it is genuinely enough for an
*inventory* view. It is **not** enough for health or cost or anything blueprint-specific.

### 2.2 Layer 2 — the telemetry contract (new; the composable part)

To show **blueprint-specific behaviour** — how much a deployed application is actually used — in one
central view, tags are not enough: tags describe existence, not behaviour. Layer 2 is a standard
*emission* format every blueprint produces at runtime. It is not yet built, but it is now
**specified and sequenced**: the telemetry amendment (Q3 = B) routes it to a second Requirements →
Stories pass after the v1 inventory dashboard is approved. This section is the cross-blueprint frame
that second pass writes its FR-9 inside.

The design principle: **the central view consumes a standard shape; the blueprint decides what
goes in it.** A blueprint emits telemetry keyed by `cornell:deployment-id`; the central dashboard
aggregates by that key without knowing what any particular blueprint *does*.

**The Layer-2 minimum is business *usage*, not health.** This is the point the telemetry amendment
settled and where an earlier draft of this document was wrong. Operational health telemetry
(latency, error rate, throughput, invocation counts, alarms, structured logs, access logs) is
**already specified** for the dashboard's own components — US-11..US-14 cover it under SECURITY-03/04
and RESILIENCY-05/06/07/09. So health is not what "custom telemetry" adds. Driven by the amendment's
Q4 answer — *"usage metrics to justify cost; feedback for business processes; metrics to determine
value / how useful the system is"* — the contract's new layer is **business-level usage counters**:
how much a deployed application is actually used.

Contract shape (to be ratified in review — see §8):

- **Usage counters (the core of Layer 2)** — business-level counts a deployed application emits
  about its own use: chatbot queries asked, documents indexed, sessions started, dashboard API hits.
  Namespaced and keyed by `cornell:deployment-id` (candidate mechanism: CloudWatch EMF or a
  `cornell:deployment-id`-scoped metric namespace). The central view renders them generically
  ("this deployment reports N of metric X") without special-casing any blueprint. These answer the
  *value* and *usefulness* questions in Q4 and need only the usage side — they are **not** gated on
  anything deferred.
- **Cost (derived, not emitted)** — cost is derivable centrally from the tag contract (Layer 1) via
  Cost Explorer / CUR keyed on `cornell:deployment-id`, so a blueprint does **not** self-report cost.
  This is why the join key matters. But **usage-per-dollar is gated on FR-8**: joining usage counters
  to spend needs the deliberately-deferred cost-data-source decision (Cost Explorer vs. CUR) made
  first. Usage counters alone ship without it; the *"justify cost"* purpose in Q4 waits on FR-8.
- **Health (already covered, noted for completeness)** — a standard health/heartbeat record per
  deployment *would* be a natural Layer-2 addition for the org-wide view, but for the dashboard
  blueprint itself it is already specified as operational telemetry (above). If the central view
  later wants uniform health across *all* blueprint types, that is a contract extension to raise
  then — not part of the usage-telemetry pass.

**Emission mechanism** is a decision, not a given (see §8): CloudWatch (metrics + EMF + a
platform-owned log destination) is the low-friction, serverless-first option that fits this repo's
constraints; an EventBridge bus or a metrics endpoint are alternatives with different coupling.
The mechanism must not require a blueprint to know the central account's internals, and must not
let one deployment read another's data.

### 2.3 Why two layers, not one

Layer 1 is **pull-based and cooperation-free** — the platform reads tags from outside the
deployment, so even a badly behaved or half-built blueprint still shows up as inventory (surfacing
that gap is itself a feature). Layer 2 is **push-based and cooperative** — richer, but only as good
as the blueprint's emission. Keeping them separate means the central view degrades gracefully: a
deployment that emits no telemetry is still *inventoried and cost-attributed*, just without usage
counters. This is exactly the property the telemetry amendment named — *"a blueprint that doesn't
implement the convention is invisible to it, exactly as an untagged resource is invisible to
inventory today"* — and it is the composable equivalent of the current spec's "fail-closed / show
staleness" requirement, lifted to the platform level.

---

## 3. The two dashboards, expressed against the contract

```
   ┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌───────────────────┐
   │  chatbot    │   │ doc-pipeline │   │  automation   │   │ dashboard blueprint│
   │ blueprint   │   │  blueprint   │   │  blueprint    │   │  (a unit's own)    │
   └──────┬──────┘   └──────┬───────┘   └──────┬────────┘   └─────────┬─────────┘
          │  emit contract  │                  │                      │  emits contract
          │  (tags + telem) │                  │                      │  like any blueprint
          └────────┬────────┴─────────┬────────┴──────────┬───────────┘
                    │                  │                   │
                    ▼                  ▼                   ▼
          ┌───────────────────────────────────────────────────────┐
          │  CENTRAL OBSERVABILITY DASHBOARD  (Track E, platform)   │
          │  consumes the contract across ALL deployments:          │
          │  owner · health · cost · inventory, keyed by            │
          │  cornell:deployment-id                                  │
          └───────────────────────────────────────────────────────┘

   The dashboard blueprint is special ONLY in that its *function* is also to
   consume a view of the contract — but a unit-scoped one (that unit's own
   deployments / data), not the org-wide central one. Same contract, narrower scope.
```

- The **central dashboard** is a *pure consumer* of the contract, at org scope. It special-cases
  no blueprint. Adding a new blueprint type requires **zero** central-dashboard changes, because
  the new blueprint conforms to the same contract. This is the test of whether the contract is
  right: *a new blueprint category must light up centrally with no central edit.*
- The **dashboard blueprint** is, from the platform's side, just another emitter. Its *own* purpose
  happens to be consuming the contract too — but scoped to one unit (a per-tenant view, which the
  workshop notes as "paper architecture" for now). The same contract serves both scopes; only the
  filter on `cornell:owner` / `cornell:deployment-id` differs.

The payoff of stating it this way: **per-tenant view = central view + an owner filter.** They are
not two systems. If the contract is right, the "paper architecture" per-tenant view is a scoping
parameter on the thing already being built, not a separate build.

---

## 4. Where the current AI-DLC cost & usage dashboard fits

The active `dashboard` blueprint (`aidlc-docs/inception/requirements/requirements.md`, approved
2026-08-03) is **the v1 of the central observability dashboard** — the Layer-1 (tag inventory)
consumer. That framing is correct and this document does not overturn it. Concretely, of what that
spec already commits to:

**Keep as-is — it is the central consumer's v1:**
- Collector → Resource Groups Tagging API → snapshot store → read API → static UI. This *is* the
  Layer-1 consumption path.
- Grouping by `cornell:deployment-id` / `owner` / `blueprint`. This is exactly the contract's join
  key doing its job.
- Surfacing resources *missing* required tags. This is the Layer-1 contract's conformance check —
  it belongs at the platform level and the current spec already has it.
- The WAF IP-allowlist access model, fail-closed behaviour, snapshot staleness display, PBT suite,
  and the documented exceptions. All sound; all survive the reframing.

**What the composable frame *adds* (and where):**
- **Usage telemetry (Layer 2)** is *already committed and sequenced*, not a gap this document opens.
  The telemetry amendment queued it as a second Requirements → Stories pass (Q3 = B), scoped it to
  business usage counters (Q1 = A), placed it inside `blueprints/dashboard/` with `observability/` as
  the eventual home triggered when a second blueprint emits (Q2 = C), and — critically — already
  identified it as *"a cross-blueprint contract, not a dashboard feature."* This document's §2.2 is
  the frame that pass writes FR-9 inside; the two agree by construction.
- **Cost (FR-8, currently deferred)** is re-cast as a *contract-level* capability (§2.2), derivable
  centrally from Layer-1 tags via Cost Explorer/CUR on `cornell:deployment-id`. It stays deferred,
  and the amendment sharpened *why*: usage counters ship without it, but **usage-per-dollar** is
  gated on the FR-8 data-source decision. Its home is the contract, not any one blueprint.
- **Operational health** is **not** what the composable frame adds here — the current spec already
  covers it (US-11..US-14). Naming it as the Layer-2 minimum was an error in this document's first
  draft, corrected in §2.2.

### 4.1 The one place this document and the committed decisions must be kept in step

The telemetry amendment lives in the AI-DLC audit trail and is the *governing* record; this document
is the wider frame. They currently agree. The place to watch is the **second Requirements pass**:
when FR-9 is written, it should cite this document's contract (§2.2) as its cross-blueprint frame,
and this document's §8 open decisions (emission mechanism, id-under-composition, artifact location)
should be resolved *at or before* that pass rather than rediscovered inside it. If FR-9 diverges
from §2.2, FR-9 wins and this document is updated — not the reverse.

**One naming caution:** the current spec's blueprint is literally named `dashboard`. If both the
central view and a builder-facing dashboard blueprint eventually exist, that name is ambiguous.
Consider `observability` (or `platform-observability`) for the central one, reserving `dashboard`
for the builder-facing category. This is a rename decision, flagged in §8, not made here.

---

## 5. Composition — the Track D horizon (future, not workshop scope)

The roadmap step after bundled blueprints is **true composition**: a deployment that assembles two
or three independently maintained blueprints that plug together through a defined protocol (Track
D handles how blocks communicate and stay isolated). This document does not design that protocol,
but the observability contract has to *not preclude* it. Two requirements fall out:

1. **The join key must be composition-stable.** When a dashboard block and a chatbot block are
   assembled into one deployment, telemetry from both must remain attributable. `cornell:deployment-id`
   as the single join key works only if a composed deployment has a coherent id story — e.g. a
   parent deployment id with per-block sub-ids, or each block keeping its own id and the composition
   recording the relationship.
   **Status as of 2026-08-03 (Application Design approved, `291ad4e`):** the *forward-compatibility*
   half of this is now handled — component C-02 carries a `schema_version` and sibling-key headroom
   specifically so the queued telemetry amendment "lands as an addition rather than a migration"
   (`application-design.md` §8). But the design treats `cornell:deployment-id` as a **single flat
   key** throughout (collector, snapshot schema, aggregation, read API), which is correct for v1 and
   for the telemetry pass — both operate on individual deployments — and silently assumes **one
   deployment = one id**. The *composition-semantics* half (flat vs. parent+sub-id vs. related-ids)
   remains **undecided and is now entering Units Generation**. This is not a defect — composition is
   correctly out of workshop scope — but the cheap-now window is closing as the flat-id assumption
   propagates downstream. See §8, decision #3, narrowed accordingly.
2. **Isolation must be contract-compatible.** Track D's isolation guarantee (one block cannot read
   another's data) must hold for telemetry too — a block emits its own signal and cannot read a
   peer's, even though both feed the same central view. The Layer-2 emission mechanism (§2.2) has to
   support write-own / no-read-peer, which rules out some shared-bus designs and favours per-deployment
   scoped destinations.

Marking these now is the point: the workshop builds bundled blueprints, but the *contract* is where
composition will either be possible or blocked, so the contract is where to be careful.

---

## 6. How this lands — repo layout and the template-repo model

Two different homes, because this platform has two: *this* mono-repo (where blueprints are authored
and the pipeline lives) and the *stamped template repos* the Cornell Builder creates per builder.

### 6.1 In this repo (authoring + central platform)

- **The contract definition is an artifact, not folklore.** A single reviewed document (schemas +
  the tag/telemetry spec) that blueprints conform to and the central dashboard consumes. Candidate
  location: `contracts/observability.md` (+ a machine-readable schema alongside it) at repo root, or
  `docs/contracts/`. It must be *linkable* from every blueprint README so conformance is checkable.
- **The central dashboard** stays a blueprint under `blueprints/` (it deploys through the same
  pipeline as everything else — no special path), likely renamed per §4. It is the reference
  *consumer* of the contract.
- **Shared emission helpers**, if Layer-2 lands, are where blueprints get the contract "for free"
  rather than each re-implementing it — the composable-primitive idea, but scoped to telemetry, not
  a speculative grab-bag. Defer building these until a *second* emitter exists to justify the
  abstraction (YAGNI); design the contract now, extract the helper when the second consumer appears.

### 6.2 In a stamped template repo (what a builder gets)

A template repo for any blueprint ships **conformance to the contract already wired in**, so the
builder (and the AI harness customizing it) cannot accidentally produce an unobservable deployment:
the `cornell:*` tags are already on the scaffolded resources, and — once Layer 2 exists — the
telemetry emission is already in the scaffold. The builder customizes *what the thing does*; the
observability is not theirs to get wrong. This is the governance model applied to observability:
the guardrail is baked into the blueprint, enforced by the pipeline, not left to the builder.

The dashboard blueprint's template repo additionally carries the *consumer* side (the per-tenant
view), scoped by an owner parameter — which, per §3, is the central view with a filter.

---

## 7. Impact on the active AI-DLC work

The in-flight `dashboard` blueprint has advanced past where an earlier draft of this section placed
it. As of 2026-08-03 it is at **INCEPTION → Application Design** (plan + questions issued, awaiting
answers): Requirements approved, User Stories approved (Q9/Q10 resolved), Workflow Planning complete.
The custom-telemetry amendment is answered and **queued as a non-blocking second pass** (Q3 = B), so
v1 is no longer held on it. This design document does **not** require reopening the approved
requirements, because:

- Everything the current v1 builds is the **Layer-1 central consumer**, which this frame keeps intact
  (§4). No requirement is contradicted.
- The composable additions (Layer-2 usage telemetry, cost-as-contract, the id-composition question)
  are the **already-sequenced second pass**, appropriately *later* than a v1 inventory dashboard.

Recommended sequencing (aligned with the committed AI-DLC state, not competing with it):
1. **Let v1 finish as the Layer-1 central consumer.** Application Design → Construction, as already
   planned. Independent of this document.
2. **Ratify the contract (§2, §8) at or before the second Requirements pass**, so FR-9 is written
   *inside* a decided contract rather than inventing one. Bounded to the contract; not a speculative
   framework.
3. **Extract shared emission helpers only when a second emitter exists** — which is also the
   amendment's own trigger for moving telemetry from `blueprints/dashboard/` to `observability/`
   (Q2 = C). The two triggers coincide, which is a good sign the seam is in the right place.

The single cheap-now / expensive-later decision that should *not* wait is the **`cornell:deployment-id`
semantics under composition** (§5.1) — it may influence how v1 treats the id as a join key, and v1 is
now in Application Design where the join-key shape gets fixed. Flagged in §8, decision #3.

---

## 8. Open decisions (for review — not resolved here)

Per methodology, these are surfaced rather than decided unilaterally:

1. **Contract ratification.** Is the two-layer contract (§2) the right shape? Specifically: is
   central cost-derivation-from-tags (no per-blueprint cost emission) accepted, and is a standard
   health record the right Layer-2 minimum?
2. **Emission mechanism (§2.2).** CloudWatch (EMF/metrics + platform log destination) vs.
   EventBridge bus vs. metrics endpoint. Constraints: serverless-first, `us-east-1`, no cross-deployment
   read, no blueprint knowing central internals.
3. **`cornell:deployment-id` under composition (§5.1) — NARROWED, and time-sensitive.** The
   schema-forward-compatibility half is *resolved* (C-02 `schema_version` + sibling-key headroom,
   Application Design `291ad4e`). What remains open is only the **composition id semantics**: flat id
   vs. parent+sub-id vs. per-block-id-with-relationship. Application Design bakes in **one deployment =
   one flat id**, which is right for v1 but propagates into Units Generation now. Either (a) confirm
   flat-id is acceptable and accept a later migration if Track D ever needs composed attribution, or
   (b) decide the composed-id shape before it hardens further. This is the one item on this list that
   is actively getting more expensive with each downstream stage.
4. **Naming (§4).** Rename the current `dashboard` blueprint to `observability` /
   `platform-observability`, reserving `dashboard` for the builder-facing category? Or keep `dashboard`
   and name the builder-facing one differently?
5. **Contract artifact location & format (§6.1).** `contracts/` at repo root vs. `docs/contracts/`;
   prose + JSON Schema vs. prose only. Whatever the choice, it must be linkable from every blueprint
   README and checkable (echoing how `pipeline/stacks.yml` makes registration checkable).
6. **Per-tenant view timing (§3).** The workshop calls it "paper architecture." Confirm it stays
   paper for now, given §3 shows it is central-view-plus-a-filter and therefore cheap once the central
   view exists.
