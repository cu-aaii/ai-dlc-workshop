# Business Rules — U-01 Domain Core

**Phase**: CONSTRUCTION → Functional Design (artifact 2 of 3)
**Date**: 2026-08-03
**Decisions**: Part A2 of the plan (Q1–Q9, all A)

Every rule is stated once and given an ID. Where two functions need the same judgement they cite the
same rule rather than restating it — that is not tidiness, it is the mechanism that stops the grouping
view and the tag-gap view from contradicting each other (see BR-05 and P9).

Each rule names what it serves. A rule serving nothing would be invention.

---

## BR-01 — Tag presence *(the single source of truth)*

> A resource **has** required tag *K* when a key exactly equal to *K* is present **and** its value
> contains at least one non-whitespace character. Otherwise the resource **lacks** *K*.

Combines Q2 (empty ⇒ missing) and Q3 (case-sensitive). "Exactly equal" means byte-for-byte:
`Cornell:Owner` is not `cornell:owner`.

**Consulted by**: BR-05 (grouping), BR-06 (gap classification). **Nothing else may re-derive it.**

**Serves**: FR-1.4, US-03, US-04.

**Rationale, since both halves look harsh.** A resource tagged `cornell:owner=""` is exactly as
unattributable as one with no owner tag — reporting it as compliant would make the tag-gap view lie in
the one way that matters. And a resource tagged `Cornell:Owner` is genuinely invisible to the
case-sensitive cost and inventory tooling this convention exists to feed, so calling it tagged would be
reporting something false to be kind.

**Consequence accepted**: a plausible typo produces a gap the author may find surprising. That is the
correct surprise — the resource really is invisible downstream.

---

## BR-02 — Normalization, and what "malformed" means

> An upstream item is **normalizable** when its ARN parses into service, region, account and resource
> segments, and its tags form a key/value mapping. A normalizable item becomes exactly one
> `ResourceRecord`. A non-normalizable item is **skipped**: not recorded, counted in `skipped_count`,
> and its reason category counted in `skipped_reasons`.

Per Q1. **Malformed means structurally unreadable** — an ARN with too few segments, a missing ARN,
a tag structure that is not key/value. A resource missing `cornell:*` tags is **not** malformed; it is
normal, and it is US-04's entire subject.

**Serves**: FR-1.1, FR-1.2, US-02.

**Why skipping is compatible with US-02, not a weakening of it.** US-02 requires that "no resource is
**silently** omitted" and that "an incomplete inventory is **never presented as complete**." A skipped
item is counted and surfaced, so it is not silent, and an inventory reported as "299 resources, 1
unreadable" is not presented as complete. Checked against the approved text rather than assumed — see
Part A2 Interaction 1, which corrects my own earlier claim that this weakened a requirement.

**Never**: skip without counting. That is the under-reporting-while-looking-successful failure the whole
design exists to prevent.

---

## BR-03 — Region derivation

> `region` is the ARN's region segment, or the literal string **`"global"`** when that segment is empty.
> Never empty, never `None`.

Per Q7. IAM roles, CloudFront distributions and other global resources have an empty region segment.

**Serves**: FR-1.2, US-02.

**Accepted consequence**: normalization is **not invertible** — `"global"` does not distinguish "empty
segment" from a literal. Nothing in the property set claims invertibility (Part A2 Interaction 6), and
the raw item is deliberately not retained.

---

## BR-04 — Deduplication

> Within one collection, two items with the same ARN are one resource. The **last** occurrence wins.
> Each dropped occurrence increments `duplicates_removed`.

Per Q4. Pagination can in principle surface a resource twice if it changes mid-collection.

**Serves**: FR-1.1, US-02, US-03 (every count depends on it), and P3/P8.

**Accepted consequence**: "last wins" is arbitrary if two records for one ARN differ. They should not —
they describe the same resource moments apart — and the collision count makes the situation visible if
it ever happens.

---

## BR-05 — Grouping

> Grouping a snapshot by tag key *K* places each record in the group named by its value for *K*, or in
> the **missing** group (`value=None`) when it lacks *K* **per BR-01**. Every record lands in exactly
> one group. Empty groups are omitted. Groups are ordered by member count descending, then by value
> ascending, with the missing group **last** (Q8).

**Serves**: FR-1.3, US-03, and P3/P4/P5/P6.

**Records are never dropped from a grouping.** That is what makes P3's sum invariant hold and what stops
US-03 from silently under-reporting — the failure mode of a naive `group_by` that skips missing keys.

**Ordering is part of the value.** Determinism is required for P2 (serialization determinism) and for a
UI that does not reshuffle between reads.

**Accepted consequence**: the group a viewer most needs to act on lands last. US-04's dedicated tag-gap
view is the mitigation; this is the inventory grouping, not the gap report.

---

## BR-06 — Gap classification

