# NFR Design Patterns — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Design (artifact 1 of 2)
**Date**: 2026-08-03
**Decisions**: `construction/plans/u-02-dashboard-platform-nfr-design-plan.md` Part A2 (Q1–Q6, all **A**)

Every pattern here traces to a numbered NFR requirement and says how it is visible in review. Nothing is
included because it is conventional. Where a pattern was already fixed at Functional Design or NFR
Requirements, it is named for the inventory and cross-referenced, not re-decided.

Unlike U-01 — a pure library with zero infrastructure and eight pattern families recorded N/A — every
mandated category is live for U-02. The dispositions (settled / decided here / routed to Infrastructure
Design) are in §8.

---

## 1. Collector upstream resilience — declarative SDK config (Q1 = A)

**Serves**: CR-02, S-4, RESILIENCY-10. **Visible in**: the client construction; a unit test asserting the
client's `.meta.config`.

The Resource Groups Tagging API client is built once with an explicit `botocore.config.Config`:

```python
Config(
    connect_timeout=<s>,
    read_timeout=<s>,
    retries={"mode": "standard", "max_attempts": <N>},
)
```

The SDK's `standard` retry mode supplies exponential backoff with jitter — which the design uses rather than
re-implements, because a hand-rolled loop without jitter synchronises retries under load, the exact failure
adaptive backoff exists to prevent. When retries are exhausted the terminating `ClientError` is caught at the
call site and mapped to **`UPSTREAM_THROTTLED`**, so an SDK-level give-up becomes a *named* collector
failure rather than a raw exception.

**The explicit timeouts are the load-bearing part of CR-02.** boto3's default socket timeout is long enough
that a stalled connection can consume most of the Lambda budget before the SDK notices; a short, explicit
`read_timeout` is what turns a hung upstream into a bounded, retryable error.

*Rejected*: a hand-rolled retry loop (duplicates the SDK, tends to omit jitter); `adaptive` mode (stateful
across calls, little to estimate from at once-hourly single-concurrency). See Q1 options B/C.

---

## 2. Context-derived internal deadline (Q2 = A) — refines TSD-8

**Serves**: P-3. **Visible in**: the page loop's top-of-iteration guard; an integration test with a slow
stubbed pager. **Precedent**: `blueprints/knowledgebase/infra/knowledgebase.yml`.

The collector reads `context.get_remaining_time_in_millis()` and stops *before starting a new page* once the
remaining time drops below a fixed safety margin (~20 s — enough to build the failure result and write the
log), raising **`UPSTREAM_TOO_SLOW`**. The 120 s Lambda timeout (P-1) is thereby the **single source of
truth** for the budget; the internal deadline tracks it automatically.

> **TSD-8 refinement (recorded, not silent).** TSD-8 stated this deadline as a hardcoded "≈100 s". This
> stage refines the *mechanism* to a derived bound while leaving the *numeric intent unchanged* — at the
> default 120 s timeout the margin lands the effective deadline near 100 s. TSD-8's original wording stands
> in `tech-stack-decisions.md`; `aidlc-state.md` carries the pointer. P-3, S-3 and the collector's failure
> semantics are untouched.

Why this matters beyond tidiness: if a future PR raises the timeout for a larger account, a hardcoded 100 s
would silently become wrong (the platform timeout could win again, producing the unnamed failure P-3 was
written to eliminate). A derived deadline cannot go stale.

---

## 3. Three named bounds, ordered so the platform timeout never wins (Q1 + Q2, Interaction 3)

**Serves**: P-3, CR-01, CR-02, SECURITY-15. **Visible in**: the collector's control flow and the reason
code on each failure path.

The collector has **three named stop conditions**, plus the platform's 120 s timeout as a last-resort
*unnamed* bound the design keeps from ever firing:

| Bound | Check location | Reason code |
|---|---|---|
| Pagination limit (50 pages) | per loop iteration | `PAGE_LIMIT_EXCEEDED` |
| Internal deadline (§2) | top of each iteration, before the next page | `UPSTREAM_TOO_SLOW` |
| SDK retry exhaustion (§1) | surfaced from the `get_resources` call | `UPSTREAM_THROTTLED` |
| *(platform 120 s timeout)* | *Lambda runtime* | *unnamed — must not win* |

