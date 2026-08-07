# NFR Design Patterns — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Design (artifact 1 of 2)
**Date**: 2026-08-03
**Decisions**: `construction/plans/u-01-domain-core-nfr-design-plan.md` Part A2 (Q1–Q6, all A)

Patterns U-01 **does** use, each tied to the NFR requirement it satisfies and to how a reviewer would see
it. Patterns U-01 does not use are listed at the end with reasons, because eight of this stage's mandated
categories are inapplicable and their absence should read as a decision.

---

## PAT-1 — Immutable value object, enforced at construction

**Satisfies**: NFR-M6, and structurally protects P1, P2, P6.

`ResourceRecord` and `Snapshot` are `@dataclass(frozen=True, eq=True)`. Frozen handles field *rebinding*.
It does **not** stop mutation of a mutable field's contents, which is the actual exposure — so every
`Mapping` field is copied and wrapped in `MappingProxyType` in `__post_init__`.

**Fields requiring this treatment**: `ResourceRecord.tags` **and** `Snapshot.skipped_reasons`. Q1's text
named only the first; the second has identical exposure (Part A2 Interaction 2).

```python
object.__setattr__(self, "tags", MappingProxyType(dict(tags)))
```

**Two details that are requirements, not idiom:**

- **`object.__setattr__` is mandatory.** A frozen dataclass rejects normal attribute assignment in
  `__post_init__`.
- **The `dict()` copy is mandatory.** Wrapping the caller's mapping without copying leaves the caller
  holding a mutable reference to the contents of a supposedly immutable object — which defeats the whole
  pattern while appearing to implement it.

**Why this is a pattern and not a nicety**: P1, P2 and P6 are equality assertions. A caller mutating
`record.tags` after construction invalidates all three, and it surfaces as a **flaky property failure**
rather than an error at the mutation site. Enforcement converts that class of bug into an immediate
`TypeError` at the offending line.

**Visible in review as**: `frozen=True` on both dataclasses, a `__post_init__` that wraps every Mapping
field, and no Mapping field left as a bare `dict`.

---

## PAT-2 — Content-based hashing, agreeing with equality

