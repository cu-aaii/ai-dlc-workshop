# Business Logic Model — U-01 Domain Core

**Phase**: CONSTRUCTION → Functional Design (artifact 3 of 3)
**Date**: 2026-08-03
**Rules referenced**: `business-rules.md` BR-01..BR-08 · **Entities**: `domain-entities.md`

Algorithms, totality, and the property set. Technology-agnostic: no AWS, no I/O, no clock.

---

## Totality — which functions can fail

Stated first because it is the property most often left implicit and most expensive to discover late.

| Function | Total? | Raises on |
|---|---|---|
| `has_required_tag` | **Total** | never |
| `normalize_resource` | Partial | a non-normalizable item (BR-02) |
| `normalize_all` | **Total** | never — absorbs BR-02 skips into counts |
| `build_snapshot` | Partial | naive `collected_at`; a negative count; ARN-duplicate input |
| `serialize_snapshot` | **Total** | never |
| `deserialize_snapshot` | Partial | malformed JSON, major-version mismatch, naive datetime (BR-08) |
| `group_by_tag` | Partial | `tag_key` not in `REQUIRED_TAGS` |
| `classify_tag_gaps` | **Total** | never |
| `evaluate_freshness` | **Total** | never — a future timestamp is a *value* (`INVALID`), not an error |
| `_reference_group_by_tag` | Partial | same as `group_by_tag` |

**The two deliberate choices here.**

`normalize_all` is total while `normalize_resource` is partial. That is the whole of Q1 = A expressed in
type terms: the per-item function is allowed to fail, and the collection-level function converts those
failures into counts rather than propagating them. One malformed ARN cannot take down a snapshot because
the only function the collector calls cannot fail that way.

`evaluate_freshness` is total. A future timestamp returns `INVALID` rather than raising, because
staleness evaluation sits on the read path and an exception there would turn a data-provenance fault into
an unexplained 500 instead of the deliberate 503 in BR-07's cross-unit obligation.

---

## `has_required_tag(record, key) -> bool`

The single presence predicate (BR-01). Everything else defers to it.

```
value = record.tags.get(key)          # exact key match — no case folding
return value is not None and value.strip() != ""
```

Three lines, and two other functions depend on it. Kept as its own function precisely so it cannot be
inlined differently in two places — the drift P9 exists to catch.

---

## `normalize_resource(raw) -> ResourceRecord`

```
parse raw.ResourceARN into (partition, service, region, account, resource)
  → not parseable, or ARN absent      ⇒ raise Malformed("arn")
tags = mapping from raw.Tags          → not key/value shaped ⇒ raise Malformed("tags")
region = region_segment or "global"   # BR-03
resource_type = first component of the resource segment
return ResourceRecord(arn, service, resource_type, region, tags)
```

`Malformed` carries a **reason category**, not a message — the categories become `skipped_reasons` keys,
so they must be a small closed set (`"arn"`, `"tags"`), not free text. Free-text reasons would make
`skipped_reasons` unbounded and could carry fragments of unparseable input into the snapshot.

---

## `normalize_all(raw_items) -> NormalizationResult`

Total. This is where Q1 = A and Q4 = A actually live.

```
records = ordered mapping arn -> ResourceRecord
skipped = 0 ; reasons = counter ; duplicates = 0

for item in raw_items:
    try: record = normalize_resource(item)
    except Malformed as m:
        skipped += 1 ; reasons[m.category] += 1 ; continue      # BR-02
    if record.arn in records: duplicates += 1                    # BR-04, last wins
    records[record.arn] = record

return NormalizationResult(
    records = tuple(records.values()),
    raw_returned = len(raw_items),
    skipped_count = skipped, skipped_reasons = reasons,
    duplicates_removed = duplicates)
```

**P8 holds by construction**: every input takes exactly one of three paths — skipped, counted as a
duplicate, or present in `records`. The identity is not an extra check bolted on; it is what the loop
shape guarantees. `raw_returned + 0` cannot drift from the sum unless the loop is restructured, and P8
fails loudly if it is.

Insertion-ordered mapping so "last wins" is unambiguous and output order is deterministic (BR-08, P2).

---

## `build_snapshot(result, collected_at, schema_version) -> Snapshot`

```
reject naive collected_at                     # BR-08 — never assume a timezone
reject negative counts
reject duplicate ARNs in result.records       # defensive: normalize_all cannot produce them,
                                              # but build_snapshot is also called from tests
assert result.raw_returned == len(records) + skipped_count + duplicates_removed   # P8
return Snapshot(...)
```

The clock is **injected**. `build_snapshot` never reads one.

The duplicate re-check is deliberate redundancy: it guards the invariant at the aggregate boundary rather
than trusting the one caller, and it means a hand-built `Snapshot` in a test cannot violate the
uniqueness that P3 and P4 assume.

---

## `serialize_snapshot(s) -> bytes` / `deserialize_snapshot(b) -> Snapshot`

```
serialize:    JSON, sort_keys=True, ISO-8601 UTC with explicit offset,
              no floats in counts, UTF-8 → bytes
deserialize:  parse JSON  → malformed ⇒ raise
              major(schema_version) != major(READER_VERSION) ⇒ raise      # BR-08
              ignore unrecognized top-level keys                          # Q9, resolved: ignore
              parse collected_at; naive ⇒ raise
              reconstruct; re-assert P8
```

`sort_keys` plus a fixed datetime format is what makes P2 (determinism) hold, which in turn is what makes
P1 (round-trip) a byte-level assertion rather than a structural one.

Re-asserting P8 on read means a snapshot that was corrupted in storage in a way that still parses as JSON
is caught as a fault rather than silently serving arithmetic that does not add up.

