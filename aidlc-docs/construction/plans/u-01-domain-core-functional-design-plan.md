# Functional Design Plan — U-01 Domain Core

**Phase**: CONSTRUCTION → Functional Design (first unit, per Q5 = A depth-first)
**Date**: 2026-08-03
**Unit**: U-01 Domain Core — C-04 Inventory Model, C-05 Aggregation Core
**Stories owned**: US-03, US-04, US-05, US-10
**Inputs**: `inception/application-design/unit-of-work.md`, `unit-of-work-story-map.md`,
`components.md`, `component-methods.md` · amendments A1/A2

---

## Why this unit's Functional Design is unusually load-bearing

U-01 is pure logic with no infrastructure, so "technology-agnostic business rules" is not an
abstraction exercise here — it is the entire unit. Two consequences:

1. **PBT-01 requires properties to be identified at this stage.** Six are already named in
   `component-methods.md`. This stage either confirms them and adds what the answers below imply, or
   ten blocking rules have no concrete subject.
2. **Every question below is a decision about behaviour a user will see.** None is a coding detail.
   "Is an empty tag value a missing tag?" decides whether US-04 flags a resource. There is no
   infrastructure layer downstream that can correct a wrong answer here.

`requirements.md` deliberately deferred "tag-gap edge cases and the exact staleness threshold" to this
stage. Q2, Q3 and Q5 are that deferral coming due.

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

---

### Question 1 — One malformed resource: fail the snapshot, or skip and report?

`component-methods.md` says `normalize_resource` "raises on a malformed item rather than emitting a
partial record," and US-02 requires complete-or-fail collection. Together those imply **one** bad ARN
among 300 resources aborts the entire snapshot. That may not be what you want, and it was never
explicitly decided.

"Malformed" means genuinely unparseable — an ARN with too few segments, a missing ARN field, a tag
structure that is not key/value. Not "missing a `cornell:*` tag," which is normal and is US-04's whole
subject.

**A) Skip the item, count it, and surface the count** ← *recommended*
   The snapshot records `skipped_count` and the reasons. The API exposes it; the UI shows it. A
   snapshot with 299 of 300 resources plus "1 resource could not be read" is more useful than no
   snapshot, **and it is still honest** — the omission is visible, which is the property US-02 actually
   cares about.
   *Cost*: `Snapshot` gains a field, and "complete" now means "complete or explicitly accounted for."
   That is a real weakening of FR-1.1's wording, and it should be recorded as such rather than glossed.

**B) Fail the whole snapshot** — strictest reading of FR-1.1 and US-02.
   *Cost*: one unparseable resource anywhere in the account blanks the dashboard until someone fixes
   it, and the person who can fix it may not be the person locked out of seeing it. In a shared
   workshop account, one team's odd resource takes out everyone's view.

**C) Skip silently** — log it, nothing user-visible.
   *Cost*: rejected in advance. This is the under-reporting-while-looking-successful failure the whole
   design is built to avoid.

X) Other

[Answer]:A

---

### Question 2 — Is a tag present but empty a missing tag?

`cornell:owner=""` is legal in AWS. It is present as a key and carries no information.

**A) Empty or whitespace-only counts as MISSING** ← *recommended*
   `classify_tag_gaps` flags it; `group_by_tag` puts it in the "missing this tag" group.
   *Why*: the point of US-04 is finding resources you cannot attribute to anyone. A resource with
   `cornell:owner=""` is exactly as unattributable as one with no owner tag, and reporting it as
   compliant makes the tag-gap view lie in the one way that matters.

**B) Present-but-empty counts as PRESENT** — the tag exists; policy compliance is about the key.
   *Cost*: creates a trivially available way to pass the tag-gap check while conveying nothing.

**C) A third state** — "present but empty," reported separately from both.
   *Why*: most precise; distinguishes carelessness from omission.
   *Cost*: three states propagate into the API, the UI, and every grouping. More surface for a
   marginal case that may not exist in practice.

X) Other

[Answer]:A

---

### Question 3 — Are tag keys matched case-sensitively?

AWS tag keys **are** case-sensitive, so `Cornell:Owner` and `cornell:owner` are genuinely different
keys on the resource. `CLAUDE.md` specifies the lowercase form.

