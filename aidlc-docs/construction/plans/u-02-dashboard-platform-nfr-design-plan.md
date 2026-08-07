# NFR Design Plan — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Design
**Date**: 2026-08-03
**Unit**: U-02 Dashboard Platform
**Inputs**: `construction/u-02-dashboard-platform/nfr-requirements/` (approved 2026-08-03) ·
`functional-design/` (approved) · U-01's NFR Design (approved) · amendments A1–A3

---

## What this stage can and cannot mean for U-02

This is the mirror image of U-01's NFR Design. U-01 had **zero** infrastructure components and recorded
eight mandated pattern families as inapplicable, because a set of pure functions has no fault to tolerate,
no load to shed, and nothing to insert. U-02 is the deployable: two Lambdas, two S3 buckets, an API
Gateway HTTP API, one CloudFront distribution, a WAF web ACL, an EventBridge schedule, CloudWatch alarms
and log groups, and a reference to an existing SNS topic. **Every mandated category is live here.**

So this stage does two real things:

1. **Decides the cross-cutting design patterns that make the 49 NFR requirements hold** — how the collector
   tolerates a slow or throttling upstream, how the internal deadline is *derived* rather than guessed, how
   both functions log and emit metrics, and how the API guarantees it is total. These are the decisions
   that determine whether R-1, R-2, P-3, SEC-4, D-5 and R-8 are structural or merely intended.
2. **Names the logical components** and their integration — the `logical-components.md` artifact, which for
   U-02 is a genuine infrastructure inventory rather than (as in U-01) a statement that there is none.

### What this stage does NOT reopen

- **RESILIENCY-04, -14 and -15 are already discharged**, not open. -14 was closed at U-01's NFR Design (the
  property suite); **-04 and -15 were closed at U-02's NFR Requirements** via R-9 (revert-to-rollback,
  deploy-by-digest) and R-10 (the README runbook). The deferral count stopped at 2. This stage does not
  re-defer or re-answer them — doing so would be the third move of a rule that already has a home.
- **Settled numbers stay settled**: sizing (P-1, P-2), no provisioned concurrency (P-4), throttle 20 rps
  (P-5), the cache strategy (P-6, P-7), retention (D-2..D-6), reserved concurrency 1 (S-1),
  `TreatMissingData: breaching` (R-4), degrade-to-stale (A-4). NFR Design chooses *mechanisms*, not these.

### What belongs to Infrastructure Design, not here

Carried forward untouched, because each is a resource-by-resource IaC-shape decision, not a pattern:
**§6.4 site-sync ordering**, the **WAF IPv6** two-IPSets-or-documented-scope decision, the
**notify-topic ARN mechanism** (parameter vs naming convention), the **API reserved-concurrency number**
(S-2), and the **exact CSP directive string**. Part A1 lists these so a reader sees they were considered
and deliberately routed onward.

Part A1 also records, for each mandated category, whether it is settled upstream, decided here, or routed
to Infrastructure Design — so the artifact never reads as though a category was forgotten.

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

Six questions, one per cross-cutting mechanism the requirements name but do not shape. Five of the six have
direct repo precedent, cited in the option text rather than argued from first principles.

---

### Question 1 — How does the collector tolerate a slow or throttling upstream? (CR-02, S-4, RESILIENCY-10)

CR-02 requires "explicit SDK connect/read timeouts" and "bounded backoff, then raise `UPSTREAM_THROTTLED`".
That fixes the *behaviour*; it does not fix the *mechanism*. There is **no `botocore.Config` retry
precedent anywhere in the repo** — every existing client uses boto3 defaults (standard mode, 3 attempts,
no explicit timeouts). So this is a genuine open decision.