> A record is **incomplete** when it lacks at least one of `REQUIRED_TAGS` **per BR-01**, and its
> `missing_tags` lists exactly those it lacks, in `REQUIRED_TAGS` order. Otherwise it is **complete**.
> `complete` and `incomplete` partition the snapshot's records.

**Serves**: FR-1.4, US-04, and P7/P9.

**Shares BR-01 with BR-05 by construction.** If these two ever consulted different presence logic, the
dashboard would contradict itself — a resource in the "missing owner" group that the gap view calls
compliant. P9 asserts they cannot.

---

## BR-07 — Freshness

> Given `collected_at`, a supplied `now`, and `stale_after`:
> - `collected_at > now` → **`INVALID`**
> - `now - collected_at <= stale_after` → **`FRESH`**
> - otherwise → **`STALE`**
>
> `stale_after` defaults to **3 × refresh_interval** (Q5).

**Serves**: FR-2.2, US-05, US-06, and P10.

**`now` is always a parameter.** No clock is read in this unit. That is what makes the judgement testable
without waiting for time to pass, and it is why Q8 = A of the Application Design (staleness as a *server*
judgement) is implementable at all.

**Why a multiple of the interval, not a fixed duration.** The refresh interval is a stack parameter
(FR-2.3). A fixed threshold would be silently invalidated the moment someone changed the interval —
the two numbers would drift apart with nothing to notice. Three intervals tolerates one missed run plus
scheduling jitter while still catching a dead collector within three cycles.

**Why `INVALID` rather than clamping to fresh** (Q6): a future `collected_at` cannot legitimately happen,
so reporting `FRESH` would hide a real fault, and `FRESH` is the most dangerous thing to report about
data whose provenance is broken.

---

## BR-08 — Serialization

> A snapshot serializes to JSON with sorted keys and a fixed datetime encoding (ISO-8601, UTC, explicit
> offset). Equal snapshots produce **identical bytes**. Deserialization accepts a stored snapshot when
> its `schema_version` **major** component equals the reader's; unknown top-level keys are **ignored**;
> a mismatched major version, malformed JSON, or a naive `collected_at` is **rejected** rather than
> best-effort parsed.

Per Q9, with the preserve-vs-ignore ambiguity resolved to *ignore* in Part A2 Interaction 5.

**Serves**: FR-2.4, US-08, and P1/P2.

**JSON only** — no `pickle`, no `yaml.load` (SECURITY-14).

**Determinism is a requirement, not an optimization.** Non-deterministic output would make P1 and P2
flaky rather than failing, which is worse than not having them.

**Ignoring unknown keys is safe *here specifically*** because **no code path reads a snapshot and writes
it back**: the collector always constructs fresh and does a single `PutObject`; the API only reads. Key
loss is therefore unobservable by construction. **P1 is correspondingly scoped** to snapshots produced by
the same major version — stated plainly rather than left as an unexamined "round-trip holds."

**Rejecting a naive `collected_at`** rather than assuming UTC: assuming a timezone invents information,
and BR-07 compares against a supplied `now` whose meaning depends on it.

---

## Rule → requirement coverage

| Rule | Serves | Stories |
|---|---|---|
| BR-01 Tag presence | FR-1.4 | US-03, US-04 |
| BR-02 Normalization / skip | FR-1.1, FR-1.2 | US-02 |
| BR-03 Region | FR-1.2 | US-02 |
| BR-04 Deduplication | FR-1.1 | US-02, US-03 |
| BR-05 Grouping | FR-1.3 | US-03 |
| BR-06 Gap classification | FR-1.4 | US-04 |
| BR-07 Freshness | FR-2.2 | US-05, US-06 |
| BR-08 Serialization | FR-2.4 | US-08 |

**Every acceptance criterion of US-03, US-04 and US-05 maps to a rule above.** US-02 and US-08 are
U-02-owned; the rules here are U-01's contribution to them, and the remainder (pagination, HTTP, the
response envelope) is U-02's.

**No rule requires** AWS, a clock read, an environment read, a file, a socket, or a subprocess. The
`core/` boundary stated in `unit-of-work.md` — no `boto3`, no `os`, no `datetime.now()` — holds across
all eight.

---

## ⚠️ Cross-unit obligation for U-02

Q6 = A makes `Freshness` three-valued, and `component-methods.md`'s degraded-state table has five rows
with nowhere for the third. That table belongs to C-03, which is **U-02's**. Recorded here so it is not
lost between the two units' Functional Design passes:

| Situation | HTTP | body `status` | UI |
|---|---|---|---|
| Snapshot present, `collected_at` in the future (`INVALID`) | **503** | `error` | Generic failure. Not presented as data. |

503 rather than 200 because this is a fault, not a state of the world — consistent with how US-06 already
treats an unreadable snapshot.

**Also for U-02**: `skipped_count`, `duplicates_removed` and `raw_returned` are on the snapshot and must
reach the UI, or Q1 = A's honesty guarantee stops at the API boundary and the "surface the count" half of
the decision is never delivered.
