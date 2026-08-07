# NFR Requirements — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Requirements (artifact 1 of 2)
**Date**: 2026-08-03
**Decisions**: `construction/plans/u-01-domain-core-nfr-requirements-plan.md` Part A2 (Q1–Q8, all A)

Every requirement has an ID, a source, and a **verification column** — because an NFR nothing checks is
an aspiration, and this artifact should make the difference visible rather than uniform.

---

## Performance

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| NFR-P1 | `normalize_all`, `group_by_tag`, `classify_tag_gaps` and both serialization functions MUST be **O(n)** in record count | Q8 | Review + NFR-P2 |
| NFR-P2 | Grouping and gap classification MUST complete over a **10,000-record** snapshot within a generous fixed bound | Q8 | **Automated** — one example-based test |
| NFR-P3 | `_reference_group_by_tag` is **exempt**; it is quadratic by design and runs only at small sizes | Q8, Part A2 Interaction 5 | Review |
| NFR-P4 | `evaluate_freshness` and `has_required_tag` MUST be O(1) | Q8 | Review |

**Why 10,000 when §4.4 says tens to low hundreds.** Two orders of magnitude of headroom costs nothing
here — the algorithms are already single-pass — and it converts "should be linear" into something
checked. An accidental O(n²) in grouping would pass all ten properties and surface only in production,
where the remedy is a data-model change rather than a U-01 change.

**NFR-P2 is deliberately not a latency budget.** Wall-clock assertions on shared CI are flaky, and flaky
gates teach people to retry rather than to look. The bound is generous enough that only a complexity
regression trips it.

---

## Maintainability

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| NFR-M1 | `src/dashboard/core/` MUST contain no `boto3`/`botocore` import, no `os` import, and no `datetime.now()` / `utcnow()` / `time.time()` call | §4.5, `unit-of-work.md` | **Automated** — grep in `tools/check` |
| NFR-M2 | The core package MUST type-check under **mypy strict** with zero errors and zero `# type: ignore` | Q4 | **Automated** — `tools/check` |
| NFR-M3 | mypy strict scope is the **core package only**; extending it to `collector/`/`api/` is a U-02 decision | Q4 | Review |
| NFR-M4 | Every public function MUST have a docstring naming the business rule (BR-xx) it implements | Maintainability | Review |
| NFR-M5 | Runtime dependencies of the core package MUST be **standard library only** | Q2, §4.5 | **Automated** — a dependency appearing there fails the boundary check |
| NFR-M6 | No public function may read configuration, environment, or a clock; all inputs are parameters | §4.5, BR-07 | NFR-M1 + review |

**NFR-M3 exists so the boundary is deliberate.** Strict mode is nearly free over frozen dataclasses and
pure functions, and expensive over boto3 response shapes — where it produces noise that gets silenced with
`# type: ignore`, which teaches people to ignore the checker. Recording the boundary stops strict mode
from either creeping outward or being quietly abandoned.

**NFR-M5 is the canary.** U-01 needs nothing beyond the standard library. If a runtime dependency ever
appears under `core/`, that is not a dependency problem — it is a signal the AWS-free boundary has been
crossed.

---

## Testability

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| NFR-T1 | All **ten** properties (P1–P10) MUST be implemented as Hypothesis property tests | PBT-01..10, functional design | **Automated** — `tools/check` |
| NFR-T2 | `max_examples = 100` per property | Q5, matching `packages/builder-mcp` | **Automated** — profile in `pyproject.toml` |
| NFR-T3 | Shrinking and seed reporting MUST NOT be disabled | PBT-08 | Review |
| NFR-T4 | Example-based tests MUST complement the properties, including NFR-P2's size check | PBT-10, Q8 | **Automated** |
| NFR-T5 | `_reference_group_by_tag` MUST be written independently of `group_by_tag` | P5 | **Review only — and it cannot be automated** |
| NFR-T6 | The suite MUST run in `tools/check`, mirroring the existing `builder-mcp` block | Q3 | **Automated** — by existing |
| NFR-T7 | Generators MUST cover the eight shapes listed in `business-logic-model.md` | US-10 | Review |

**NFR-T5 is the one requirement here that no tool can enforce**, and it is load-bearing: if the oracle is
written by copying the implementation, P5 becomes a tautology that passes forever while asserting nothing.
Flagged as review-only rather than folded in with the automated ones, because a reviewer needs to know
which lines they are personally responsible for.

