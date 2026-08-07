# Logical Components — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Design (artifact 2 of 2)
**Date**: 2026-08-03

Where U-01's `logical-components.md` stated plainly that a pure library contributes **no** infrastructure,
this one is a genuine inventory. It names each logical component, what it is, which NFR requirements and
rules it carries, and — critically — which decisions are **not settled here** but routed to Infrastructure
Design. It stops at the logical level: no ARNs, no property values, no template shape.

---

## 1. Component inventory

| # | Logical component | Kind | Created by this unit? | Carries |
|---|---|---|---|---|
| L-1 | **Collector function** (C-01) | Lambda, container image, arm64 | yes | CR-01..CR-06, P-1, P-3, S-1, R-1 |
| L-2 | **Snapshot bucket** (C-02) | S3, versioned, encrypted, BPA on | yes | SR-01, SR-02, D-1, D-2, D-7, SEC-1/-9 |
| L-3 | **Read API function** (C-03) | Lambda, container image, arm64 | yes | AR-01..AR-08, P-2, P-4, R-2 |
| L-4 | **HTTP API** | API Gateway HTTP API | yes | P-5, SEC-5, SEC-12, AR-01 |
| L-5 | **Distribution** (C-07) | CloudFront, two origins | yes | ER-03, ER-04, ER-05, P-6, P-7, SEC-2/-11 |
| L-6 | **Web ACL + IPSet(s)** (C-07) | WAF | yes | ER-01, ER-02, SEC-7, D-6 |
| L-7 | **Site bucket** (C-06 host) | S3, private via OAC | yes | ER-05, D-3, D-4, FR-4.2 |
| L-8 | **Collector schedule** | EventBridge rule/schedule → L-1 | yes | US-07, CR-01, Q6 async posture |
| L-9 | **Alarms** (C-09) | CloudWatch alarms | yes | R-3, R-4, R-5, R-6 |
| L-10 | **Log groups** | CloudWatch Logs (Lambda ×2, CloudFront, WAF) | yes | D-5, D-6, SEC-3, SEC-4, OR-06 |
| L-11 | **Metric namespace** | CloudWatch metrics via EMF | *implicit* (§5 of patterns) | R-8, CR-06 |
| L-12 | **Marker stack** (C-08) | CloudFormation `dashboard-marker` | already deployed | DR-01, DR-02, FR-6/-7 |
| **D-a** | **notify-topic** SNS topic | **dependency — not created here** | **no** | R-7, OR-05 |
| **D-b** | **`dashboard.core`** (U-01) | in-process Python import | **no — imported** | §4.5, all delegated derivations |

Two rows are **dependencies, not components**: `notify-topic` is created by its own pipeline-deployed
blueprint (D-a), and `dashboard.core` is U-01's library imported into both images (D-b). Both are drawn as
inbound arrows below, never as boxes this unit owns.

---

## 2. No queue, no cache, no circuit breaker (Q6 = A)

The mandated "logical components" examples are queues, caches, and circuit breakers. **U-02 has none, by
decision, and the reasons are on record:**

- **No DLQ / queue** — Q6 = A. The scheduled collector's async event is a bare tick carrying no replayable
  payload; re-running *is* just running again at the next tick. A DLQ would be infrastructure and an alarm
  surface for events that hold nothing worth replaying. `MaximumRetryAttempts: 0` + the OR-01 alarm is the
  posture.
- **No response cache in the API** — ER-03 fixes `/api/*` as no-cache; a cache would reintroduce two viewers
  disagreeing about freshness (the US-05 failure). CloudFront caches the *static site* only (P-6).
- **No circuit breaker** — one hourly upstream call and one per-request S3 read; there is nothing to isolate
  behind a breaker, and the SDK retry bound (§1 of patterns) plus the internal deadline (§2) already cap the
  one call that can be slow.

Stated explicitly so a reader does not wonder why the queues/caches section is empty — it is empty on
purpose, not by omission.

---

## 3. Data flow and trust boundaries

```
EventBridge schedule (L-8)
        │  async invoke, MaxRetryAttempts=0 (Q6)
        ▼
  Collector (L-1) ──imports──► dashboard.core (D-b, U-01)
        │  Resource Groups Tagging API (Config: timeouts + standard retries, §1)
        │  one PutObject, complete-or-fail (CR-05)
        ▼
  Snapshot bucket (L-2)  ◄── GetObject only, scoped to one key
        ▲                         │
        │ PutObject only          │
   C-01 role                 C-03 role         ← SR-02: two roles, one key each
                                  │
                                  ▼
                        Read API (L-3) ──imports──► dashboard.core (D-b)
                                  │  one GetObject/request; outer error boundary (§6)
                                  ▼
                        HTTP API (L-4)  throttle 20 rps (P-5)
                                  ▲
                                  │  /api/*  (no-cache, ER-03)
        Browser ──► CloudFront (L-5) ──► Site bucket (L-7, private, OAC)
                        ▲   default behaviour: cached static assets (P-6)
                        │
                   Web ACL (L-6)  deny-by-default, Cornell CIDRs only (ER-01)

  All functions ──EMF/JSON──► Log groups (L-10) ──► Metrics (L-11) ──► Alarms (L-9) ──► notify-topic (D-a)
```