**A) Declarative `botocore.Config` — timeouts and retry mode as SDK configuration** ← *recommended*
   Construct the Resource Groups Tagging API client with
   `Config(connect_timeout=…, read_timeout=…, retries={"mode": "standard", "max_attempts": N})`, and map an
   exhausted-retries `ClientError` to `UPSTREAM_THROTTLED`.
   *Why*: the SDK already implements exponential backoff with jitter correctly; hand-rolling it re-implements
   a solved problem and tends to get the jitter wrong. Configuration is declarative, testable by inspecting
   the client's config, and the timeouts are the part CR-02 specifically calls "explicit."
   *Cost*: the boundary between "boto3 retried and gave up" and "our code decides to stop" must be drawn
   clearly, or a caller cannot tell which bound fired.

**B) Hand-rolled retry loop** around each `get_resources` call with explicit `sleep` and backoff.
   *Why*: total control over the sequence; the retry count is visible in our own code.
   *Cost*: duplicates the SDK's backoff, and a naive loop without jitter synchronises retries under load —
   the failure mode adaptive backoff exists to avoid.

**C) boto3 `adaptive` retry mode** — client-side rate limiting that backs off on throttling automatically.
   *Why*: designed for exactly a throttled API.
   *Cost*: adaptive mode is stateful across calls and less predictable to reason about in a unit test than a
   fixed `max_attempts`; for a once-hourly single-concurrency collector, its client-side rate estimation has
   little to work with.

X) Other

[Answer]:A

---

### Question 2 — How is the collector's internal deadline derived? (P-3, TSD-8)

P-3 requires the collector to raise `UPSTREAM_TOO_SLOW` on an internal deadline **below** the 120 s Lambda
timeout, so a slow upstream fails with a *name* rather than as a bare platform timeout. TSD-8 wrote that
deadline as a hardcoded "≈100 s". There is a **direct repo precedent that does this better**:
`blueprints/knowledgebase/infra/knowledgebase.yml` bounds its poll loop by
`context.get_remaining_time_in_millis()` rather than a fixed count, documenting the reason as "*Polling is
deadline-driven off this value, not a fixed iteration count. Raising [the timeout] raises the polling budget
automatically.*"

**A) Derive the deadline from `get_remaining_time_in_millis()`, reserving a fixed safety margin** ← *recommended*
   Before starting each page, stop and raise `UPSTREAM_TOO_SLOW` once remaining time drops below a margin
   (enough to build and write the partial-free failure and log it). **This refines TSD-8's "≈100 s"** from a
   guessed constant to a derived bound.
   *Why*: single source of truth — the 120 s timeout parameter is the *only* place the budget is stated, and
   the deadline tracks it automatically. Matches the one existing precedent for exactly this problem. If a
   future PR raises the timeout for a larger account, the collector's budget rises with it and no second
   constant goes stale.
   *Cost*: a small refinement to an already-approved TSD-8 number-mechanism, recorded explicitly in Part A2
   rather than silently. The margin is a chosen constant (the one thing still hardcoded), justified by how
   long the failure-write path takes.

**B) Hardcoded ~100 s constant**, as TSD-8 literally states.
   *Why*: simplest; no dependency on the context object; exactly what was approved.
   *Cost*: two independent numbers (the 120 s timeout parameter and the 100 s constant) that must be kept in
   the right order by hand. Raising one and forgetting the other reintroduces the bare-timeout failure P-3
   exists to prevent.

X) Other

[Answer]:A

---

### Question 3 — What is the structured-logging mechanism for both functions? (SEC-4, OR-06, D-5)

SEC-4 and OR-06 require structured JSON logs; CR-04 requires one entry per skipped item carrying the reason
code and ARN but **never a tag value**. The repo has a clear house pattern:
`course-chatbot/src/handler.py` and `packages/builder-mcp` both use stdlib `logging.getLogger()` with
`LOG.setLevel(os.environ.get("LOG_LEVEL", "INFO"))`. **`aws-lambda-powertools` appears nowhere in the repo.**

