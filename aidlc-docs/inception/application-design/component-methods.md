# Component Methods — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 2 of 5)
**Date**: 2026-08-03

Signatures are Python-typed because the runtime components are Python (repo convention: Lambda means
container images, and the existing tooling is Python). They are **design intent**, not final code —
Functional Design refines them and Code Generation writes them. Names are chosen to be stable enough
that PBT-01's property identification at Functional Design has something concrete to attach to.

---

## C-04 — Inventory Model (pure)

The only component with no dependency on anything, so it is specified first.

```python
# Types
@dataclass(frozen=True)
class ResourceRecord:
    arn: str
    service: str                    # derived from the ARN, not from a tag
    region: str
    tags: Mapping[str, str]         # all tags, not only cornell:*

@dataclass(frozen=True)
class Snapshot:
    schema_version: str
    collected_at: datetime          # UTC, timezone-aware
    resources: tuple[ResourceRecord, ...]
```

| Method | Signature | Notes |
|---|---|---|
| `normalize_resource` | `(raw: Mapping) -> ResourceRecord` | Raw Tagging API item → record. Raises on a malformed item rather than emitting a partial record. |
| `build_snapshot` | `(records: Sequence[ResourceRecord], collected_at: datetime, schema_version: str) -> Snapshot` | Clock is **injected**, never read here. |
| `serialize_snapshot` | `(s: Snapshot) -> bytes` | JSON, sorted keys, no `pickle`, no `yaml` (SECURITY-14). Deterministic output — a requirement, since non-determinism would make the round-trip property flaky rather than failing. |
| `deserialize_snapshot` | `(b: bytes) -> Snapshot` | Rejects unknown `schema_version` explicitly rather than best-effort parsing. |

**Properties owned here** (PBT §4.2)
- Round-trip: `deserialize_snapshot(serialize_snapshot(s)) == s` for all `s`
- Serialization determinism: two calls on equal snapshots give identical bytes

`frozen=True` and `tuple` are deliberate: the round-trip and idempotence properties are equality
assertions, and mutable defaults make those assertions accidental rather than structural.

---

## C-05 — Aggregation Core (pure)

```python
REQUIRED_TAGS = ("cornell:owner", "cornell:blueprint",
                 "cornell:blueprint-version", "cornell:deployment-id")

@dataclass(frozen=True)
class Group:
    value: str | None               # None == the resource lacks this tag
    resources: tuple[ResourceRecord, ...]

@dataclass(frozen=True)
class GroupingResult:
    tag_key: str
    groups: tuple[Group, ...]
    total: int                      # must equal sum of group sizes — the invariant, stored so it is checkable

@dataclass(frozen=True)
class TagGapReport:
    complete: tuple[ResourceRecord, ...]
    incomplete: tuple[tuple[ResourceRecord, tuple[str, ...]], ...]   # record + which tags are missing

class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
```

| Method | Signature | Notes |
|---|---|---|
| `group_by_tag` | `(s: Snapshot, tag_key: str) -> GroupingResult` | Resources lacking `tag_key` land in the `value=None` group. **Never dropped** — that is what makes the sum invariant hold and what stops US-03 from silently under-reporting. |
| `classify_tag_gaps` | `(s: Snapshot, required: Sequence[str] = REQUIRED_TAGS) -> TagGapReport` | A resource is incomplete if it lacks ≥1 required tag. Which tags are missing is returned, not just the fact of a gap — US-04 needs the specifics to be actionable. |
| `evaluate_freshness` | `(collected_at: datetime, now: datetime, stale_after: timedelta) -> Freshness` | `now` injected (Q8 = A: server-side judgement, testable without waiting). |
| `_reference_group_by_tag` | `(s: Snapshot, tag_key: str) -> GroupingResult` | Naive reference implementation, test-only. The oracle for the oracle property. |

**Properties owned here** (PBT §4.2)
- Invariant: `sum(len(g.resources) for g in r.groups) == r.total == len(s.resources)`
- Invariant: every resource appears in exactly one group
- Oracle: `group_by_tag == _reference_group_by_tag`
- Idempotence: regrouping an already-grouped set by the same key is a no-op
- Easy verification: a record is in `incomplete` **iff** `set(REQUIRED_TAGS) - record.tags.keys()` is
  non-empty. Trivially checkable per record, hard to get wrong across a generated corpus.

`stale_after` is passed in rather than read from config here, so the threshold stays a stack
parameter (FR-2.3 family) and this module stays environment-free.

---

## C-01 — Tag Inventory Collector

```python
@dataclass(frozen=True)
class CollectionResult:
    records: tuple[ResourceRecord, ...]
    pages_fetched: int
```