---

## `group_by_tag(snapshot, tag_key) -> GroupingResult`

```
reject tag_key not in REQUIRED_TAGS            # closed allowlist; U-02 relies on this
buckets: value -> [records]
for record in snapshot.resources:
    key = record.tags[tag_key] if has_required_tag(record, tag_key) else None    # BR-01
    buckets[key].append(record)
groups = [Group(v, tuple(rs)) for v, rs in buckets]
sort: (-len(resources), value) with None sorted last     # BR-05 / Q8
omit empty groups                                        # cannot arise, asserted anyway
return GroupingResult(tag_key, tuple(groups), total=len(snapshot.resources))
```

Every record is appended exactly once, so P3 and P4 hold structurally rather than by a subsequent check.
The `None` bucket is created only if something lands in it, which is what keeps the missing group absent
rather than empty.

### `_reference_group_by_tag` — the oracle

Test-only, and **it must be written independently** or P5 asserts nothing. The reference is the
deliberately naive version: for each distinct value, filter the whole record list; append the missing
group by filtering again; sort with a plain comparator. Quadratic and obviously correct. If it is written
by copying the real implementation, the oracle property becomes a tautology — noted because that is the
easy mistake.

---

## `classify_tag_gaps(snapshot, required=REQUIRED_TAGS) -> TagGapReport`

```
for record in snapshot.resources:
    missing = tuple(k for k in required if not has_required_tag(record, k))   # BR-01, ordered
    → missing empty  ⇒ complete
    → else           ⇒ incomplete with missing_tags = missing
```

Iterating `required` (not the record's keys) is what makes `missing_tags` deterministically ordered, which
P2 needs.

Sharing `has_required_tag` with `group_by_tag` is what makes P9 true by construction rather than by
coincidence.

---

## `evaluate_freshness(collected_at, now, stale_after) -> Freshness`

```
if collected_at > now:              return INVALID      # BR-07 / Q6
if now - collected_at <= stale_after: return FRESH
return STALE
```

Total. Order matters: the `INVALID` check is first, because a future timestamp would otherwise satisfy the
`FRESH` comparison (a negative age is trivially under any threshold) — which is precisely the bug Q6 = A
exists to prevent, and precisely what P10 catches.

---

## Property set (PBT-01 satisfied here)

Ten properties. Six carried from `component-methods.md`, three new from the answer interactions, one
metamorphic.

| # | Property | Statement | Kind | Rule |
|---|---|---|---|---|
| P1 | Round-trip | `deserialize(serialize(s)) == s` for all `s` at the reader's major version | Round-trip | BR-08 |
| P2 | Determinism | `s1 == s2` ⇒ `serialize(s1) == serialize(s2)`, bytewise | Invariant | BR-08 |
| P3 | Sum | `sum(len(g.resources)) == r.total == len(s.resources)` | Invariant | BR-05 |
| P4 | Partition | every record in exactly one group; no group empty | Invariant | BR-05 |
| P5 | Oracle | `group_by_tag == _reference_group_by_tag` | Oracle | BR-05 |
| P6 | Idempotence | regrouping a grouped result by the same key changes nothing, **order included** | Idempotence | BR-05 |
| P7 | Gap iff | record in `incomplete` **iff** some required tag fails `has_required_tag` | Easy verification | BR-06 |
| **P8** | **Accounting** | `raw_returned == len(resources) + skipped_count + duplicates_removed` | Invariant | BR-02, BR-04 |
| **P9** | **Agreement** | record in the `None` group for *K* **iff** `classify_tag_gaps` reports *K* missing | Consistency | BR-01 |
| **P10** | **Monotonicity** | with `collected_at`/`stale_after` fixed, increasing `now` never takes STALE → FRESH | Metamorphic | BR-07 |

**What each of the three new ones buys.**

- **P8** makes Q1 = A's honesty mechanically checkable. Without it, "we skipped one" is an unverifiable
  claim and a resource could vanish with no bucket accounting for it.
- **P9** catches the specific drift that would make the dashboard contradict itself — a resource in the
  "missing owner" group that the tag-gap view calls compliant. Two views on one snapshot must agree; this
  is that requirement as an assertion.
- **P10** catches sign and comparison-direction errors in a threshold function. Those are the realistic
  bug in `evaluate_freshness` and they are invisible to single-value tests, which is exactly what
  property-based testing is for.

### Generator obligations

The generators are U-02's contribution to US-10 (recorded in `unit-of-work-story-map.md`), but the shapes
they must cover are U-01's to specify:

- ARNs with an empty region segment (BR-03 / `"global"`)
- Tag values that are empty, whitespace-only, and normal (BR-01)
- Tag keys differing from required ones only by case (BR-01)
- Duplicate ARNs within one input (BR-04)
- Non-normalizable items mixed with valid ones (BR-02)
- `collected_at` before, equal to, and after `now` (BR-07)
- Snapshots with zero resources — distinct from no snapshot, which U-01 cannot represent
- Snapshots carrying an unrecognized top-level key (BR-08 / Q9)

The last two are the ones a generator author would not think of unprompted, which is why they are listed.

---

## Nothing here that cannot be settled

No open item at this stage. Everything Q1–Q9 raised is resolved in `business-rules.md`, including the Q9
ambiguity that was mine (Part A2 Interaction 5).

**Carried out to U-02**, not open here: the `INVALID` → 503 row in C-03's state table, and surfacing
`skipped_count` / `duplicates_removed` / `raw_returned` to the UI. Both are in `business-rules.md`'s
cross-unit obligation section. If U-02's pass drops them, Q1 = A's "surface the count" half is never
delivered and Q6 = A's third state has nowhere to appear.