**A) Case-sensitive match; a wrong-case key is a missing tag** ← *recommended*
   *Why*: it matches what AWS actually stores, and it matches what the cost/inventory tooling this
   feeds will do. A resource tagged `Cornell:Owner` is genuinely invisible to a case-sensitive
   consumer, so reporting it as tagged would be reporting something false.
   *Cost*: a plausible typo produces a gap report the author may find surprising.

**B) Case-insensitive match** — treat `Cornell:Owner` as satisfying `cornell:owner`.
   *Cost*: the dashboard would report a resource as correctly tagged when the tooling the convention
   exists for cannot see it. Kinder, and wrong.

**C) Case-sensitive, but flag near-misses distinctly** — a gap, with "did you mean `cornell:owner`?"
   *Why*: correct *and* actionable, which is arguably what a tag-gap view is for.
   *Cost*: a near-miss rule to define and test.

X) Other

[Answer]:A

---

### Question 4 — Can the same ARN appear twice, and what if it does?

The Tagging API paginates; a resource created or modified mid-collection could in principle surface on
two pages. Every count in US-02 and US-03 depends on the answer, and so does the PBT invariant that
group sizes sum to the total.

**A) Deduplicate by ARN, last occurrence wins, count the collisions** ← *recommended*
   *Why*: an ARN uniquely identifies a resource, so two records for one ARN are one resource, and
   counting it twice inflates every view. Recording the collision count keeps it from being invisible.
   *Cost*: "last wins" is arbitrary between two differing tag sets, though they should not differ.

**B) Treat a duplicate ARN as malformed** and route it through Q1's answer.
**C) Preserve duplicates** — the snapshot mirrors exactly what the API returned.
   *Cost*: resource counts become wrong in a way no one can explain from the UI.

X) Other

[Answer]:A

---

### Question 5 — What is the staleness threshold?

Explicitly deferred here by `requirements.md`. `evaluate_freshness(collected_at, now, stale_after)`
takes it as an argument, so this decides the *default* the stack parameter carries.

The refresh interval is itself a stack parameter (FR-2.3), so the threshold should be expressed in
terms of it rather than as a bare duration — otherwise changing the interval silently breaks the
staleness judgement.

**A) `3 × refresh_interval`** ← *recommended*
   *Why*: tolerates one missed run plus scheduling jitter without crying stale, and catches a genuinely
   dead collector within three intervals. Expressed as a multiple, so it stays correct when the
   interval changes.
   *Cost*: with a long interval, staleness is noticed late.

**B) `2 × refresh_interval`** — tighter; one missed run shows as stale.
**C) A fixed duration** (e.g. 24h) independent of the interval.
   *Cost*: decouples the two, so a interval change quietly invalidates it.
**D) You choose** — I pick and record the reasoning. (That lands on A.)

X) Other

[Answer]:A

---

### Question 6 — What if `collected_at` is in the future?

Clock skew, or a snapshot written by a misconfigured environment. `evaluate_freshness` receives both
timestamps and must return something.

**A) Treat a future `collected_at` as an error state, distinct from fresh and stale** ← *recommended*
   *Why*: it cannot legitimately happen, so reporting "fresh" hides a real fault — and "fresh" is the
   most dangerous thing to report about data whose provenance is broken. US-06 already has an
   unavailable/error path for this to surface through.
   *Cost*: a third `Freshness` value, and a UI state to render.

**B) Clamp to fresh** — treat future as age zero. Simplest; hides the fault.
**C) Small tolerance, then error** — allow a minute of skew, error beyond it.
   *Cost*: another constant to justify.

X) Other

[Answer]:A

---

### Question 7 — What is `region` for a global resource?

`arn:aws:iam::123456789012:role/x` and CloudFront ARNs have an **empty** region segment. `ResourceRecord`
declares `region: str`.

**A) The literal string `"global"`** ← *recommended*
   *Why*: it is what the console and AWS's own docs call these, so it will not surprise anyone reading
   the dashboard, and it keeps `region` a plain non-empty string — no `None` handling in grouping or
   display.
   *Cost*: a synthesized value that is not literally in the ARN.

**B) Empty string** — faithful to the ARN. *Cost*: renders as a blank cell, which reads as a bug.
**C) `None`** — honest about absence. *Cost*: optionality propagates through grouping and the UI.

X) Other

[Answer]:A

---

### Question 8 — How are groups ordered, and where does the "missing" group go?

`serialize_snapshot` must be deterministic (a named PBT property), and the UI should not reshuffle
between reads. `GroupingResult.groups` therefore needs a defined order.

