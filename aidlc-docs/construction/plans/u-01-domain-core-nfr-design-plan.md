# NFR Design Plan — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Design
**Date**: 2026-08-03
**Unit**: U-01 Domain Core
**Inputs**: `construction/u-01-domain-core/nfr-requirements/` (approved 2026-08-03) ·
`functional-design/` (approved) · amendments A1–A3

---

## What this stage can and cannot mean for U-01

NFR Design's mandated categories are **resilience patterns, scalability patterns, performance patterns,
security patterns, and logical components** — where "logical components" the rules illustrate as "queues,
caches, circuit breakers."

U-01 has none of those and will have none. It is a set of pure functions with no I/O, no network, no
clock, no state, and no runtime dependency. There is no fault to tolerate, nothing to retry, no load to
shed, and no component to insert. Inventing a circuit breaker for a function call would be worse than
useless — it would add the state this unit's entire value proposition is the absence of.

So this stage does two real things for U-01:

1. **Decides the internal design patterns that make the NFR requirements hold** — how immutability is
   *enforced* rather than documented, how errors are typed, and what the public surface is. These are the
   design decisions that determine whether NFR-M1, NFR-S1 and the equality-based properties are structural
   or merely intended.
2. **Settles RESILIENCY-04, -14 and -15**, which were deferred to "NFR Design" at Requirements Analysis
   and are now due. Q5 and Q6 below handle them — including, honestly, the question of whether two of the
   three belong to this unit at all.

Part A1 records the categories that are genuinely inapplicable, with reasons.

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

---

### Question 1 — How is immutability *enforced*, not just documented?

`ResourceRecord.tags` is typed `Mapping[str, str]`. A `Mapping` type annotation is a promise, not a
guarantee: if the runtime object is a plain `dict`, any caller can mutate it in place.

This matters more here than it usually would. **P1, P2 and P6 are equality assertions**, and P2 requires
that equal snapshots serialize to identical bytes. A caller that mutates `record.tags` after construction
silently invalidates all three — and the corruption would appear as a flaky property failure rather than as
an error at the mutation site, which is the worst possible failure signature.

**A) Wrap in `MappingProxyType` at construction** ← *recommended*
   `__post_init__` replaces the incoming mapping with a read-only view. Mutation attempts raise
   `TypeError` at the point of the mistake.
   *Why*: standard library, no dependency, no custom class to test, and it converts a documentation promise
   into a runtime one. The frozen dataclass already handles field rebinding; this closes the one hole left.
   *Cost*: `MappingProxyType` is not hashable, so `ResourceRecord` cannot be hashed unless the tags are
   converted to a `frozenset` of items for hashing. Relevant to Q2.

**B) Plain `dict` plus a docstring** saying "do not mutate."
   *Why*: simplest; nothing in this codebase would mutate it.
   *Cost*: relies on every future caller — including U-02's collector and API — reading and honouring a
   comment. The failure is silent and shows up as a flaky test.

**C) A custom frozen mapping type** — hashable and immutable.
   *Why*: gets both immutability and hashability.
   *Cost*: a hand-written container is code that can be wrong, and it becomes part of U-01's public surface
   that U-02 must then understand.

X) Other

[Answer]:A

---

### Question 2 — Is U-01 hashable, and does it memoize anything?

Two related questions, because the answer to one constrains the other.

**Memoization**: `group_by_tag` on the same snapshot and key always returns the same result, so it is
cacheable in principle. But per Q5 = A of the Application Design each API path derives **one** view, so
there is nothing to memoize *within* a request; and caching *across* requests is U-02's decision, where the
design already specifies `/api/*` as no-cache.

**Hashability** matters independently: if `Snapshot` and `ResourceRecord` are hashable, U-02 *could* cache
on them later without U-01 changing. If they are not, that option is closed off.

**A) No memoization in U-01; make the types hashable anyway** ← *recommended*
   U-01 stays stateless. Hashability is provided (tags hashed as a `frozenset` of items) so U-02 retains the
   option.
   *Why*: memoization inside U-01 would introduce the one thing this unit exists not to have — state — and
   would make P2's determinism assertion depend on cache state rather than input. Hashability costs a few
   lines and keeps a door open that is expensive to reopen later.
   *Cost*: a custom `__hash__` alongside Q1 = A's `MappingProxyType`, and it must agree with `__eq__` or the
   equality-based properties break in a new way.

