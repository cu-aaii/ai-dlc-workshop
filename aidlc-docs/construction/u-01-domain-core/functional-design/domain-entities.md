# Domain Entities — U-01 Domain Core

**Phase**: CONSTRUCTION → Functional Design (artifact 1 of 3)
**Date**: 2026-08-03
**Decisions**: `construction/plans/u-01-domain-core-functional-design-plan.md` Part A2 (Q1–Q9, all A)

Technology-agnostic. No AWS type, no serialization format, and no clock appears in any definition here.
Types are expressed in Python-ish notation because that is the implementation language, not because the
entities depend on it.

---

## The domain in one sentence

An **inventory snapshot** is an immutable, timestamped set of **resource records**, each carrying every
tag its resource had; everything else in this unit is a *view* derived from one snapshot plus, where
time matters, a supplied instant.

There is exactly one aggregate — `Snapshot`. Nothing else has an independent lifecycle.

---

## `ResourceRecord`

One AWS resource as the inventory knows it.

| Field | Type | Rule |
|---|---|---|
| `arn` | `str` | **Identity.** Non-empty. Uniquely identifies the record within a snapshot (Q4). |
| `service` | `str` | Derived from the ARN's service segment. Never from a tag. |
| `resource_type` | `str` | Derived from the ARN's resource segment. Required by FR-1.2. |
| `region` | `str` | Derived from the ARN's region segment; **`"global"`** when that segment is empty (Q7). Never empty, never `None`. |
| `tags` | `Mapping[str, str]` | **All** tags the resource carries, not only `cornell:*`. Keys exactly as AWS reported them — no case folding (Q3). |

**Identity and equality**
- Identity is `arn` alone. Two records with the same ARN are the same resource (Q4).
- **Equality is structural** — all five fields. This matters: P1 (round-trip) and P6 (idempotence) are
  equality assertions, so equality must be total and value-based, never identity-based.
- **Immutable.** Frozen, with `tags` treated as read-only. Nothing in this unit mutates a record after
  construction, and immutability is what makes the equality assertions meaningful rather than
  accidental.

**Deliberately absent**
- No `is_compliant` flag. Compliance is computed by `classify_tag_gaps`, not stored — a stored flag can
  disagree with the tags it was derived from.
- No `cornell_owner` / `cornell_blueprint` convenience fields. Required tags are read through the one
  predicate in `business-rules.md`; promoting four of them to fields would create a second path to the
  same question and let the two drift (P9 exists to catch exactly that drift).
- No raw upstream payload. Normalization is not reversible (Q7), and retaining the raw item would imply
  it is.

---

## `Snapshot`

The aggregate. One collection run's complete result, including what it could not use.

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `str` | Semantic `MAJOR.MINOR`. Read compatibility is major-version equality (Q9). |
| `collected_at` | `datetime` | **Timezone-aware, UTC.** A naive datetime is invalid input, not a value to coerce — coercion would silently invent a timezone. |
| `resources` | `Sequence[ResourceRecord]` | The usable records. ARN-unique (Q4). |
| `skipped_count` | `int` | Items the upstream returned that could not be normalized (Q1). `>= 0`. |
| `skipped_reasons` | `Mapping[str, int]` | Reason category → count. Carries *why* without carrying unbounded detail or anything resembling an ARN of a resource that failed to parse. |
| `duplicates_removed` | `int` | ARN collisions dropped by deduplication (Q4). `>= 0`. |
| `raw_returned` | `int` | Items the upstream returned, before skipping or deduplication. |

**The four counts are the point.** `raw_returned` exists solely so P8 can be asserted:

```
raw_returned == len(resources) + skipped_count + duplicates_removed
```

Without it, "we skipped some" is an unverifiable claim. With it, a resource cannot disappear without
landing in exactly one bucket — which is what makes Q1 = A honest rather than merely convenient.

**Extensibility** (FR-2.4, and the queued telemetry amendment)
- Unknown top-level keys encountered on read are **ignored, not fatal** (Q9, resolved in Part A2
  Interaction 5). Safe here specifically because **no code path reads a snapshot and writes it back** —
  the collector always constructs fresh, the API only reads — so a dropped key is unobservable.
- A future sibling key (`costs`, `metrics`) is therefore an additive change requiring no migration.