**A) By member count descending, then by value ascending; "missing" group always last** ← *recommended*
   *Why*: the biggest groups are what a viewer scans for, the value tiebreak makes it fully
   deterministic, and pinning "missing" last stops it jumping position as counts change. Deterministic
   without being alphabetical-and-useless.
   *Cost*: the group a viewer most needs to act on (missing tags) is furthest down. US-04's dedicated
   tag-gap view is the mitigation — this is the inventory grouping, not the gap report.

**B) By value ascending; "missing" last** — simplest, most predictable, least informative.
**C) By count descending; "missing" first** — puts the actionable group up front.
   *Cost*: an empty "missing" group would head the list on a fully compliant account, which reads oddly.

X) Other

[Answer]:A

---

### Question 9 — What makes a stored `schema_version` acceptable to read?

`deserialize_snapshot` "rejects unknown `schema_version` explicitly." FR-2.4 requires the schema to be
extensible, and the queued telemetry amendment will add a sibling top-level key — so this rule decides
whether that future addition is readable by today's code or a breaking change.

**A) Same major version, ignore unknown top-level keys** ← *recommended*
   `1.x` readable by a `1.*` reader; unrecognized keys preserved-or-ignored, not fatal.
   *Why*: this is precisely what makes FR-2.4 and the telemetry amendment additive rather than a
   migration. A reader that rejects unknown keys turns "add a `metrics` key" into a coordinated
   deploy.
   *Cost*: a typo'd key name is silently ignored rather than caught.

**B) Exact version match only** — safest, most brittle. A version bump breaks reads until both sides
   deploy, and the collector and API deploy in the same stack anyway.
**C) Accept anything, best-effort parse** — rejected: this is the "corrupt object read as valid data"
   path US-06 exists to distinguish.

X) Other

[Answer]:A

---

## Part A1 — Categories evaluated and deliberately not asked about

- **Frontend components** — **not applicable to U-01.** C-06 Web UI is U-02's. No
  `frontend-components.md` will be generated for this unit; it belongs to U-02's Functional Design.
  Recorded so its absence is not read as an omission of a mandated artifact.
- **Integration points** — U-01 has none. Its dependency matrix row is empty; it is called in-process
  and calls nothing. Asking about API contracts or data exchange would invent a boundary the approved
  design does not have.
- **Persistence** — U-01 persists nothing. `serialize_snapshot` returns bytes; who writes them is
  U-02's business.
- **Which four tags are required** — already settled by `CLAUDE.md` and FR-1.4. Not reopened.
- **The PBT library and example counts** — a Code Generation concern. PBT-01 requires the *properties*
  here, and those are named below, not the harness that runs them.
- **Business workflows / processes** — U-01 has no workflow. It is a set of total functions over one
  input. The workflow lives in U-02's two services, already designed.

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] Confirm all nine `[Answer]:` tags are filled
- [x] Run the mandatory Step 5 analysis — vagueness, undefined terms, contradiction, missing detail,
      option-merging — and raise a clarification file rather than proceeding if any is found
- [x] Record resolved decisions and answer interactions in a `Part A2` section

### B2. `domain-entities.md`
- [x] `ResourceRecord`, `Snapshot`, `Group`, `GroupingResult`, `TagGapReport`, `Freshness`
- [x] Field-level definitions with the Q2/Q3/Q7 rules applied
- [x] Identity, equality, and immutability semantics — equality is load-bearing, since three PBT
      properties are equality assertions
- [x] Any field the answers add (Q1 `skipped_count`, Q4 collision count)
- [x] Explicitly technology-agnostic: no AWS types, no serialization format in the entity definitions

### B3. `business-rules.md`
- [x] Normalization rules, including the Q1 malformed-item rule and the Q7 region rule
- [x] Tag-presence rules (Q2 empty, Q3 case) as the single source of truth both grouping and gap
      classification consult — stated once, not twice, so they cannot drift apart
- [x] Deduplication rule (Q4)
- [x] Gap classification rule
- [x] Freshness rule including the Q5 threshold and the Q6 future-timestamp state
- [x] Ordering and determinism rules (Q8)
- [x] Schema compatibility rule (Q9)
- [x] For each rule: which story or requirement it serves, so none is orphaned

### B4. `business-logic-model.md`
- [x] Algorithms for `normalize_resource`, `build_snapshot`, `group_by_tag`, `classify_tag_gaps`,
      `evaluate_freshness`, and the serialization pair
