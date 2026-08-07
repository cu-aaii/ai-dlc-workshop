# Logical Components — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Design (artifact 2 of 2)
**Date**: 2026-08-03

---

## U-01 contributes zero infrastructure components

The stage illustrates "logical components" as queues, caches, and circuit breakers. **U-01 introduces none
of them, and will introduce none.** No queue, no cache, no circuit breaker, no load balancer, no service
mesh, no database, no connection pool, no scheduler, no bucket, no function, no role.

Stated first and plainly so a reader does not scan for a missing infrastructure section and assume it was
forgotten. U-01 is a Python package imported in-process. Its deployable footprint is *zero* — it ships
inside two container images that **U-02** builds and deploys.

Every infrastructure component this blueprint has (C-01, C-02, C-03, C-06, C-07, C-09, both templates, the
EventBridge schedule, the WAF ACL, the alarms) belongs to U-02 and appears in its artifacts.

So what follows is U-01's **internal logical structure**: modules, their dependency direction, the public
surface, and the error types. Those are the real components at this level.

---

## Internal module structure

```
src/dashboard/core/
  __init__.py      the public surface — __all__ (Q4 = A)
  model.py         C-04: ResourceRecord, Snapshot, normalize_*, build_snapshot, (de)serialize
  aggregation.py   C-05: group_by_tag, classify_tag_gaps, evaluate_freshness, has_required_tag
  errors.py        CoreError hierarchy (Q3 = A)
```

| Module | Depends on | Depended on by |
|---|---|---|
| `errors.py` | nothing | `model.py`, `aggregation.py`, and U-02 |
| `model.py` | `errors.py` | `aggregation.py`, `__init__.py` |
| `aggregation.py` | `model.py`, `errors.py` | `__init__.py` |
| `__init__.py` | all three | **U-02 only** |

**Dependency direction is one-way: `aggregation → model → errors`.** Never the reverse. `aggregation.py`
must not be imported by `model.py` — grouping is computed *over* the entities, so a reverse edge would make
the entity module depend on a view of itself, and would create the first cycle in a graph that is currently
strictly acyclic at both the unit and module level.

`has_required_tag` lives in `aggregation.py` and is the **single presence predicate** (BR-01) that both
`group_by_tag` and `classify_tag_gaps` consult. It must not be duplicated into `model.py`, because P9
asserts the two consumers agree, and two implementations is exactly how they would stop agreeing.

---

## The public surface (Q4 = A)

`__all__` in `src/dashboard/core/__init__.py` **is** the U-01 ↔ U-02 contract. A reviewer can read one list
and know everything U-02 is permitted to depend on.

```python
__all__ = [
    # Entities
    "ResourceRecord", "Snapshot",
    "Group", "GroupingResult",
    "TagGapReport", "IncompleteRecord",
    "Freshness",
    "NormalizationResult",
    # Constants
    "REQUIRED_TAGS",
    # Model operations (C-04)
    "normalize_resource", "normalize_all", "build_snapshot",
    "serialize_snapshot", "deserialize_snapshot",
    # Aggregation operations (C-05)
    "has_required_tag", "group_by_tag", "classify_tag_gaps", "evaluate_freshness",
    # Errors — U-02 must be able to catch these
    "CoreError", "MalformedResource", "IncompatibleSchema", "InvalidSnapshot",
]
```

**The error types are in the surface deliberately** (Part A2 Interaction 4). An `__all__` listing only
functions and entities, while U-02 needs to catch U-01's exceptions, would push U-02 toward
`except Exception` — which would swallow genuine bugs alongside expected failures.

**Not in the surface**, and U-02 must not import them:

| Excluded | Why |
|---|---|
| `_reference_group_by_tag` | Test-only oracle. In the surface it could be used in production, and P5 would then compare an implementation against itself. |
| Submodule paths (`dashboard.core.model`) | Q4 = A's point: U-02 depends on the package, not the file layout, so files can move without a cross-unit break. |
| Any internal ARN-parsing helper | An implementation detail of BR-02/BR-03. |

---

## Error types as components