**B) No memoization, not hashable** — the minimum.
   *Why*: least code; nothing needs hashing today.
   *Cost*: if U-02 later wants to cache a derived view keyed by snapshot, U-01 has to change.

**C) Memoize derived views inside U-01** (e.g. `functools.lru_cache` on grouping).
   *Cost*: introduces state, makes determinism cache-dependent, and requires hashable inputs anyway. Also
   caches nothing useful, since each request derives one view.

X) Other

[Answer]:A

---

### Question 3 — What is U-01's error type design?

NFR-S1 fixes the *content* (category only, never a tag value or ARN). This is about the *shape* U-02 catches.

**A) A small hierarchy under one base** ← *recommended*
```
CoreError                      (base — U-02 can catch everything with one except)
  MalformedResource(category)  BR-02; category ∈ {"arn", "tags"}
  IncompatibleSchema           BR-08 major-version mismatch
  InvalidSnapshot              BR-08 malformed JSON, naive datetime, P8 violation
```
   *Why*: U-02 needs to distinguish these — a malformed *resource* is skipped and counted, whereas an
   incompatible *schema* means the whole snapshot is unreadable and must become a 503. Those are different
   HTTP outcomes, so they must be different types rather than one type inspected by string.
   *Cost*: four classes instead of one.

**B) One exception type carrying a category enum** — `CoreError(category=...)`.
   *Cost*: U-02 branches on an attribute rather than on `except`, which is easy to get wrong and impossible
   for a type checker to help with.

**C) Built-in exceptions** (`ValueError`, `TypeError`).
   *Cost*: indistinguishable from bugs originating anywhere else, including inside the standard library.

X) Other

[Answer]:A

---

### Question 4 — What is the public surface U-02 imports?

`dashboard.core` contains two logical modules (the model and the aggregation logic). U-02 needs both.

**A) A flat public API re-exported from `dashboard.core`** ← *recommended*
   `from dashboard.core import Snapshot, group_by_tag, classify_tag_gaps, evaluate_freshness, ...`, with
   `__all__` declaring the surface and internal module layout free to change.
   *Why*: makes the boundary explicit and reviewable — `__all__` *is* the contract, so a reviewer can see in
   one place what U-02 is allowed to depend on. Also means the `core/` internal file layout can be
   reorganized without touching U-02.
   *Cost*: one more file to keep in step; a new public function must be added to `__all__` deliberately,
   which is the point.

**B) U-02 imports from submodules directly** — `from dashboard.core.aggregation import group_by_tag`.
   *Cost*: couples U-02 to U-01's internal file layout, so moving a function is a breaking change across a
   unit boundary.

X) Other

[Answer]:A

---

### Question 5 — RESILIENCY-14: is the property suite the resiliency test for U-01?

Deferred to this stage at Requirements Analysis. For a pure library, "resiliency testing" can only mean
adversarial input — there is no network to partition, no dependency to fail, no instance to kill.

The ten properties plus the eight generator shapes already cover malformed ARNs, empty and whitespace tag
values, wrong-case keys, duplicate ARNs, non-normalizable items mixed with valid ones, and out-of-order
timestamps.

**A) Yes — the property suite *is* the resiliency test, recorded as such** ← *recommended*
   *Why*: property-based testing with adversarial generators is a stronger robustness check than a
   hand-written fault-injection suite would be, because Hypothesis shrinks to a minimal counterexample
   rather than reporting one hand-picked case. Declaring it satisfied here — rather than leaving
   RESILIENCY-14 open or inventing a second suite — is the honest reading.
   *Cost*: none identified, provided the generators actually cover the eight shapes (NFR-T7, review-only).

**B) Add a separate adversarial-input suite** — deliberately hostile inputs beyond what generators produce
   (enormous tag values, deeply pathological Unicode, 10⁶ tags on one resource).
   *Why*: generators produce *plausible* inputs; an attacker or a broken upstream produces implausible ones.
   *Cost*: a second suite with overlapping coverage, and the inputs come from AWS rather than a user.