**Trust boundaries that matter:**

- **The two S3 permissions are asymmetric and key-scoped** (SR-02): the collector role can `PutObject` the
  one snapshot key and nothing else; the API role can `GetObject` that one key and nothing else. Neither is
  bucket-wide. This is the least-privilege pattern (SEC-6) at the storage boundary.
- **The WAF fronts both origins** (ER-01): one deny-by-default control over the site *and* `/api/*`, rather
  than two controls that must agree. It is the unit's single entry boundary.
- **Same-origin `/api/*`** (Application Design Q4): no CORS surface, no credentials, no token (SEC-8, FR-4.5)
  — a boundary that does not exist cannot be misconfigured.
- **The collector's only egress** is the Tagging API and one S3 key; it reads no secrets and holds no
  credentials of its own (least-privilege execution role).

---

## 4. The U-01 ↔ U-02 interface, as U-02 consumes it (D-b)

Both container images import `dashboard.core`. U-02 consumes the flat `__all__` surface U-01's NFR Design
fixed — entities, the total `normalize_all`, the four derivations (`group_by_tag`, `classify_tag_gaps`,
`evaluate_freshness`, serialization), and the four `CoreError` types it must catch.

**The boundary is enforced, not documented**: `tools/check`'s grep forbids `boto3`, `botocore`, `os`,
`logging`, `datetime.now()`/`time.time()`, `assert`, and `print(` under `src/dashboard/core/`. A dependency
or a clock read appearing there is a **boundary violation caught by the gate**, not a dependency decision. So
the collector and API may configure boto3, read the clock (`get_remaining_time_in_millis`), and log — none
of which `core/` can do — while every *derivation* stays in the library. CR-03 and AR-04 (delegate every
derivation) are the runtime side of this same boundary.

---

## 5. Explicitly not settled here — routed to Infrastructure Design

NFR Design chose *patterns and logical components*. The following are the **resource-by-resource template
shape**, which is Infrastructure Design's job. Listed with owner so none reads as forgotten:

| Item | Why it is not settled here | Owner |
|---|---|---|
| **§6.4 site-sync ordering** | pipeline topology — likely Build emits the bundle as a CodePipeline artifact, synced at `RunOrder: 2` in `BlueprintDeploy` | Infrastructure Design |
| **WAF IPv6** (L-6) | IPSets are per-address-family; an IPv4-only allowlist silently locks out IPv6-only clients. Two IPSets or a documented IPv4-only scope | Infrastructure Design |
| **notify-topic ARN mechanism** (D-a) | its outputs carry no `Export:`, so `Fn::ImportValue` is unavailable — parameter or naming-convention construction | Infrastructure Design |
| **API reserved-concurrency number** (S-2) | a value, decided alongside the rest of the sizing | Infrastructure Design |
| **Exact CSP directive string** (L-5) | belongs with the response-headers policy; the *constraint* (no `unsafe-inline`/`unsafe-eval`) is fixed, the string is not | Infrastructure Design |
| **Two-template split** (`dashboard.yml` app + `dashboard-storage.yml` stateful) | which stack owns which resource is a template-shape decision; the *reason* (stateful buckets stay out of the stack updates replace) is settled | Infrastructure Design |

---

## 6. Component → requirement traceability (reverse check)

Every NFR requirement lands on at least one component above.

| Requirement group | Components |
|---|---|
| Performance P-1..P-7 | L-1, L-3, L-4, L-5, L-7 |
| Scalability S-1..S-5 | L-1 (S-1), L-3/L-4 (S-2 routed), managed (S-5) |
| Availability A-1..A-4 | L-1 + L-2 (A-4 degrade); rest recorded N/A |
| Durability D-1..D-7 | L-2 (D-1/-2/-7), L-7 (D-3/-4), L-10 (D-5/-6) |
| Security SEC-1..15 | L-2, L-3, L-5, L-6, L-10; SEC-8/-13 N/A by construction |
| Reliability/observability R-1..R-11 | L-1, L-3, L-9, L-10, L-11, D-a; R-11 N/A |

**No requirement is unassigned, and no component exists without a requirement.** L-12 (the marker) carries
the deployment-record requirements (DR-01/-02) and is already deployed; the only edit U-02 makes to it is
flipping `deployed_by: manual` → `pipeline` (DR-02) in the same change as the BlueprintDeploy action.