The ordering guarantee: the deadline and page-count checks run at the top of the loop and the retry
exhaustion is caught at the call, so **every failure is attributable before the runtime can kill the
invocation**. No two bounds share a reason code, so a log line unambiguously says which one fired — which is
what CR-04's per-skip logging and the R-10 runbook depend on.

---

## 4. Structured logging — stdlib `logging` + JSON (Q3 = A)

**Serves**: SEC-4, OR-06, CR-04, US-12, D-5. **Visible in**: the module-level logger setup; a grep for the
skip-log call shape. **Precedent**: `course-chatbot/src/handler.py`, `packages/builder-mcp`.

Both functions use `logging.getLogger()` with the level from `os.environ["LOG_LEVEL"]` (default `INFO`) and
a JSON formatter emitting one object per record — matching the two existing handlers exactly, so the repo
keeps one logging convention rather than two. `aws-lambda-powertools` was rejected: a new runtime dependency
with zero repo precedent, against Q11 = B's supply-chain posture (see Q3 option B).

**CR-04 is enforced by the fields the call passes, not by a filter.** The per-skip entry carries the reason
code and the resource ARN and *nothing else* — no tag values, because a `cornell:owner` value is a NetID and
a log group has readers. This is greppable and reviewable: the skip-log call site lists its keys explicitly.

---

## 5. Metrics via Embedded Metric Format (Q4 = A) — same channel as logs

**Serves**: R-8, CR-06, RESILIENCY-05. **Visible in**: the EMF envelope emitted on every outcome; an
integration test asserting the `_aws` envelope shape. R-8 is **`deployed`-verified** (§7).

