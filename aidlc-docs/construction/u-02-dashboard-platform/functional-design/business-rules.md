# Business Rules — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Functional Design (artifact 2 of 4)
**Date**: 2026-08-03

Rules are prefixed by component. **U-01's BR-01..BR-08 are not restated** — U-02 calls them. Where a rule
below appears to be about grouping or freshness, it is about *transporting* U-01's answer, not producing
one.

Each rule names what it serves. Four rules discharge the obligations U-02 inherited.

---

## Collector — C-01

### CR-01 — Paginate to exhaustion, bounded
> Page until the upstream returns no continuation token, to a maximum of **50 pages** (Q1 = A).
> Exceeding it raises `PAGE_LIMIT_EXCEEDED`. **A partial result is never written.**

Serves FR-1.1, US-02. ~5,000 resources against a stated ceiling of tens-to-low-hundreds (§4.4): an order
of magnitude of headroom, while still bounding a runaway.

**The limit is an error, not a truncation.** Truncating would under-report while reporting success, which
is the failure the whole design is organized against.

### CR-02 — Bounded retries, then fail
> Explicit SDK connect/read timeouts. On throttling, retry with exponential backoff to a bounded count,
> then raise `UPSTREAM_THROTTLED`.

Serves RESILIENCY-10. Unbounded retry inside a scheduled Lambda is an unbounded bill.

### CR-03 — Normalize via U-01, never inline
> Every raw item goes through `dashboard.core.normalize_all`. C-01 does not parse ARNs, read tags, or
> deduplicate.