- [x] Totality per function — which raise, which cannot
- [x] The `_reference_group_by_tag` oracle's definition, since the oracle property is only as good as
      the reference being independently written
- [x] Confirm and extend the PBT property set (PBT-01) — the six already named plus any the answers
      imply, each mapped to the rule it verifies

### B5. Validation and honest reporting
- [x] Every rule traces to a story or requirement; every US-03/04/05/10 acceptance criterion has a rule
- [x] No rule requires AWS, a clock read, an environment read, or I/O
- [x] Confirm the `core/` boundary stays grep-able: no `boto3`, no `os`, no `datetime.now()`
- [x] Report anything that cannot be settled here with the stage that carries it

### B6. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 🔧 Functional Design Complete - U-01 Domain Core` and wait for explicit approval

---

## Part A2 — Resolved decisions (Q1–Q9)

Step 5 analysis. All nine tags filled, all **A**, all clean single selections — no vagueness in the
*answers*, no contradiction between them, no option-merging. One ambiguity was found, and it is in **my
Q9 option text**, not in the answer (Interaction 5).

| # | Decision | Answer |
|---|---|---|
| Q1 | Malformed resource | Skip, count, surface the count |
| Q2 | Empty tag value | Counts as **missing** |
| Q3 | Tag key case | **Case-sensitive**; wrong case is missing |
| Q4 | Duplicate ARN | Deduplicate, last wins, count collisions |
| Q5 | Staleness threshold | **3 × refresh_interval** |
| Q6 | Future `collected_at` | A distinct **error** state |
| Q7 | Region of a global resource | The literal string `"global"` |
| Q8 | Group ordering | Count desc, then value asc; **missing group last** |
| Q9 | Schema compatibility | Same major version; unknown top-level keys not fatal |

### Interaction 1 — I was wrong that Q1 weakens the approved requirements. It does not.

My Q1 text said option A is "a real weakening of FR-1.1's wording [that] should be recorded as such."
I then checked the approved text rather than trusting my own summary of it, and the claim does not
survive.

FR-1.1 says the system "MUST collect an inventory … using the Resource Groups Tagging API." It says
nothing about totality. The completeness language lives in **US-02**, and US-02 was written in terms of
*silence*, not absolutes:

> "the list is complete across all pages and **no resource is silently omitted**"
> "an incomplete inventory is **never presented as complete**"

Q1 = A satisfies both **exactly**. A skipped malformed resource is omitted, but it is counted and
surfaced, so it is not silent; and an inventory reported as "299 resources, 1 unreadable" is not being
presented as complete. §4.4's "under-reporting while looking successful is worse than failing" is
likewise about *looking successful*, which Q1 = A specifically avoids.

**So no approved artifact needs annotating, and no amendment is warranted.** The approved criteria were
already phrased in the right terms; my question text overstated the conflict. Recording the correction
because a fabricated amendment is as much a defect in the record as a missing one.

### Interaction 2 — Q1 = A and Q4 = A together imply a NEW property (P8)

Both answers introduce accounting fields, and together they break a naive reading of the existing sum
invariant. After Q1 and Q4 there are **four** distinct counts, not one:

1. items the upstream API returned
2. items skipped as malformed (Q1)
3. items removed as duplicate ARNs (Q4)
4. records in the snapshot

The existing invariant — group sizes sum to `len(snapshot.resources)` — still holds, and is now clearly
about **(4)**. But (4) is no longer the number the API returned, and nothing yet asserts the relationship.
So a new property falls out:

> **P8 — Accounting identity**: `raw_returned == len(resources) + skipped_count + duplicates_removed`

This is the property that makes Q1 = A honest rather than merely defensible: it is mechanically
impossible for a resource to vanish without landing in one of the three buckets. Neither answer implies
it alone; the pair does.

### Interaction 3 — Q2 = A and Q3 = A collapse into ONE predicate, and imply P9

Both answer the same underlying question — "does this resource have required tag *K*?" Q2 says empty
counts as absent; Q3 says wrong-case counts as absent. There is therefore exactly one predicate,
`has_required_tag(record, key)`, and **both** `group_by_tag` and `classify_tag_gaps` must consult it.

If each implements its own version, they drift, and the dashboard contradicts itself: a resource sitting
in the "missing owner" group while the tag-gap view calls it compliant. That yields:

> **P9 — Grouping and classification agree**: a record is in the `value=None` group for key *K* **iff**
> `classify_tag_gaps` reports *K* missing for that record.