**C) Defer RESILIENCY-14 to U-02** — treat resiliency testing as a whole-system concern.
   *Cost*: U-01's robustness is exactly what property testing is for; deferring it wastes the one place
   where the technique fits best.

X) Other

[Answer]:A

---

### Question 6 — RESILIENCY-04 and -15 landed here. Do they belong to this unit?

Both were deferred to "NFR Design" at Requirements Analysis, and this is the first NFR Design pass — so
they arrive now by the letter of the deferral. But:

- **RESILIENCY-04** — CI/CD tooling, **rollback mechanism**, deployment style. U-01 is not deployed. It is
  code inside two images that U-02 builds and deploys; rollback means redeploying an earlier digest.
- **RESILIENCY-15** — **incident response process**. U-01 has no incident surface: it emits no logs
  (NFR-S6), raises no alarms, and cannot be paged about independently of the Lambdas containing it.

I am not deciding this silently, because re-deferring a deferral without saying so is how a requirement
quietly never gets answered.

**A) Route both to U-02's NFR Design; record the routing explicitly** ← *recommended*
   *Why*: both are genuinely properties of the deployable, and U-02 is the deployable. Answering them here
   would produce statements about a unit that cannot enact them.
   *Cost*: they remain open for one more stage. Mitigated by recording them in `aidlc-state.md` as
   **assigned to U-02's NFR Design** rather than as generically "deferred", so the second pass inherits a
   named obligation.

**B) Answer them now at whole-system level**, in U-01's NFR Design, even though U-01 cannot enact them.
   *Why*: closes them sooner; the answers are not unit-specific.
   *Cost*: puts system-level deployment and incident-response decisions in a document about a pure library,
   where nobody working on U-02 will look for them.

**C) Answer RESILIENCY-04 now, route -15 to U-02** — rollback interacts with the digest-pinning already
   designed, so it is nearly decided.
   *Cost*: splits a pair that was deferred together.

X) Other

[Answer]:A

---

## Part A1 — Categories evaluated and NOT asked about

| Mandated category | Why inapplicable to U-01 |
|---|---|
| **Resilience patterns** — retries, backoff, circuit breakers, bulkheads, timeouts, fallbacks | Every one presupposes a call that can fail slowly or transiently. U-01 makes no calls: no network, no disk, no subprocess. Its only failure mode is a rejected input, which is deterministic and immediate. Retrying a pure function with the same input returns the same result. RESILIENCY-10's timeouts and bounded retries apply to C-01/C-03 and are **U-02's**. |
| **Scalability patterns** — sharding, partitioning, autoscaling, queues, load shedding | U-01 runs inside its caller's process and has no independent load. Scaling the dashboard means scaling Lambda concurrency, which is U-02's (RESILIENCY-09). The only scale dimension U-01 has is input size, already bounded by NFR-P1/P2. |
| **Caching / CDN patterns** | Covered by Q2, and the answer is expected to be "not in U-01." Response caching is C-07's, where the design already fixes `/api/*` as no-cache. |
| **Infrastructure logical components** — queues, caches, circuit breakers, service meshes, load balancers | U-01 introduces **zero** infrastructure. Its `logical-components.md` will describe internal logical structure (modules, error types, the public surface) rather than infrastructure, and will say so explicitly rather than leaving a reader to wonder why the queues section is missing. |
| **Availability patterns** — multi-AZ, failover, health checks, graceful degradation | A library has no availability. Graceful degradation *is* designed — the skip-and-count behaviour of BR-02 — but it is a business rule already decided at Functional Design, not a pattern to choose here. |
| **Security patterns** — authn, authz, encryption, secrets, network isolation | No identity, no storage, no network, no secret. The security requirements U-01 *does* have (NFR-S1..S6) are content and parsing rules, already decided; Q1 and Q3 cover the two with a design dimension left. |
| **Observability patterns** | NFR-S6 forbids U-01 emitting anything. Deliberate: logging is U-02's, at a boundary where retention and access are configurable. |
| **Performance patterns** — connection pooling, lazy loading, batching, pagination | All concern I/O U-01 does not perform. Pagination is C-01's. The one real performance dimension is algorithmic complexity, fixed by NFR-P1..P4. |

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] Confirm all six `[Answer]:` tags are filled
- [x] Run the Step 5 analysis for vagueness, contradiction, and option-merging; raise follow-ups rather
      than proceeding if any is found