Serves §4.5 and the unit boundary. `normalize_all` is **total** — it cannot raise on a malformed item —
so one bad ARN cannot fail a collection (U-01's PAT-3).

### CR-04 — Log what U-01 cannot ⟵ **inherited obligation 3**
> When `skipped_count > 0`, C-01 logs one structured entry per skipped item containing the **reason code
> and the resource ARN**. It must **not** log tag values.

Serves SECURITY-04, US-12, and discharges obligation 3.

**Why C-01 and not U-01.** U-01's exceptions carry a category only, because `cornell:owner` holds a
**NetID** and an exception message can reach a log group or an error body. That was deliberate — and it
means *nothing in U-01 can say which resource was malformed*. If C-01 does not log it here, malformed
ARNs are undebuggable.

C-01 is the right place because it is the only component that can decide what is safe: it knows the log
group's retention and access, and it has the raw item in hand. **The ARN is logged; tag values are not.**
An ARN identifies the resource without carrying the NetID.

### CR-05 — One write, complete or not at all
> A single `PutObject` of a freshly built snapshot. **No read-modify-write.** On any failure, nothing is
> written and the previous snapshot survives.

Serves FR-1.1, US-02, RESILIENCY-12.

The absence of read-modify-write is load-bearing beyond safety: it is the reason U-01 can *ignore*
unknown top-level keys on read (BR-08) without ever losing one. If C-01 ever reads-then-writes, that
reasoning collapses and P1's scoping becomes wrong.

### CR-06 — Emit metrics on every outcome
> Duration, `pages_fetched`, `resources_collected`, `skipped_count`, and **snapshot age** — on success
> *and* failure where meaningful.

Serves US-14, RESILIENCY-05, and feeds OR-02's alarm.

---

## Snapshot store — C-02

### SR-01 — One fixed key, versioned, encrypted
> One object at a deterministic key. Bucket versioning on; encryption at rest; Block Public Access on;
> no public policy.

Serves SECURITY-01, SECURITY-09, FR-4.1, RESILIENCY-12. A fixed key means the reader needs no listing
and no "find the latest" logic; version history comes free.

### SR-02 — Two readers, no more
> `PutObject` from C-01's role only; `GetObject` from C-03's role only, scoped to that one key.

Serves SECURITY-06. Not bucket-wide: the API can read the snapshot and nothing else.

---

## Read API — C-03

### AR-01 — Closed route table
> Exactly five routes. Anything else is 404 **without touching S3**.

| Route | Derivation |
|---|---|
| `GET /api/inventory` | none — raw snapshot |
| `GET /api/groups/{tag_key}` | `group_by_tag`; `{tag_key}` validated against `REQUIRED_TAGS` |
| `GET /api/tag-gaps` | `classify_tag_gaps` |
| `GET /api/status` | `evaluate_freshness` + counts |
| `GET /api/health` | none |

Serves SECURITY-05, FR-3.1–3.3. `{tag_key}` is the **only** user-supplied value reaching logic, and it is
checked against a closed four-element allowlist — which is what makes input validation structural rather
than a layer to maintain.

### AR-02 — Read once, classify into three states
> One `GetObject` per request. Distinguish `PRESENT` / `ABSENT` / `UNREADABLE`.

Serves US-06. `ABSENT` is "the collector has never succeeded"; `UNREADABLE` is "the object exists and
does not parse". Collapsing them loses the distinction US-06 is about.

### AR-03 — The six-state response mapping ⟵ **inherited obligation 1**
> | Situation | HTTP | `status` | UI shows |
> |---|---|---|---|
> | Present, fresh | 200 | `ok` | data |
> | Present, stale | 200 | `stale` | data + prominent staleness notice |
> | Present, **zero resources** | 200 | `ok` | "no tagged resources found" |
> | Absent | 200 | `no_data` | "no data collected yet" |
> | Unreadable | 503 | `error` | generic failure |
> | **Present, `collected_at` in the future** | **503** | **`error`** | **generic failure** |

Serves US-06, FR-3.3, FR-3.4, and discharges obligation 1.

**The last row is the inherited one.** U-01's `Freshness` is three-valued: `INVALID` means the timestamp
is in the future, which cannot legitimately happen. It is a **fault, not a state of the world**, so it is
503 — not a 200 that would present data whose provenance is broken as if it were fine.

Rows 3 and 4 are the pair US-06 exists for: "no tagged resources found" and "no data collected yet"
render identically under a naive implementation and mean opposite things.

`no_data` is **200, not 404**: the request succeeded and the answer is "there is no snapshot yet". A 404
would suggest the endpoint is wrong.

### AR-04 — Delegate every derivation
> Grouping, gap classification and freshness come from `dashboard.core`. C-03 computes nothing.

Serves §4.5 and the boundary. A grouping loop in the handler means the boundary is gone.

### AR-05 — Counts in every response ⟵ **inherited obligation 2**
> Every `/api/*` response (except `/api/health`) carries `counts` with `resources`, `skipped`,
> `duplicates_removed`, `raw_returned`.

Discharges obligation 2. Not only on the inventory view: skipping is only honest where the count is
visible *wherever the data is*.

### AR-06 — Errors carry nothing
> Generic bodies. No stack trace, ARN, bucket name, key, account id, or path.

Serves FR-3.4, SECURITY-09. U-01 already refuses to put a NetID in an exception; C-03 must not undo that
by echoing the exception into a response.

### AR-07 — Never write, never trigger collection
> No route mutates anything or invokes C-01.

Serves FR-2.1, FR-4.5, US-07. Satisfied by there being no such code path, rather than by a check that
could later be removed.

### AR-08 — Health reports liveness, not data quality
> `/api/health` returns a static 200 without reading S3.

Serves RESILIENCY-06, Application Design Q6. It answers "is the function alive", so it stays green when
data is missing — which is correct, and is why it is not the staleness signal.

---

## Edge — C-07

### ER-01 — Deny by default
> One WAF web ACL, **default action Block**, allowing only the configured Cornell CIDR ranges. Covers the
> site *and* `/api/*`.

Serves FR-5.1, FR-5.2, SECURITY-07. One control rather than two that must agree.

### ER-02 — Ranges arrive as a parameter with no default
> A comma-separated CIDR parameter with `AllowedPattern` and **no `Default`**, split into the IPSet.

Serves FR-5.1 (Q3 = A). No default means a deploy that omits it **fails**, rather than admitting everyone
or nobody.

**Accepted consciously**: the real ranges live in `pipeline.yml`, which is public. CIDRs are not secrets
but are reconnaissance-useful.

**⚠️ Unresolved, and it is a lockout risk**: WAF IPSets are **per-address-family** — one set cannot hold
IPv4 and IPv6. An IPv4-only allowlist silently locks out IPv6-only clients, which is indistinguishable
from an outage to the person affected. Either two IPSets or a documented IPv4-only scope. **Owner:
Infrastructure Design** (Part A2 Interaction 3).

### ER-03 — `/api/*` no-cache; the site cached
> The `/api/*` behaviour disables caching. The default behaviour caches static assets.

Serves US-05. **Inverted, this serves stale JSON under a fresh-looking timestamp** — the exact failure
US-05 exists to prevent, and the price of putting both origins behind one distribution.

### ER-04 — HTTPS only, TLS 1.2+, security headers
> HTTP redirects to HTTPS. A response-headers policy sets CSP, HSTS, X-Content-Type-Options,
> X-Frame-Options, Referrer-Policy.

Serves SECURITY-02, SECURITY-11. The CSP permits **no** `unsafe-inline` and no `unsafe-eval`; the build
is configured to match rather than the header loosened to match the build.

### ER-05 — Private bucket via OAC
> The site bucket stays private; CloudFront reaches it with origin access control.

Serves FR-4.2, SECURITY-09.

### ER-06 — Log enough to diagnose a block
> CloudFront access logging and **WAF logging** enabled.

Serves FR-5.4, SECURITY-03, US-11. Without WAF logs a legitimate user blocked by ER-01 is
indistinguishable from an outage — and this is the design's most likely operational surprise.

---

## Observability — C-09

### OR-01 — Collector failure alarms on the first failure
> Alarm on ≥1 Lambda error in one period.

Serves US-13, RESILIENCY-07. The collector runs hourly; waiting for two doubles the blind window.

### OR-02 — Staleness alarm, `TreatMissingData: breaching`
> Alarm when snapshot age exceeds **3 × refresh interval** — the *same* threshold the UI uses. Missing
> data is **breaching**.

Serves US-13, US-05, RESILIENCY-07.

**Two things here are deliberate and neither is obvious.**

Sharing the threshold with the UI means the alarm and the screen can never disagree. "The dashboard says
stale but nothing alarmed" destroys trust in both.

`TreatMissingData: breaching` is what makes this alarm detect **a collector that never runs at all**. If
the schedule is disabled or its target permission breaks, there are zero invocations — so OR-01 stays
green, because nothing failed; nothing ran. The default (`missing`) would leave this alarm sitting in
`INSUFFICIENT_DATA`, which looks green forever. This is the only alarm covering that case
(Part A2 Interaction 1).

### OR-03 — Alarm on Lambda errors, throttles, and quota utilization
Serves RESILIENCY-07, RESILIENCY-09.

### OR-04 — Do NOT alarm on `skipped_count > 0`
> Skipped resources are surfaced in the UI and metrics. They do **not** raise an alarm.

Skipping is *designed-for* degradation with a visible count. Alarming on expected behaviour is how people
learn to ignore alarms.

### OR-05 — Alarms publish to the existing notify-topic
> Alarm actions target the SNS topic from `blueprints/notify-topic/`, not a new one.

That blueprint exists for exactly this and is actively pipeline-deployed; its `TopicArn` output is
documented as "ARN to publish to, **or to hand to another stack that needs to publish here**".

**Mechanism unresolved**: its outputs carry no `Export:`, so `Fn::ImportValue` is unavailable. Either a
parameter or construction from the naming convention. **Owner: Infrastructure Design**
(Part A2 Interaction 7).

### OR-06 — Structured JSON logs with retention
> Both functions log structured JSON; both log groups have explicit retention.

Serves SECURITY-04, US-12.

---

## Deployment — C-08, and the registry

### DR-01 — Marker records the deploying commit
Serves FR-6. Already implemented; carries all four `cornell:*` tags and a `DeploymentName` parameter.

### DR-02 — Flip the marker to `deployed_by: pipeline`
> When the BlueprintDeploy action is added, `dashboard-marker` changes from `manual` to `pipeline` **in
> the same change**.

Serves FR-7.1, FR-7.2. `validate_stacks.py` enforces both directions: `pipeline` with no action deploys
nothing while reporting success; `manual` with an action is also an error.

### DR-03 — Rollback is a revert; deployment is all-at-once
> Rollback = revert the PR and let the pipeline redeploy. Lambda deploys **by digest**, so a revert
> restores the exact previous image.

Serves RESILIENCY-04 (Q8 = A), discharging half of **obligation 4**.

Because storage is a separate stack, an application rollback **structurally cannot** touch snapshot or
site data. Noted honestly: `CLAUDE.md` now requires zero approving reviews, so the revert — and the
change that caused it — can be self-merged.

### DR-04 — A runbook, in the README
> `blueprints/dashboard/README.md` gains a runbook: what each alarm means and the first thing to check.
> Covers collector failure (**first step: was the page limit hit?**), staleness, **WAF lockout**, and
> unreadable snapshot.

Serves RESILIENCY-15 (Q9 = A), discharging the other half of **obligation 4**.

**The WAF-lockout entry is the one that has to exist**, and the README is the right home for a reason
worth stating: a deny-by-default failure looks exactly like an outage, and **the person locked out cannot
read the dashboard to diagnose it**. A runbook hosted on the thing it diagnoses is no runbook. GitHub is
reachable when CloudFront is not.

---

## Rule coverage

| Story | Rules |
|---|---|
| US-01 open from a Cornell network | ER-01..ER-06, AR-01 |
| US-02 see every tagged resource | CR-01, CR-03, CR-05, AR-01, AR-05 |
| US-06 honest answer when unavailable | AR-02, AR-03, AR-06 |
| US-07 refreshes itself | CR-01 (schedule), AR-07 |
| US-08 pull as JSON | AR-01 (`/api/inventory`) |
| US-09 supply-chain integrity | (Infrastructure Design / Code Generation) |
| US-11 access logging | ER-06 |
| US-12 application logging | CR-04, OR-06 |
| US-13 resiliency alarms | OR-01..OR-05 |
| US-14 operational monitoring | CR-06, OR-03, OR-06 |
| US-15 deploy through the pipeline | DR-01..DR-03 |

**Inherited obligations**: 1 → AR-03 · 2 → AR-05 · 3 → CR-04 · 4 → DR-03 + DR-04. All four discharged by
a named rule rather than an acknowledgement.

**No rule here duplicates or contradicts BR-01..BR-08.** Every derivation is delegated (CR-03, AR-04).

**Nothing here requires** a VPC, subnet, VPN, Direct Connect, Transit Gateway, or any identity system.