**Satisfies**: Q2 = A (keep U-02's caching option open) without introducing state.

`MappingProxyType` is unhashable, and `@dataclass(frozen=True, eq=True)` **auto-generates a `__hash__`**
from the field tuple — which would call `hash()` on the proxy and raise `TypeError` on first use. So an
explicit `__hash__` is required:

```python
def __hash__(self) -> int:
    return hash((self.arn, self.service, self.resource_type,
                 self.region, frozenset(self.tags.items())))
```

**The hash/eq contract holds and must be checked**, because three properties rest on it.
`MappingProxyType` compares by content, so the generated `__eq__` is correct unchanged, and a
content-based hash agrees with it. If the two disagreed, P1, P2 and P6 would fail in a way that reads as a
serialization bug rather than a hashing bug — which is why the agreement is called out here rather than
left to be discovered.

**Deliberately absent: memoization.** No `lru_cache`, no cached property, no internal store. Per Q5 = A of
the Application Design each API path derives exactly one view, so there is nothing to memoize within a
request; and caching across requests is U-02's, where `/api/*` is already specified no-cache. Memoization
would also make P2's determinism assertion depend on cache state rather than on input.

---

## PAT-3 — Total function wrapping a partial one

**Satisfies**: NFR-R2, and it is Q1 = A of Functional Design expressed as structure.

`normalize_resource` is **partial** — it raises `MalformedResource` on unparseable input.
`normalize_all` is **total** — it catches, counts, and continues.

The collector only ever calls `normalize_all`. So the function U-02 depends on **cannot fail on a malformed
item**, which is what makes one bad ARN unable to take down a snapshot. The failure is converted to data
(`skipped_count`, `skipped_reasons`) at the boundary between the two.

**Visible in review as**: a `try/except MalformedResource` inside `normalize_all`'s loop, and no
`except` around it anywhere in U-02.

---

## PAT-4 — Explicit invariant checks, never `assert`

**Satisfies**: NFR-R3, and closes a hole in the functional design's pseudocode.

`business-logic-model.md` wrote P8's accounting identity as `assert`. **`assert` is stripped entirely under
`python -O`**, and NFR-R3 requires P8 to be checked on deserialization — a production read path inside a
Lambda. An invariant that disappears under an optimization flag is not an invariant.

> P8 is enforced by an explicit `if ...: raise InvalidSnapshot(...)` in both `build_snapshot` and
> `deserialize_snapshot`. No `assert` in any non-test module.

This changes the mechanism, not the requirement (Part A2 Interaction 3).

**Visible in review as**: zero `assert` statements under `src/dashboard/core/`. Grep-able, and worth adding
to the boundary check that already looks for `boto3`, `os` and `datetime.now()`.

---

## PAT-5 — Discriminated result instead of an exception or a sentinel

**Satisfies**: US-06, BR-07, NFR-R2.

`evaluate_freshness` returns `Freshness` — `FRESH | STALE | INVALID` — rather than raising on a future
timestamp or returning `None`.

**Why**: it keeps `evaluate_freshness` total. A provenance fault on the read path becomes a *value* U-02
maps to a deliberate 503, instead of an exception that becomes an unexplained 500. The three states are
exhaustive, so mypy strict (NFR-M2) can check that U-02 handles all of them.

The same shape appears in U-02's `LoadOutcome` (`PRESENT | ABSENT | UNREADABLE`), which is why US-06's four
distinguishable states are representable at all.

---

## PAT-6 — Injected dependency for everything ambient

**Satisfies**: NFR-M6, NFR-M1, and it is what makes BR-07 testable.

`now` and `stale_after` are **parameters**. There is no clock read, no environment read, no config lookup
anywhere in U-01.

**Why**: it is what allows staleness — a *server-side* judgement per Q8 = A of the Application Design — to
be tested without waiting for time to pass, and it is what P10 (monotonicity in `now`) requires to be
assertable at all.

**Visible in review as**: the grep in `tools/check` finding no `datetime.now()`, `utcnow()`, `time.time()`,
or `os.environ` under `src/dashboard/core/`.

---

## PAT-7 — Error hierarchy mapping to caller outcomes

**Satisfies**: NFR-S1, and gives U-02 what it needs to produce the right HTTP status.

```
CoreError                       base — U-02 can catch all of U-01 with one except
├── MalformedResource(category) one item unusable  → skip + count      (BR-02)
├── IncompatibleSchema          whole snapshot unreadable → 503        (BR-08)
└── InvalidSnapshot             malformed JSON / naive datetime / P8   → 503
```

**Why a hierarchy rather than one type with a category attribute**: these produce **different HTTP
outcomes**. A malformed resource is absorbed and counted; an incompatible schema means there is no usable
snapshot at all. Distinguishing by `except` is checkable by a type checker; distinguishing by inspecting a
string attribute is not.

**Content rule (NFR-S1)**: every one of these carries a **category only** — no ARN, no tag key, no tag
value, no input index. `cornell:owner` holds a NetID, and an exception message can reach a log group or an
error body. Making the rule structural means it does not depend on every future exception message being
written carefully.

**Consequence for U-02**: nothing in U-01 can say *which* resource was malformed. C-01 must log that at its
own boundary, where it can decide what is safe to emit. Recorded as a cross-unit obligation.

---

## PAT-8 — Closed-allowlist validation

**Satisfies**: NFR-S3, SECURITY-05, and it is why U-02's input surface is nearly structural.

- `group_by_tag` rejects any `tag_key` not in `REQUIRED_TAGS` — a fixed four-element tuple.
- ARN parsing is `str.split(":", 5)` with explicit arity and emptiness checks. **No regular expression.**

**Why split, not regex**: an ARN is a fixed six-field colon-delimited grammar, so a regex adds a
backtracking surface for no functional gain, and a permissive pattern would silently accept malformed ARNs
that a split-plus-check rejects — and rejecting them is what feeds `skipped_reasons`. ARNs currently arrive
from AWS rather than a user, but "the input is trusted" is a property that erodes.

---

## PAT-9 — Independent test oracle

**Satisfies**: P5, NFR-T5.

`_reference_group_by_tag` is a deliberately naive quadratic implementation, used only as P5's oracle.

**It must be written independently.** If it is produced by copying `group_by_tag`, P5 becomes a tautology
that passes forever while asserting nothing. **No tool can detect this** — it is the single review-only
requirement in this unit whose failure is silent and permanent (NFR-T5).

Excluded from NFR-P2's 10,000-record check: running a quadratic reference at that size would measure the
test double rather than the implementation.

---

## RESILIENCY-14 — satisfied by the property suite, at its real strength

**Q5 = A**: for a unit with no network, no dependency and no instance, "resiliency testing" can only mean
adversarial input. The ten properties plus the eight generator shapes cover malformed ARNs, empty and
whitespace-only tag values, wrong-case keys, duplicate ARNs, non-normalizable items mixed with valid ones,
timestamps before/equal/after `now`, zero-resource snapshots, and snapshots carrying an unrecognized
top-level key.

Hypothesis shrinking to a minimal counterexample makes this stronger than a hand-written fault-injection
suite, which would test hand-picked cases.

**Recorded at its real strength, not its stated one**: RESILIENCY-14 is a *blocking* rule, and this
satisfaction depends on the generators genuinely covering those eight shapes — which is **NFR-T7,
review-only**. So a blocking rule is discharged by something no tool checks. That is not an argument
against Q5 = A (a fault-injection suite would also be discharged by review, and would cover less), but the
claim is weaker than a bare "satisfied" implies.

**NFR-T5 and NFR-T7 are therefore the two review-only requirements carrying disproportionate weight** — T5
because a copied oracle makes P5 vacuous, T7 because thin generators make RESILIENCY-14 hollow. Both are
visible only to a person reading the test file.

## RESILIENCY-04 and RESILIENCY-15 — assigned to U-02's NFR Design

**Q6 = A.** Both concern a deployable, and U-01 is not one: rollback means redeploying an earlier image
digest, and U-01 has no incident surface because it emits nothing (NFR-S6) and cannot be paged
independently of the Lambdas containing it.

**This is their second deferral** (Requirements Analysis → NFR Design → U-02's NFR Design). Recorded in
`aidlc-state.md` as *assigned to U-02's NFR Design* with the deferral count, so a third would be visible as
a pattern rather than looking like a first.

---

## Patterns deliberately NOT used

| Pattern family | Why not |
|---|---|
| Retry, backoff, circuit breaker, bulkhead, timeout, fallback | All presuppose a call that can fail transiently or slowly. U-01 makes no calls — no network, no disk, no subprocess. Its only failure is a rejected input: deterministic and immediate. Retrying a pure function with the same input returns the same result. RESILIENCY-10's timeouts and bounded retries are **U-02's**, on C-01 and C-03. |
| Sharding, partitioning, autoscaling, queueing, load shedding | U-01 has no independent load; it runs in its caller's process. Scaling the dashboard means Lambda concurrency (RESILIENCY-09) — **U-02's**. |
| Caching, CDN, read-through, write-behind | Q2 = A: none in U-01. Response caching is C-07's, where `/api/*` is already no-cache — and inverting that is the specific failure US-05 exists to prevent. |
| Multi-AZ, failover, health check, leader election | A library has no availability. Graceful degradation **is** designed — BR-02's skip-and-count — but as a business rule decided at Functional Design, not a pattern chosen here. |
| Authn, authz, encryption, secret management, network isolation | No identity, storage, network or secret anywhere in U-01. FR-5.5 removes identity from the whole design. |
| Structured logging, metrics, tracing, correlation IDs | NFR-S6 forbids U-01 emitting anything. Deliberate: logging belongs at U-02's boundary where retention and access are configurable, and where it can decide what is safe to write. |
| Connection pooling, lazy loading, batching, pagination | All concern I/O U-01 does not perform. Pagination is C-01's. U-01's only performance dimension is algorithmic complexity, fixed by NFR-P1..P4. |
| Saga, event sourcing, CQRS, outbox | No transactions, no events, no writes. The read/write split already exists at the service level (S-01/S-02) and needs no pattern inside a pure library. |

---

## Consistency check against the ten properties

| Concern | Result |
|---|---|
| `__eq__` / `__hash__` agreement (PAT-1, PAT-2) | **Holds** — `MappingProxyType` compares by content; hash uses `frozenset(items)`. P1, P2, P6 depend on this. |
| Does any pattern introduce state? | **No.** Memoization explicitly rejected. |
| Does any pattern introduce I/O, a clock, or a dependency? | **No.** PAT-6 keeps everything ambient injected. |
| Does PAT-4 change P8? | **No** — same invariant, a mechanism that survives `python -O`. |
| Does PAT-1's copy affect determinism (P2)? | **No** — `dict()` preserves insertion order, and serialization sorts keys anyway. |
| Property count | **Unchanged at ten.** This stage added no properties and removed none. |