**A) stdlib `logging` with a JSON formatter, level from `LOG_LEVEL`** ← *recommended*
   A small `logging.Formatter` (or a `json.dumps` in a filter) emitting one JSON object per record; the
   CR-04 skip entry is a structured call with fixed keys. Matches `course-chatbot` and `builder-mcp` exactly.
   *Why*: no new dependency — which matters directly under Q11 = B, where every added package is unscanned
   npm-equivalent surface. One convention across the repo's Lambdas instead of two. The CR-04 "log ARN, never
   a tag value" rule is enforced by *what fields the call passes*, which is reviewable and greppable.
   *Cost*: a few lines of formatter code we own, versus a library that would provide it.

**B) `aws-lambda-powertools` Logger** — structured logging, correlation IDs, and (with its Metrics module)
   EMF for free.
   *Why*: purpose-built for Lambda; would also answer Q4 in the same import.
   *Cost*: a **new runtime dependency with zero repo precedent**, pulling a transitive tree into both images,
   against the supply-chain posture Q11 = B set. Introducing the repo's first powertools usage inside a
   cost-visibility blueprint is a poor place to start a convention.

**C) Bare `print(json.dumps(...))`.**
   *Why*: absolute minimum; CloudWatch captures stdout.
   *Cost*: no levels, no filtering, and it diverges from the two existing handlers for no gain.

X) Other

[Answer]:A

---

### Question 4 — How are operational metrics emitted? (R-8, CR-06, RESILIENCY-05)

CR-06/R-8 require metrics on every outcome — duration, `pages_fetched`, `resources_collected`,
`skipped_count`, snapshot age — on success *and* failure. R-8 is a **`deployed`-verified** requirement, so
the mechanism should minimise the ways it can silently not-emit. No metric-emission precedent exists in the
repo.

**A) Embedded Metric Format (EMF) — a structured log line CloudWatch extracts metrics from** ← *recommended*
   The metrics are written as a specially-shaped JSON log record (the `_aws` envelope); CloudWatch turns them
   into metrics with no API call.
   *Why*: no extra API call means nothing to throttle or time out on the collector's own failure path —
   which is exactly when R-8 must still fire. No additional IAM permission (it is a log write, which the
   function already has). And it composes with Q3 = A: metrics and logs are the same delivery channel.
   *Cost*: the EMF envelope shape must be exactly right or the metric silently doesn't materialise — a
   `deployed`-only failure, consistent with R-8's own classification. One integration test asserting the
   envelope shape mitigates this.

**B) `CloudWatch.put_metric_data` API calls.**
   *Why*: explicit and obvious; easy to read.
   *Cost*: a synchronous API call on the failure path — it can itself throttle or time out, so the metric
   most needed (a failing collector) is the one most at risk. Adds an IAM permission and latency to every
   invocation.

**C) `aws-lambda-powertools` Metrics** (EMF under the hood, nicer API).
   *Cost*: same new-dependency objection as Q3 = B. Only reasonable if Q3 = B is also chosen.

X) Other

[Answer]:A

---

### Question 5 — How is the API handler's totality guaranteed? (R-2, AR-02, AR-03, AR-06)

R-2 requires `api.handler` to be **total** — no path escapes without a response — and AR-06 requires that no
error body leak internals. Totality can be structural or per-route.

**A) One outer error boundary around the whole handler** ← *recommended*
   The route dispatch and per-state logic run inside a single top-level `try/except`; any exception that
   escapes it is mapped to a generic 503 with no internals (AR-06). Inside, S3-read outcomes are classified
   explicitly into the six-state table (AR-02, AR-03). The 404 for unknown routes is decided *before* any S3
   access (AR-01).
   *Why*: makes "returns a response on every path" a property of one enclosing structure a reviewer can see
   at a glance, rather than a claim about every branch. The generic-503 mapping lives in exactly one place,
   so AR-06 cannot be undone by a new route forgetting to sanitise its own errors. R-2 becomes structural.
   *Cost*: the outer handler must not itself contain a path that can raise before entering the `try` (e.g.
   parsing the event) — that seam is named for review.

**B) Per-route `try/except`**, each route responsible for its own error mapping.
   *Why*: localised handling, each route explicit about its failure modes.
   *Cost*: totality then rests on *every* route getting it right, and a future route can silently omit the
   catch — the failure R-2 exists to prevent, reintroduced per-route.