Metrics are written as EMF log records — the `_aws` metadata envelope CloudWatch extracts metrics from — on
**success and failure**: duration, `pages_fetched`, `resources_collected`, `skipped_count`, snapshot age,
and outcome. Because an EMF metric *is* a log line (Q3's channel), this adds **no API call, no IAM
permission, and cannot throttle** — which is decisive on the collector's failure path, precisely when R-8
must still fire. `put_metric_data` was rejected for putting a throttleable synchronous call on that path
(Q4 option B).

**CR-04's privacy rule extends here** (Interaction 2): EMF *dimensions* must never carry a tag value. The
chosen dimensions are all counts and outcomes; a future "top owner" dimension would leak a NetID into
CloudWatch and is forbidden by the same rule that governs the logs.

*Cost, stated honestly*: an EMF envelope with a malformed shape emits no metric and fails silently — a
`deployed`-only failure mode, consistent with R-8's own classification. The envelope-shape integration test
is the mitigation.

---

## 6. API totality via one outer error boundary (Q5 = A)

**Serves**: R-2, AR-02, AR-03, AR-06. **Visible in**: the handler's single enclosing `try/except`; the
route table checked before any S3 access.

`api.handler` is **total** by structure, not by per-branch discipline:

1. Unknown routes return 404 **before any S3 access** (AR-01) — the closed five-route table.
2. A known route classifies the S3 read into the six-state table (AR-02, AR-03): present-fresh, present-stale,
   present-empty, absent (`no_data`, 200), unreadable (503), and the inherited `INVALID`→503 sixth row.
3. **Any exception escaping the above is caught by one top-level handler** and mapped to a generic 503 with
   no internals (AR-06) — no stack trace, ARN, bucket name, key, or account id.

Because the generic-503 mapping lives in exactly one place, **AR-06 cannot be undone by a new route
forgetting to sanitise its own errors**, and R-2 ("no path escapes without a response") is a property of the
enclosing structure a reviewer sees at a glance. Per-route try/except was rejected for resting totality on
every future route getting it right (Q5 option B).

*Seam named for review*: the outer handler must not contain a path that can raise *before* entering the
`try` (e.g. event parsing) — that would escape the boundary. Event access is inside the guard.

---

## 7. Complete-or-fail write, closed-allowlist validation, degrade-to-stale (settled upstream, named here)

These were decided at Functional Design / NFR Requirements; they are named so the pattern inventory is
complete and their review-visibility is on record.

| Pattern | Serves | Decided | Review-visible in |
|---|---|---|---|
| **Complete-or-fail write** — one `PutObject` of a freshly built snapshot, no read-modify-write; on any failure the previous snapshot survives | CR-05, R-1, SECURITY-15 | Functional Design | absence of any `GetObject`-then-`PutObject` on the collector path |
| **Closed-allowlist route validation** — `{tag_key}` checked against the four-element `REQUIRED_TAGS`; everything else 404 | AR-01, SEC-5 | Functional Design | the route table; a property test on `route` |
| **Degrade-to-labelled-stale** — a collector failure leaves the prior snapshot; the UI shows *stale* against a shared threshold | A-4, US-05, R-4 | Functional Design | the six-state mapping + the alarm sharing `3 × interval` |
| **Async fail-clean** (Q6 = A) — `MaximumRetryAttempts: 0`, no DLQ; alarm fires, next tick retries | OR-01, R-3 | **here** | the Lambda async-invoke config; absence of a DLQ resource |

**Q5 and Q6 are one discipline on two functions** (Interaction 4): a failure must be *named and visible*,
never papered over. The API never leaks an unhandled exception; the collector never hides a failed run behind
a silent retry. Both compute boundaries express the same stance.

---

## 8. Every mandated category, with its disposition

No category is inapplicable to U-02. Each is settled upstream, decided here, or routed to Infrastructure
Design — stated so the artifact never reads as though a category was forgotten.

| Category | Disposition |
|---|---|
| **Resilience** | Decided here: §1 retry/timeout, §2 deadline, §6 API boundary, §7 async fail-clean. Settled: A-4 degrade, CR-05 complete-or-fail, R-4 `TreatMissingData: breaching`. **N/A**: circuit breakers / bulkheads — one hourly upstream call and one S3 read have nothing to isolate. |
| **Scalability** | Settled: S-1 reserved concurrency 1, P-5 throttle 20 rps. **Routed**: API reserved-concurrency number (S-2). **N/A**: sharding/partitioning/autoscaling — managed services scale without configuration (S-5). |
| **Performance** | Decided here: §2 deadline derivation. Settled: P-4 no provisioned concurrency, P-6/P-7 cache strategy. |
| **Security** | Settled: SEC-1..15 (deny-by-default WAF, least-privilege IAM, strict CSP, encryption, no identity). Decided here: §4 CR-04-safe logging. **Routed**: exact CSP directive string; WAF IPv6 IPSet decision. |
| **Logical components** | §7 (Q6) settles that **no queue/DLQ component exists**. Full inventory in `logical-components.md`. |
| **Observability** | Decided here: §4 logging, §5 metrics. Settled: R-3..R-7 alarms, R-11 tracing N/A. |

**Routed to Infrastructure Design, carried forward untouched**: §6.4 site-sync ordering · WAF IPv6
(two IPSets or documented IPv4-only scope) · notify-topic ARN mechanism (parameter vs naming convention) ·
API reserved-concurrency number (S-2) · exact CSP directive string · resource-by-resource template shape.

---

## 9. The four `deployed`-only requirements — the honest weak point

Four requirements cannot be verified by any static analysis and are confirmed only against a running stack.
The patterns above make them *likely* correct; none proves them.

| ID | What only a deployment confirms | Which pattern supports it |
|---|---|---|
| SEC-7 | the WAF allowlist actually admits the right people | deny-by-default ER-01 (settled) |
| A-4 | a collector failure really degrades to *labelled stale* | §7 degrade + §7 async fail-clean |
| P-6 | the cache behaves (immutable assets, 60 s `index.html`) | P-6 cache strategy (settled) |
| R-8 | metrics actually arrive | §5 EMF |

**U-01 finished with 60 executed tests and a 9/9 mutation score. U-02 structurally cannot reach that without
a merge to `main`, which deploys to the shared account.** That asymmetry is a property of the unit — most of
U-02 is CloudFormation, and `cfn-lint` checks a template is *valid*, not that a cache policy is the right way
round — and it must not be smoothed over when U-02's Build and Test reports.