A cross-function consistency property, which is the kind that catches exactly this drift.

### Interaction 4 — Q6 = A adds a sixth row to a table in an approved artifact (cross-unit obligation)

`Freshness` becomes three-valued: `FRESH | STALE | INVALID`. `component-methods.md`'s degraded-state
table has five rows and no place for "snapshot present, timestamp in the future."

That table belongs to C-03, which is **U-02's**. So this is a **cross-unit obligation flowing out of
U-01's Functional Design**, and it is the kind of thing that gets lost between two units' passes.
Recorded explicitly here and it will be carried into `business-rules.md`:

| Situation | HTTP | body `status` | UI |
|---|---|---|---|
| Snapshot present, `collected_at` in the future | **503** | `error` | generic failure — the data's provenance is broken, so it must not be presented as data |

503 rather than 200 because this is a fault, not a state of the world. Flagged for U-02's Functional
Design so it is not discovered at Code Generation.

### Interaction 5 — an ambiguity in MY Q9 text, resolved here rather than re-asked

Q9 option A said unknown top-level keys are "**preserved-or-ignored**, not fatal." Those are two
different behaviours and I should not have written them as one. They differ precisely where the
round-trip property lives:

- **Preserve** — round-trip holds for *any* readable snapshot, but `Snapshot` needs a passthrough field
- **Ignore** — round-trip holds only for snapshots written by the same major version; an unknown key is
  lost on a read-then-write

**Resolved: ignore.** The reasoning is decisive and comes from an already-approved design property
rather than from preference — **there is no read-modify-write path anywhere in this system.** C-01 does
a single `PutObject` of a freshly constructed snapshot and never reads the existing object; C-03 only
ever reads. So no code path can read a snapshot containing an unknown key and write it back, which means
key loss is **unobservable by construction**. Adding a passthrough field would carry real complexity to
protect against a sequence the architecture forbids.

Consequence for P1, stated rather than hidden: **round-trip is scoped to snapshots produced by the same
major schema version.** That is the honest statement of the property, not a weaker one smuggled in.

If you would rather preserve unknown keys, say so — it is a small change now and an awkward one after
Code Generation.

### Interaction 6 — Q7 = A makes normalization non-invertible, and no property claims otherwise

Mapping an empty ARN region segment to `"global"` loses the distinction between "ARN had an empty
region" and "ARN literally said global." So `normalize_resource` is **not** injective.

Checked against the property set: nothing asserts it is. Round-trip (P1) is about
`serialize`/`deserialize` of a `Snapshot`, not about recovering the raw API item from a `ResourceRecord`.
The raw item is not retained and is not meant to be. Noted because "round-trip" invites the assumption
that normalization is reversible, and it is not — by design.

### Interaction 7 — Q8 = A slightly strengthens the idempotence property (P6)

With ordering now defined (count desc, value asc, missing last), "regrouping a grouped result by the same
key is a no-op" means equal **and identically ordered**. That is a stronger and more useful assertion
than set equality, and it is what makes serialization determinism (P2) reachable — nondeterministic group
order would make identical inputs serialize differently.

### The property set after analysis: 10, up from 6

| # | Property | Kind | Source |
|---|---|---|---|
| P1 | Round-trip, same major version | Round-trip | Existing, scoped by Interaction 5 |
| P2 | Serialization determinism | Invariant | Existing |
| P3 | Group sizes sum to total | Invariant | Existing, clarified by Interaction 2 |
| P4 | Every record in exactly one group | Invariant | Existing |
| P5 | Grouping matches the naive oracle | Oracle | Existing |
| P6 | Grouping idempotent, order included | Idempotence | Existing, strengthened by Interaction 7 |
| P7 | Gap flagged **iff** a required tag is absent | Easy verification | Existing |
| **P8** | **Accounting identity** | **Invariant** | **New — Q1 + Q4** |
| **P9** | **Grouping and classification agree** | **Consistency** | **New — Q2 + Q3** |
| **P10** | **Freshness monotonic in `now`** | **Metamorphic** | **New — Q5 + Q6** |

P10: holding `collected_at` and `stale_after` fixed, increasing `now` may take FRESH → STALE but never
STALE → FRESH. It catches sign and comparison-direction errors, which are the realistic bug in a
threshold function and are invisible to a single-value test.

PBT-01's requirement that properties be identified at Functional Design is satisfied by this table.