X) Other

[Answer]:A

---

### Question 6 — What is the scheduled collector's async-invocation failure posture? (OR-01, R-3, CR-05, A-4)

EventBridge invokes the collector **asynchronously**, which brings two Lambda knobs the requirements have
not set: async **retry attempts** (default 2) and an optional **on-failure destination / DLQ**. The snapshot
is `state: derived` (D-7), CR-05 guarantees a failed run leaves the previous snapshot intact, and OR-01
alarms on the *first* failure.

**A) `MaximumRetryAttempts: 0`, no DLQ — the alarm is the signal, the next tick is the retry** ← *recommended*
   Fail cleanly on the first failure; OR-01 fires immediately; the next hourly schedule is the natural retry.
   *Why*: the async event is a bare schedule tick carrying no recoverable payload — there is nothing in a DLQ
   worth replaying, because re-running *is* just running again. Default retries (2) inside a
   reserved-concurrency-1 function can also collide with the alarm's picture of "how many failures." Zero
   retries keeps the failure signal one-to-one with reality, which is what R-3 + R-4 depend on.
   *Cost*: a transient blip that a single retry would have papered over instead shows as one alarm — accepted,
   because A-4's design is that a missed collection degrades visibly to *labelled stale*, not that it is
   hidden.

**B) Default retries (2), no DLQ.**
   *Why*: rides out a transient upstream error without alarming.
   *Cost*: muddies the failure count and can overlap invocations against reserved concurrency 1.

**C) A DLQ / on-failure destination** capturing failed events.
   *Cost*: new infrastructure (an SQS queue + its own alarm surface) to capture events that carry nothing
   replayable. Value is near zero for a derived, self-healing snapshot.

X) Other

[Answer]:A

---

## Part A1 — Mandated categories: settled, decided here, or routed onward

Unlike U-01, no category is *inapplicable* to U-02. Each is one of: **settled** by a prior approved stage,
**decided here** by a question above, or **routed** to Infrastructure Design as an IaC-shape decision.

| Mandated category | Disposition for U-02 |
|---|---|
| **Resilience patterns** — retries, backoff, timeouts, fallback, degradation | **Decided here** (Q1 retry/timeout mechanism, Q6 async failure posture) + **settled** (A-4 degrade-to-stale, CR-05 complete-or-fail, R-4 `TreatMissingData: breaching`). Circuit breakers/bulkheads: **N/A** — a single once-hourly upstream call and a single S3 read have nothing to isolate. |
| **Scalability patterns** — concurrency bounds, load shedding | **Settled** (S-1 reserved concurrency 1; P-5 throttle 20 rps). **Routed**: the API's reserved-concurrency *number* (S-2) is a value for Infrastructure Design. Sharding/partitioning/autoscaling **N/A** — managed services scale without configuration (S-5). |
| **Performance patterns** — deadlines, caching, cold start | **Decided here** (Q2 deadline derivation) + **settled** (P-4 no provisioned concurrency; P-6/P-7 cache strategy). |
| **Security patterns** — authn/z, encryption, network isolation, headers, supply chain | **Settled** by NFR Requirements §Security (SEC-1..15) and Functional Design (deny-by-default WAF, least-privilege IAM, strict CSP, no identity). **Decided here** only where a mechanism remained: Q3's CR-04-safe logging (never a tag value). **Routed**: the exact CSP directive string and the WAF IPv6 IPSet decision. |
| **Logical components** — queues, caches, circuit breakers, and the real infrastructure inventory | **Decided here** in part (Q6 settles whether a DLQ/queue component exists — recommended *not*). The full component inventory and their wiring is the substance of `logical-components.md`. |
| **Observability patterns** — logging, metrics, alarms, tracing | **Decided here** (Q3 logging mechanism, Q4 metrics mechanism) + **settled** (R-3..R-7 alarms, R-11 tracing N/A). |