- [x] Record resolved decisions and interactions in a `Part A2` section
- [x] If Q6 ≠ B, record RESILIENCY-04/-15 in `aidlc-state.md` as **assigned to U-02's NFR Design** with
      that wording, not as generically deferred

### B2. `nfr-design-patterns.md`
- [x] The patterns U-01 **does** use, named and justified: immutable value objects, pure functions with
      injected dependencies (clock, threshold), total-function-wrapping-partial (`normalize_all` over
      `normalize_resource`), discriminated result (`Freshness`, `LoadOutcome`), test oracle, and
      closed-allowlist validation
- [x] For each: which NFR requirement it satisfies, and how it would be visible in review
- [x] The Q1 immutability enforcement mechanism and its interaction with Q2's hashability
- [x] The Q3 error hierarchy, with the mapping from error type → U-02's HTTP outcome
- [x] **Every Part A1 category marked N/A with its reason**, so the artifact does not read as though
      resilience and scalability were forgotten
- [x] RESILIENCY-14's disposition per Q5, stated as a decision rather than an assumption

### B3. `logical-components.md`
- [x] State plainly that U-01 contributes **no infrastructure components**, and why
- [x] Internal logical structure: module boundaries inside `dashboard.core`, the `__all__` surface (Q4),
      and the error types (Q3)
- [x] The dependency direction inside the unit (aggregation → model, never the reverse)
- [x] The U-01 ↔ U-02 interface as U-02 will see it: exactly what is importable and what is not
- [x] The enforceable boundary check (no `boto3`, no `os`, no `datetime.now()` under
      `src/dashboard/core/`) and where it runs

### B4. Validation and honest reporting
- [x] Every pattern traces to an NFR requirement; no pattern included because it is conventional
- [x] No pattern introduces state, I/O, a clock read, or a dependency into `core/`
- [x] Confirm consistency with the ten properties — in particular that Q1 and Q2 together do not break
      `__eq__`/`__hash__` agreement, which three properties depend on
- [x] Report anything unsettled with the stage that carries it

### B5. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 🎨 NFR Design Complete - U-01 Domain Core` and wait for explicit approval

---

## Part A2 — Resolved decisions (Q1–Q6)

Step 5 analysis. All six clean single selections, all **A**, no vagueness, contradiction or
option-merging. No blocking follow-up. Six interactions, two of which are **concrete implementation traps
that Q1 = A and Q2 = A create together** and one of which **weakens a claim I made in Q5**.

| # | Decision | Answer |
|---|---|---|
| Q1 | Immutability | `MappingProxyType` at construction |
| Q2 | Hash / memoize | Hashable; **no** memoization |
| Q3 | Errors | Hierarchy under a `CoreError` base |
| Q4 | Public surface | Flat `__all__` re-export from `dashboard.core` |
| Q5 | RESILIENCY-14 | The property suite **is** the resiliency test |
| Q6 | RESILIENCY-04, -15 | Routed to U-02's NFR Design, recorded as **assigned** |

### Interaction 1 — Q1 = A and Q2 = A collide on the dataclass-generated `__hash__`

Q1's cost note said `MappingProxyType` is unhashable and that hashing would need a `frozenset` of items.
Working that through produces a hard requirement, not a preference:

A `@dataclass(frozen=True, eq=True)` **auto-generates `__hash__`** from the tuple of its fields. That
generated hash would call `hash()` on a `MappingProxyType` and raise `TypeError` at first use. So:

> `ResourceRecord` MUST declare `eq=True, frozen=True` **and provide an explicit `__hash__`** that hashes
> tags as `frozenset(self.tags.items())`. Relying on the generated one is a runtime failure, not a style
> choice.