**Deliberately absent**
- No derived aggregates. Q2 = A of the Application Design put aggregation at read time; storing a
  grouping inside the snapshot would let it disagree with the `resources` it came from.
- No `is_stale`. Staleness needs a `now` the snapshot does not have, and freezing a verdict at write
  time is exactly the bug US-05 exists to prevent.

---

## `Group` and `GroupingResult`

One grouping of a snapshot by one tag key.

```
Group:
  value:      str | None        # None == the record lacks this tag per the presence rule
  resources:  Sequence[ResourceRecord]

GroupingResult:
  tag_key:    str
  groups:     Sequence[Group]   # ordered: count desc, value asc, None last (Q8)
  total:      int               # == len(snapshot.resources)
```

- `value=None` is the **missing** group, and "missing" is decided by the single presence predicate — so
  it holds records with no such key, with a wrong-case key, and with an empty value (Q2, Q3).
- The missing group is **omitted entirely when empty**, rather than present with zero members. An empty
  group would violate the "no empty groups" invariant and would render as a phantom row.
- `total` is stored rather than computed at read so P3 has something to assert against.
- **Order is part of the value** (Q8). Two `GroupingResult`s with the same groups in a different order
  are **not** equal, which is what makes P6 (idempotence including order) and P2 (serialization
  determinism) reachable.

---

## `TagGapReport`

Which resources lack which required tags.

```
TagGapReport:
  complete:    Sequence[ResourceRecord]
  incomplete:  Sequence[IncompleteRecord]

IncompleteRecord:
  record:        ResourceRecord
  missing_tags:  Sequence[str]   # ordered as REQUIRED_TAGS is, for determinism
```

- `missing_tags` is non-empty for every entry in `incomplete` — that is the definition, and P7 asserts it.
- **Which** tags are missing is returned, not just that some are. US-04 is only actionable with the
  specifics.
- `complete` and `incomplete` partition `snapshot.resources`: every record appears in exactly one, and
  their sizes sum to the total.
- `REQUIRED_TAGS` is the fixed tuple `("cornell:owner", "cornell:blueprint",
  "cornell:blueprint-version", "cornell:deployment-id")`, ordered, lowercase, from `CLAUDE.md`.

---

## `Freshness`

Three-valued, after Q6.

| Value | Meaning |
|---|---|
| `FRESH` | `0 <= now - collected_at <= stale_after` |
| `STALE` | `now - collected_at > stale_after` |
| `INVALID` | `collected_at > now` — impossible in a correct system, so it is a fault, not an age |

`INVALID` exists because reporting `FRESH` about data whose provenance is broken is the most dangerous
thing this unit could say. It is the one `Freshness` value that means "do not trust this snapshot at
all," and it maps to a 503 rather than a 200 — see the cross-unit obligation in `business-rules.md`.

---

## Entity relationships

```
Snapshot 1 ──── * ResourceRecord          composition; records have no life outside a snapshot

Snapshot ──derives──> GroupingResult      one per tag key, computed on demand, never stored
Snapshot ──derives──> TagGapReport        computed on demand, never stored
Snapshot + now + stale_after ──> Freshness

GroupingResult *Group ──references──> ResourceRecord   the same records, regrouped, never copies
```

Every arrow out of `Snapshot` is a **pure derivation**. None is persisted, none is cached, and none can
disagree with the snapshot it came from — because there is nowhere for a stale copy to live.

**No entity references a Group, GroupingResult, TagGapReport, or Freshness.** They are outputs. That is
why the dependency graph terminates here, and why every one of them can be constructed in a test from a
literal snapshot with no setup.

---

## What this unit refuses to model

Recorded because an implementer filling a perceived gap would break an approved decision.

| Not modelled | Why |
|---|---|
| A user, session, or identity | No identity system exists (FR-5.5) |
| An HTTP request or response | U-02's business (C-03) |
| A bucket, key, region config, or ARN of the snapshot itself | U-01 knows nothing about storage |
| Cost | FR-8 deferred, data source undecided |
| A refresh trigger or collection schedule | Read never causes write (FR-2.1) |
| "Current time" as state | `now` is always a parameter. There is no clock in this unit. |
| Business-level telemetry | Queued amendment; will arrive as a sibling key, which Q9 = A already permits |