**Routed to Infrastructure Design, carried forward untouched**: §6.4 site-sync ordering · WAF IPv6
(two IPSets or documented IPv4-only scope) · notify-topic ARN mechanism (parameter vs naming convention) ·
API reserved-concurrency number (S-2) · exact CSP directive string · resource-by-resource template shape.

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] Confirm all six `[Answer]:` tags are filled
- [x] Run the Step 5 analysis for vagueness, contradiction, and option-merging; raise follow-ups rather than
      proceeding if any is found
- [x] Record resolved decisions and interactions in a `Part A2` section
- [x] If Q2 = A, record the **refinement to TSD-8** (deadline derived from `get_remaining_time_in_millis()`,
      not a hardcoded ~100 s) explicitly — an approved number-mechanism is being refined, so it is annotated,
      not silently changed

### B2. `nfr-design-patterns.md`
- [x] The cross-cutting patterns U-02 uses, each named and traced to the NFR requirement it satisfies and how
      it is visible in review: SDK-configured retry/timeout (Q1), context-derived deadline (Q2), structured
      logging (Q3), EMF or chosen metric emission (Q4), single outer error boundary (Q5), async failure
      posture (Q6)
- [x] The complete-or-fail write pattern (CR-05/R-1) and the closed-allowlist route validation (AR-01/SEC-5),
      as patterns already decided at Functional Design but named here for the pattern inventory
- [x] The degrade-to-labelled-stale availability pattern (A-4) and its shared threshold with the alarm (R-4)
- [x] For each: which NFR requirement it satisfies, and — for the four `deployed`-only requirements — that its
      verification is deferred to a running stack, stated at its real strength
- [x] Every Part A1 category addressed with its disposition (settled / decided / routed / N/A + reason)

### B3. `logical-components.md`
- [x] The full infrastructure inventory: C-01 collector Lambda, C-02 snapshot bucket, C-03 API Lambda,
      API Gateway HTTP API, C-07 CloudFront distribution + WAF web ACL + IPSet, the site bucket, the
      EventBridge schedule, CloudWatch alarms and log groups, and the **reference** to the existing
      `notify-topic` SNS topic (a dependency, not a component this unit creates)
- [x] Whether a queue/DLQ component exists (Q6) — stated as a decision with its reason
- [x] The data-flow and trust boundaries: collector → snapshot bucket → API → CloudFront/WAF → browser;
      which role can touch which key (SR-02); same-origin `/api/*` (no CORS surface)
- [x] The U-01 ↔ U-02 interface as consumed here: both images import `dashboard.core`; the boundary grep
      still forbids `boto3`/`os`/clock under `src/dashboard/core/`
- [x] Explicitly mark the Infrastructure-Design-routed items as *not settled here*, with owner

### B4. Validation and honest reporting
- [x] Every pattern traces to an NFR requirement; none included because it is conventional
- [x] No pattern contradicts a settled decision (sizing, cache, concurrency, retention, `TreatMissingData`)
- [x] The four `deployed`-only requirements (SEC-7, A-4, P-6, R-8) are reported as verifiable only against a
      running stack — the asymmetry with U-01 not smoothed over
- [x] Report anything unsettled with the stage that carries it

### B5. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 🎨 NFR Design Complete - U-02 Dashboard Platform` and wait for explicit approval

---

## Part A2 — Resolved decisions (Q1–Q6)

Step 5 analysis. All six clean single selections, all **A**, no vagueness, contradiction or
option-merging. No blocking follow-up. Answered "choose defaults and proceed" — recorded as an explicit
acceptance of each recommendation, not an absence of a decision.

| # | Decision | Answer |
|---|---|---|
| Q1 | Collector retry/timeout | Declarative `botocore.Config` (`connect_timeout`, `read_timeout`, `retries` standard mode); exhausted retries → `UPSTREAM_THROTTLED` |
| Q2 | Internal deadline | Derived from `get_remaining_time_in_millis()` with a fixed safety margin — **refines TSD-8** |
| Q3 | Structured logging | stdlib `logging` + JSON formatter, level from `LOG_LEVEL`; no powertools |
| Q4 | Metric emission | Embedded Metric Format (EMF) — a structured log line, no API call |
| Q5 | API totality | One outer error boundary → generic 503; states classified inside |
| Q6 | Async failure posture | `MaximumRetryAttempts: 0`, no DLQ; alarm is the signal, next tick is the retry |