**NFR-T6's cost was already paid.** `tools/check` already runs `cd packages/builder-mcp && uv run --quiet
pytest -q`. U-01's block mirrors it, including running from the package directory (pytest resolves
`testpaths` against its own rootdir) and relying on `.python-version` so `uv` fetches a 64-bit CPython.
Both details are copied from the existing block's comments rather than rediscovered.

---

## Security and privacy

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| NFR-S1 | Exceptions raised by U-01 MUST carry a **reason category only** — no ARN, no tag key, no tag value, no input index | Q6, SECURITY-09, FR-3.4 | **Review** + NFR-S2 |
| NFR-S2 | `skipped_reasons` keys MUST come from a fixed closed set (`"arn"`, `"tags"`) | Q6, BR-02 | **Automated** — an enum, not free text |
| NFR-S3 | ARN parsing MUST use `str.split(":", 5)` with explicit arity and emptiness checks — **no regular expression** | Q7 | Review |
| NFR-S4 | Serialization MUST use JSON only. No `pickle`, no `yaml.load`, no `eval` | SECURITY-14, BR-08 | **Automated** — grep |
| NFR-S5 | Deserialization MUST reject a major-version mismatch, malformed JSON, and a naive `collected_at` rather than best-effort parsing | BR-08 | **Automated** — property/example tests |
| NFR-S6 | No log emission from U-01 at all | Q6 | **Automated** — grep for `logging` |

**Why NFR-S1 is stricter than it looks necessary.** `cornell:owner` holds a **NetID**. U-01 is the only
place tag values are parsed, so it is the only place a NetID can enter an exception message — and an
exception message can reach a log group or, through an unhandled error, an HTTP body. Making the rule
"category only" is structural: it does not depend on every future exception message being written
carefully by someone who remembers this.

**NFR-S3's justification is not current risk.** ARNs arrive from AWS, not from users, so ReDoS is not a
present threat. But "the input is trusted" is a property that erodes — the collector is one configuration
change from reading a file — and a split costs nothing over a regex for a fixed six-field grammar. A
permissive pattern would also silently accept malformed ARNs a split-plus-check rejects.

**NFR-S6 follows from NFR-S1.** A pure library that emits no logs cannot leak through them. Logging is
U-02's, at a boundary where retention and access are configurable.

---

## Reliability

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| NFR-R1 | Function totality MUST match the table in `business-logic-model.md` | Functional design | **Automated** — property tests |
| NFR-R2 | `normalize_all` and `evaluate_freshness` MUST be **total** — no input causes them to raise | Q1, Q6, BR-02, BR-07 | **Automated** |
| NFR-R3 | P8's accounting identity MUST be asserted at snapshot construction **and** on deserialization | BR-02, BR-04, BR-08 | **Automated** |

**NFR-R2 is the reliability requirement that matters most in this unit.** `normalize_all` being total is
Q1 = A expressed as a contract: the only function the collector calls cannot fail on a malformed item, so
one bad ARN cannot take down a snapshot. `evaluate_freshness` being total keeps a provenance fault on the
read path from becoming an unexplained 500 instead of the deliberate 503.

---

## Explicitly N/A for this unit

Recorded with reasons so the artifact does not read as though the categories were forgotten. Each marked
**U-02** applies squarely there and will be asked at its NFR pass.

| Category | Why N/A here |
|---|---|
| Availability, uptime, DR, failover | A library has no uptime. RESILIENCY-02 already records RTO/RPO N/A; U-01 holds no state to recover. |
| Scalability triggers, capacity planning | Runs in-process in its caller. NFR-P2 covers the only real dimension (input size). → **U-02** |
| Throughput, concurrency, rate limiting | All functions pure and stateless: trivially concurrency-safe, nothing to throttle. → **U-02** |
| Authentication, authorization | No identity system exists anywhere (FR-5.5). |
| Encryption at rest / in transit | Touches no storage, no network. → **U-02** (SECURITY-01, -02) |
| Monitoring, alerting, tracing | Emits nothing (NFR-S6). → **U-02** (C-09) |
| Usability, accessibility, i18n | No interface. → **U-02** (C-06) |
| Data retention, backup | Persists nothing; `state: derived` decided at Q9c. |
| RESILIENCY-04 / -14 / -15 | Already deferred to **NFR Design**, the next stage. |
| Cost | Estimated at Units Generation. U-01 adds no runtime cost — it is code inside a Lambda that runs regardless. |

---

## Verification summary

| Group | Automated | Review-only | Total |
|---|---|---|---|
| Performance | 1 | 3 | 4 |
| Maintainability | 3 | 3 | 6 |
| Testability | 4 | 3 | 7 |
| Security & privacy | 4 | 2 | 6 |
| Reliability | 3 | 0 | 3 |
| **Total** | **15** | **11** | **26** |

The eleven review-only requirements are NFR-P1, P3, P4, M3, M4, M6, T3, T5, T7, S1 and S3 — of which
**NFR-T5 is the only one whose failure is silent and permanent**. Every other review item fails visibly: a
missing docstring is obvious, a regex ARN parser is obvious in a diff, an out-of-scope mypy config is
obvious in `pyproject.toml`. A copied oracle looks correct and passes forever.

That asymmetry is why NFR-T5 is called out separately rather than listed among the others — it is the one
line where a reviewer's attention is the only control.

## Carried forward

- **§6.4** — site-sync ordering. Unchanged, U-02, Infrastructure Design.
- **Cross-unit to U-02**: `Freshness.INVALID` → 503; the three accounting counts must reach the UI; and
  **new from Q6 = A** — C-01 must log enough at its own boundary to identify a skipped item, because U-01
  deliberately cannot.
- **`tools/check` remains unexecutable here** (needs `uv` and `terraform`). NFR-M1, M2, T1, T6 and the
  grep checks are specified but **unrun**. First verification is CI or a machine with both installed.
