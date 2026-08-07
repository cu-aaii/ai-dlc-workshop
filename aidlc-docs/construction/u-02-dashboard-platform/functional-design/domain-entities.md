# Domain Entities — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Functional Design (artifact 1 of 4)
**Date**: 2026-08-03

---

## U-02 introduces no domain entities

Every domain type belongs to **U-01**: `ResourceRecord`, `Snapshot`, `Group`, `GroupingResult`,
`TagGapReport`, `IncompleteRecord`, `Freshness`, `NormalizationResult`, `REQUIRED_TAGS`.

Stated first and plainly, because the tempting thing for a unit that owns a collector, an API and a UI
is to define its own resource shape "for the response" — and that would create a second model that can
drift from the one ten property-based tests already guard. **If a domain type appears in U-02, the
boundary has been crossed.**

What U-02 adds is *plumbing* types: outcomes, envelopes, and view state. They carry no business meaning
and no rules; they exist to move U-01's values across an HTTP boundary and onto a screen.

## The import contract

```python
from dashboard.core import Snapshot, group_by_tag, evaluate_freshness, CoreError  # correct
from dashboard.core.model import Snapshot                                          # FORBIDDEN
```

`__all__` in `dashboard/core/__init__.py` is the whole contract — 22 names. U-02 imports from the
package, never a submodule, so U-01's internal file layout can change without breaking a unit boundary.

`_reference_group_by_tag` is deliberately **not** exported. If U-02 ever reaches for it, P5 would be
comparing an implementation against itself.

---

## C-01 Collector types

```python
@dataclass(frozen=True)
class CollectionOutcome:
    result: NormalizationResult      # U-01's type, not a copy
    pages_fetched: int
    duration_seconds: float
```

`pages_fetched` exists for the Q1 = A page-limit rule and for the metric C-09 alarms on. Nothing else.

```python
class CollectorFailure(StrEnum):
    PAGE_LIMIT_EXCEEDED = "page_limit_exceeded"
    UPSTREAM_THROTTLED  = "upstream_throttled"
    UPSTREAM_ERROR      = "upstream_error"
    WRITE_FAILED        = "write_failed"
```

**A closed set, and it is load-bearing** (Part A2 Interaction 2). The collector-failure alarm watches an
error *count* and cannot say why. So the reason must be in the log as a stable code, or the runbook's
first step — "was the page limit hit?" — has nothing to check and the operator starts debugging IAM.

---

## C-03 Read API types

```python
class SnapshotState(StrEnum):
    PRESENT    = "present"
    ABSENT     = "absent"        # the collector has never successfully run
    UNREADABLE = "unreadable"    # the object exists and does not parse

@dataclass(frozen=True)
class LoadOutcome:
    state: SnapshotState
    snapshot: Snapshot | None
```

**Three states, not a boolean.** A bare `try/except` collapses "never collected" and "corrupt", and
US-06 requires them to look different to the user — they mean opposite things.

```python
@dataclass(frozen=True)
class ApiResponse:
    http_status: int
    body_status: str             # "ok" | "stale" | "no_data" | "error"
    payload: Mapping[str, object]
```

Both fields, always (Application Design Q8). A status code alone makes "stale" a client-side judgement;
a body field alone makes failures invisible to the status-code-watching layer C-09's alarms depend on.

### Response envelope

Every `/api/*` response carries the same top-level shape, so the UI has one thing to reason about:

```json
{
  "status": "ok",
  "collected_at": "2026-08-03T12:00:00+00:00",
  "freshness": "fresh",
  "counts": { "resources": 42, "skipped": 1, "duplicates_removed": 0, "raw_returned": 43 },
  "data": { }
}
```

**`counts` is inherited obligation 2 made concrete.** `skipped`, `duplicates_removed` and `raw_returned`
travel in *every* response rather than only on an inventory view, because the skip-and-count decision is
only honest if the count is visible wherever the data is. If this object is dropped to slim the payload,
the guarantee U-01 was built around ends at a boundary nobody sees.

`freshness` is the server's judgement (U-01's `evaluate_freshness`), never recomputed in the browser.

---

## C-06 UI view state

```ts
type ViewName = 'inventory' | 'grouping' | 'tag-gaps' | 'status'

type ViewState<T> =
  | { kind: 'loading' }
  | { kind: 'ready';  envelope: Envelope<T> }   // envelope.status decides what renders
  | { kind: 'failed'; httpStatus: number }
```

Per Q4 = A: `useState` + `useEffect` per view, no store, no router, no data-fetching library. Four
read-only views, no shared mutable state, no forms — a store would be infrastructure for a problem this
UI does not have, and every dependency is surface Q11 = B decided not to scan.

**`kind: 'ready'` does not mean "there is data."** It means the request succeeded; `envelope.status` then
distinguishes `ok` / `stale` / `no_data`. Collapsing those into `ready` versus `failed` is precisely how
"no data collected yet" and "no resources found" become indistinguishable, which is the mistake US-06
exists to prevent.

---

## What U-02 deliberately does not model

| Absent | Why |
|---|---|
| Any copy of `ResourceRecord` or `Snapshot` | U-01 owns them; a second shape can drift from ten tested properties |
| A user, session, token, or role | No identity system anywhere (FR-5.5) |
| A write or mutation type | The dashboard is read-only (FR-4.5); there is no write path to omit |
| A refresh-trigger request | A read never causes a write (FR-2.1, US-07) |
| A cost type | FR-8 deferred, data source undecided (US-D1/D2) |
| A client-side freshness calculation | Server judgement only, or two views can disagree (US-05) |
| A client-side cache | `/api/*` is no-cache; caching reintroduces the US-05 failure |