### Interaction 1 — Q2 = A refines an approved TSD-8 number-mechanism (recorded, not silent)

TSD-8 (approved at NFR Requirements) states the collector's internal deadline as "≈100 s". Q2 = A replaces
the **guessed constant** with a **derived bound**: the deadline is `get_remaining_time_in_millis()` less a
fixed safety margin sufficient to build and write the failure snapshot-free result and log it.

> **TSD-8 refinement.** P-3's "≈100 s → `UPSTREAM_TOO_SLOW`" is now "stop starting a new page once the
> remaining Lambda time drops below a fixed margin (~20 s), then raise `UPSTREAM_TOO_SLOW`." The 120 s
> timeout parameter (P-1) becomes the single source of truth; the deadline tracks it automatically.

This is annotated rather than rewritten in place: TSD-8's original "≈100 s" wording stands in
`tech-stack-decisions.md`, and `aidlc-state.md` carries the refinement pointer. The **numeric intent is
unchanged** at the default 120 s timeout — the margin lands the effective deadline near 100 s — so P-3, S-3
and the collector's failure semantics are untouched; only the *mechanism* moved from a second hardcoded
constant to a derived one. Matches the `knowledgebase.yml` precedent exactly.

### Interaction 2 — Q3 = A and Q4 = A compose into one delivery channel, and that is load-bearing

Structured logs (Q3) and EMF metrics (Q4) are **both just log records** on the same stdout channel. This
composition is why Q4 = A needs no new IAM permission and cannot throttle: emitting a metric is emitting a
log line, which the function already can do. It also means one formatter concern, not two subsystems.

Consequence to write down: the **CR-04 privacy rule extends to the metric line too.** EMF dimensions must
never carry a tag value (a NetID). Metric *dimensions* are `pages_fetched`, `resources_collected`,
`skipped_count`, snapshot age, outcome — none of which is a tag value — but a future contributor adding a
"top owner" dimension would leak a NetID into CloudWatch. Named for the pattern doc.

### Interaction 3 — Q1 = A and Q2 = A both bound the collector, and the boundary must be legible

Two independent stop conditions now guard the collector: the SDK's retry/timeout exhaustion (Q1 →
`UPSTREAM_THROTTLED`) and the context-derived deadline (Q2 → `UPSTREAM_TOO_SLOW`), on top of the 50-page
bound (CR-01 → `PAGE_LIMIT_EXCEEDED`). Three distinct named failures, plus the platform's own 120 s timeout
as a **last-resort unnamed** bound the design tries to keep from ever winning.

The design requirement this produces: **each of the three named bounds must be checked before the platform
timeout can fire**, and the reason code must identify which fired. This is exactly what P-3 asked for,
generalised — the pattern doc states the ordering (deadline checked at the top of each page loop, page
count checked per iteration, retry exhaustion surfaced from the SDK call) so no two bounds can be confused
in a log.

### Interaction 4 — Q5 = A and Q6 = A are the same discipline on two functions

Q5 makes the API total via one outer boundary; Q6 makes the collector fail cleanly with no silent retry.
Both express the unit's core stance — **a failure must be named and visible, never papered over**: the API
never leaks an unhandled exception (it becomes a generic 503), and the collector never hides a failed run
behind an automatic retry (it alarms, and the UI degrades to labelled stale per A-4). Recorded together
because they are one design principle applied at the two compute boundaries, and the pattern doc presents
them as such rather than as two unrelated error-handling choices.

**Nothing else changed.** No requirement, rule, entity or property was modified by this stage. The 49 NFR
requirements stand; TSD-8's mechanism is refined and annotated; RESILIENCY-04/-14/-15 remain discharged and
were not reopened.