The hash/eq contract holds: `MappingProxyType` compares by content (`mappingproxy({'a':'b'}) == {'a':'b'}`
is `True`), so dataclass-generated `__eq__` is correct as-is, and a content-based hash agrees with it.
**That agreement is what three properties depend on** — if `__hash__` disagreed with `__eq__`, P1, P2 and
P6 would fail in a way that looks like a serialization bug.

Second trap, same territory: **`__post_init__` cannot assign to a frozen dataclass** with normal
attribute syntax. Wrapping the mapping requires `object.__setattr__(self, "tags", MappingProxyType(dict(tags)))`.
The `dict()` copy is also required — wrapping a caller's dict without copying leaves the caller holding a
mutable reference to the "immutable" object's contents, which defeats the entire point of Q1 = A.

### Interaction 2 — Q1 = A's text named only `tags`, but `Snapshot` has a Mapping too

Q1 asked about `ResourceRecord.tags`. `Snapshot.skipped_reasons` is also a `Mapping[str, int]` and has
exactly the same exposure: mutable after construction, and unhashable once wrapped.

**Extended:** the same treatment applies to `Snapshot.skipped_reasons` — copy, wrap, and include in the
custom `__hash__`. Recorded as an extension of Q1 = A rather than a new decision, because the reasoning is
identical and applying it to one field but not the other would be arbitrary. My question text was narrower
than the problem.

### Interaction 3 — `assert` is the wrong mechanism for P8, and Q3 = A gives the right one

`business-logic-model.md` wrote P8's accounting identity as `assert ...` in both `build_snapshot` and
`deserialize_snapshot`. **`assert` statements are removed entirely under `python -O`.** NFR-R3 requires
P8 to be checked on deserialization, which is a production read path inside a Lambda — so an invariant
that vanishes under an optimization flag is not an invariant.

Q3 = A supplies the fix: **`InvalidSnapshot` raised explicitly**, never `assert`. Recorded as a design
requirement rather than an implementation note, because the two places it matters are exactly the two
places NFR-R3 names.

This does not change P8 or NFR-R3 — it changes the mechanism from one that can be compiled away to one
that cannot.

### Interaction 4 — Q3 = A and Q4 = A compose: the error types are part of the public surface

U-02 catches these, so `CoreError`, `MalformedResource`, `IncompatibleSchema` and `InvalidSnapshot` all
belong in `__all__`. Stating it because an `__all__` containing only functions and types — and omitting the
exceptions U-02 must catch — is an easy and silent omission that would push U-02 toward
`except Exception`.

### Interaction 5 — Q5 = A discharges a blocking rule using a review-only requirement

RESILIENCY-14 is a blocking rule. Q5 = A satisfies it with the property suite, and that satisfaction is
only as good as the generators actually covering the eight shapes listed in `business-logic-model.md` —
which is **NFR-T7, classified review-only** in `nfr-requirements.md`.

So a blocking resiliency rule is now discharged by something **no tool checks**. That is not an argument
against Q5 = A: a hand-written fault-injection suite would be discharged by review too, and would cover
less. But the claim is weaker than "RESILIENCY-14: satisfied" looks, and it should be recorded at its real
strength rather than at its stated one.

Practical consequence: NFR-T7 and NFR-T5 are now the **two** review-only requirements carrying
disproportionate weight — T5 because a copied oracle makes P5 a tautology, T7 because thin generators make
RESILIENCY-14 hollow. Both are things only a person reading the test file will catch.

### Interaction 6 — Q6 = A: this is the second deferral, and the count is now recorded

RESILIENCY-04 and -15 were deferred once (Requirements Analysis → NFR Design) and are now deferred again
(U-01 NFR Design → U-02 NFR Design). Recorded in `aidlc-state.md` as **"assigned to U-02's NFR Design"**
with the deferral count, so a third would be visible as a pattern rather than looking like a first.

The routing is right — U-01 has no deployment to roll back and no incident surface — but the *number of
times a blocking rule has been moved* is the thing worth tracking, not just its current owner.

**Nothing else changed.** No property, requirement, entity or business rule was modified by this stage; the
ten properties stand, and the 26 NFR requirements stand.