| Type | Raised by | U-02's expected handling |
|---|---|---|
| `CoreError` | never directly | base — catch-all boundary |
| `MalformedResource(category)` | `normalize_resource` | **Never seen by U-02** — `normalize_all` absorbs it into `skipped_count` (PAT-3) |
| `IncompatibleSchema` | `deserialize_snapshot` | `UNREADABLE` → **503** |
| `InvalidSnapshot` | `build_snapshot`, `deserialize_snapshot` | `UNREADABLE` → **503** |

`MalformedResource` never escaping to U-02 is the whole point of PAT-3: the only normalization function
U-02 calls is total. If U-02 ever needs to catch `MalformedResource`, something has been wired wrong.

**Content**: category only. No ARN, no tag key, no tag value, no index (NFR-S1).

---

## The U-01 ↔ U-02 interface, as U-02 sees it

| Property | Value |
|---|---|
| Mechanism | Python import, in-process |
| Transport | none — no HTTP, no queue, no socket, no shared file |
| Serialization across the boundary | none — Python objects pass directly |
| Versioning | none needed — same repo, same commit, same image |
| Failure modes | `IncompatibleSchema`, `InvalidSnapshot`. That is all. |
| Latency | function-call cost |
| Retry / timeout / circuit breaking | **not applicable** — nothing to retry |

There is no network hop at this boundary, so there is nothing to make resilient. Worth stating because a
reader arriving from the vendored rules' microservice framing will look for an inter-service contract, and
there is none.

**What U-02 must supply on every call**: `now` and `stale_after` for freshness (PAT-6), and `collected_at`
plus `schema_version` for `build_snapshot`. U-01 will not read a clock, an environment variable, or a
config file to fill these in — if U-02 forgets one, it is a type error, not a silent default.

---

## Boundary enforcement

**NFR-M1**, run in `tools/check` alongside the existing cfn-lint and pytest blocks. A grep over
`src/dashboard/core/` failing the build on any of:

| Forbidden | Because |
|---|---|
| `boto3`, `botocore` | §4.5 — the AWS-free boundary that makes ten properties testable |
| `import os`, `os.environ` | PAT-6 — no ambient config |
| `datetime.now(`, `utcnow(`, `time.time(` | PAT-6 — the clock is injected, or P10 is unassertable |
| `logging`, `print(` | NFR-S6 — U-01 emits nothing, so it cannot leak a NetID through a log |
| `assert ` | **PAT-4** — `assert` is stripped under `python -O`, and NFR-R3 needs P8 checked on a production read path |
| `pickle`, `yaml` | SECURITY-14 / NFR-S4 |

The last two are additions this stage produced: `assert` from Interaction 3, and `print(` alongside
`logging` because a stray `print` leaks exactly as effectively as a log line.

**This check has never run.** `tools/check` requires `uv` and `terraform`, neither installed in the
environment these decisions were made in (§A1.6). The grep is specified, not demonstrated.

---

## What this unit deliberately has no component for

| Absent | Owner |
|---|---|
| Storage of any kind | U-02 (C-02) |
| HTTP handling, routing, response shaping | U-02 (C-03) |
| Scheduling | U-02 (EventBridge under C-01) |
| Caching | U-02 (C-07); `/api/*` is no-cache |
| Logging, metrics, alarms | U-02 (C-09) |
| Access control | U-02 (C-07 WAF) |
| Deployment, rollback | U-02 — and RESILIENCY-04 is **assigned** to its NFR Design |
| Incident response | U-02 — RESILIENCY-15 likewise |
| Cost computation | Deferred (FR-8, US-D1/D2) |

---

## Carried forward

- **Cross-unit obligations for U-02**, now four:
  1. `Freshness.INVALID` → a sixth row in C-03's state table: **503 / `error`**
  2. `skipped_count`, `duplicates_removed`, `raw_returned` must reach the UI
  3. C-01 must log enough at its own boundary to identify a skipped item, because U-01 deliberately cannot
  4. **RESILIENCY-04 and -15 are assigned to U-02's NFR Design** — second deferral, count recorded
- **§6.4** site-sync ordering — unchanged, U-02, Infrastructure Design
- **Two review-only requirements carry disproportionate weight**: NFR-T5 (independent oracle) and NFR-T7
  (generator coverage). Both invisible to tooling; both silent when wrong
- **`tools/check` still unexecutable here** — every automated check in this unit is specified, not observed