| Method | Signature | Notes |
|---|---|---|
| `handler` | `(event: dict, context) -> None` | Entry point. Returns nothing; success is the written object. |
| `collect_all_resources` | `(client, page_limit: int) -> CollectionResult` | Paginates to exhaustion. **Raises** if the token sequence ends abnormally or `page_limit` is hit — a partial result is never returned as success (FR-1.1, US-02). |
| `write_snapshot` | `(client, bucket: str, key: str, body: bytes) -> None` | Single `PutObject`. No read-modify-write, so no lost-update window. |
| `emit_metrics` | `(result: CollectionResult, duration_s: float) -> None` | Custom metrics for US-14 / RESILIENCY-05. |

**`page_limit` exists because unbounded pagination is unbounded runtime and unbounded cost.** It is a
guard rail whose breach is an error, not a truncation — the distinction that keeps FR-1.1 honest.

**Control flow on failure**: log structured, emit the failure metric, raise. The Lambda invocation
fails, the alarm fires (US-13), and the **previous snapshot is left intact** — a stale-but-complete
snapshot beats a fresh-but-partial one, and the UI can tell the user it is stale (US-05).

---

## C-03 — Inventory Read API

```python
class SnapshotState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"           # collector has never successfully run
    UNREADABLE = "unreadable"   # object exists but does not parse

@dataclass(frozen=True)
class LoadOutcome:
    state: SnapshotState
    snapshot: Snapshot | None
```

| Method | Signature | Notes |
|---|---|---|
| `handler` | `(event: dict, context) -> dict` | API Gateway proxy in, proxy response out. |
| `load_current_snapshot` | `(client, bucket: str, key: str) -> LoadOutcome` | **Distinguishes absent from unreadable.** A bare try/except collapses them, and US-06 requires them to look different to the user. |
| `route` | `(method: str, path: str) -> Handler \| None` | Explicit table (Q5 = A). Unmatched → 404 without touching S3. |
| `respond` | `(http_status: int, body_status: str, payload: Mapping) -> dict` | The single response shaper (Q8 = A: status code **and** body field, never one without the other). |
| `health` | `() -> dict` | Static 200. Does **not** read S3, so it stays green when data is missing — it reports whether the function is alive, not whether the data is good (Q6 = A). |

### Route table (Q5 = A)

| Path | Returns | Derivation |
|---|---|---|
| `GET /api/inventory` | full resource list | none (raw snapshot) |
| `GET /api/groups/{tag_key}` | one grouping | `group_by_tag`; `tag_key` validated against `REQUIRED_TAGS` |
| `GET /api/tag-gaps` | the gap report | `classify_tag_gaps` |
| `GET /api/status` | freshness + state | `evaluate_freshness` |
| `GET /api/health` | liveness | none |

`{tag_key}` is the only user-supplied value the API accepts, and it is validated against a closed
allowlist. That is the whole of the input surface — which is why Q5 = A makes SECURITY-05 nearly
structural rather than a validation layer to be written and maintained.

### The four states, mapped concretely

This table is the reason `LoadOutcome` is a three-state type rather than a boolean.

| Situation | HTTP | `status` in body | UI shows |
|---|---|---|---|
| Snapshot present, fresh | 200 | `ok` | data |
| Snapshot present, stale | 200 | `stale` | data + prominent staleness notice |
| Snapshot absent | 200 | `no_data` | "no data collected yet" — **not** an empty table |
| Snapshot unreadable | 503 | `error` | generic failure, no internals (FR-3.4) |
| Snapshot present, zero resources | 200 | `ok` | "no tagged resources found" — **not** the same as `no_data` |

The last two rows are the point of US-06. "Nothing collected" and "nothing to collect" render
identically under a naive implementation and mean opposite things.

`no_data` is 200, not 404: the request succeeded and the answer is "there is no snapshot yet." A 404
would suggest the endpoint is wrong.

---

## C-06 — Web UI

Not method-level specified here — component structure is Functional Design's business. The
obligations that must survive into implementation:

| Obligation | Source |
|---|---|
| Render all five rows of the state table distinguishably | US-06, FR-3.3 |
| Show `collected_at` on every view that shows data | US-05, FR-2.2 |
| Never construct a request path from unvalidated input | SECURITY-05 |
| No inline scripts, no `eval` — configure Vite's modulepreload polyfill off | US-01, SECURITY-11 |
| No third-party origins in the built output | SECURITY-14 |
| Show the WAF-block case usefully if reachable | FR-5.4 |

---

## What no component does

Stated because their absence is a design decision, and an implementer filling a perceived gap would
break a requirement.

- **No write path from the UI.** The dashboard is read-only (FR-4.5, `personas.md`).
- **No on-demand collection trigger.** Not exposed anywhere (FR-2.1, US-07). A "refresh" button that
  re-collects would let any allowlisted viewer drive Tagging API cost and throttling.
- **No cross-account or cross-region assumption.** Single account, `us-east-1` (§5).
- **No cost computation.** FR-8 / US-D1 / US-D2 are deferred with the data source undecided.
- **No user, session, or identity handling.** No Cognito, no tokens (FR-5.5).
