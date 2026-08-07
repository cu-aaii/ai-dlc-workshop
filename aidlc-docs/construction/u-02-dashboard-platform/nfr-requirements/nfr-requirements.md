# NFR Requirements — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Requirements (artifact 1 of 2)
**Date**: 2026-08-03
**Decisions**: `construction/plans/u-02-dashboard-platform-nfr-requirements-plan.md` Part A2

Every requirement has an ID, a source, and a **verification column**. U-01's split was automated
vs. review-only; **U-02 needs a third category — `deployed`** — because many of these cannot be checked
by any amount of static analysis. Distinguishing them is the point: an NFR that only a deployment can
confirm should not sit in a table looking as settled as one `cfn-lint` enforces.

---

## Performance

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| P-1 | Collector: 512 MB, **120 s** timeout | Q1 | `cfn-lint` / template review |
| P-2 | API: 512 MB, **10 s** timeout | Q1 | template review |
| P-3 | Collector raises `UPSTREAM_TOO_SLOW` on an internal deadline **below** the Lambda timeout (≈100 s) | Part A2 Interaction 1 | **Automated** — unit test with a slow stubbed pager |
| P-4 | API cold start accepted; **no provisioned concurrency** | Q2 | template review (absence) |
| P-5 | API Gateway throttle **20 rps, burst 40**, as a parameter | Q3, FR-3.5, SECURITY-12 | template review |
| P-6 | Hashed assets cached long; `index.html` **60 s**; no invalidation step | Q4 | template review + **deployed** |
| P-7 | `/api/*` **no-cache** while the site is cached | ER-03, US-05 | **Automated** — template assertion |

**P-3 is the requirement this stage added.** Two bounds guard the collector — 50 pages and a 120 s
timeout — and only one of them is diagnosable. If the upstream slows past ~2.4 s per page the timeout
wins, and the failure becomes a bare platform timeout with no reason code: exactly what Functional
Design Q1 chose its answer to prevent. An internal deadline keeps every collector failure named.

**P-7 is a template assertion rather than a code test**, which is unusual and deliberate. Inverting the
cache policy serves stale JSON under a fresh timestamp — the US-05 failure — and nothing else in the
pipeline would catch it before deploy.

---

## Scalability and limits

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| S-1 | Collector reserved concurrency **1** | RESILIENCY-09 | template review |
| S-2 | API concurrency bounded (number at Infrastructure Design) | RESILIENCY-09 | template review |
| S-3 | Pagination bounded at **50 pages**; breach raises, never truncates | CR-01 | **Automated** — unit test |
| S-4 | Explicit SDK connect/read timeouts and bounded backoff | CR-02, RESILIENCY-10 | code review |
| S-5 | No autoscaling configuration — Lambda, S3, CloudFront and API Gateway scale without input | Q8 | N/A by design |

A scheduled collector needs exactly one concurrent execution. Bounding it caps both blast radius and
cost, which is the only scaling dimension this unit really has.

---

## Availability

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| A-1 | **Best-effort, single region, no SLA.** Availability is whatever the managed services provide | Q8, RESILIENCY-02 | N/A — recorded, not measured |
| A-2 | No multi-region, failover, or DR mechanism | Q8, RESILIENCY-02 | N/A |
| A-3 | No synthetic canary | RESILIENCY-06 | N/A — the endpoint is WAF-restricted and not publicly reachable |
| A-4 | Collector failure leaves the **previous snapshot intact**; the UI degrades to *labelled stale* | CR-05, US-05 | **Deployed** |

**A-1 is recorded precisely so a later reader does not assume an SLA exists.** Every component is already
multi-AZ without configuration, so there is nothing to build; and a total loss costs organizers a view
they can also obtain from the console.

**A-4 is the real availability property of this design** — not an uptime number, but that the failure mode
is visible staleness rather than invisible incompleteness.

---

## Durability and retention

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| D-1 | Snapshot bucket versioned, encrypted, Block Public Access on | SR-01, SECURITY-01/-09 | **Automated** — `cfn-lint` + review |
| D-2 | **Non-current** snapshot versions expire after **30 days** | Q6 | template review |
| D-3 | **Site bucket** objects not modified for 30 days expire | Part A2 Interaction 2 | template review |
| D-4 | Site sync runs **without `--delete`** | Part A2 Interaction 2, Q4 | pipeline review |
| D-5 | Lambda log groups: **30 days** retention, explicit | Q5, SECURITY-04, US-12 | **Automated** |
| D-6 | CloudFront and WAF logs: **30 days** retention | Q5, SECURITY-03, US-11 | template review |
| D-7 | Snapshot declared `state: derived` — nothing here needs backup | Q9c of Units Generation | manifest review |

**D-3 closes a gap my own Q6 left**: it asked about snapshot versions and stopped, but content-hashed
assets accumulate on every deploy too.

**D-4 is a requirement not to do something.** Deleting old assets on sync would break any browser
mid-rollout still holding a cached `index.html` — the failure Q4's design exists to avoid. The 30-day
lifecycle is the right cleanup mechanism; `--delete` is not.

**D-6 is a privacy decision, not a cost one.** Access logs contain source IPs. Lambda logs, by CR-04's
design, contain ARNs and reason codes but **no tag values and therefore no NetIDs**.

---

## Security

Mapping §4.1's rules onto the component that satisfies each. The rules are not restated; their owners are.

| ID | Requirement | Rule | Owner | Verified by |
|---|---|---|---|---|
| SEC-1 | Encryption at rest | SECURITY-01 | C-02 | **Automated** |
| SEC-2 | HTTPS only, TLS 1.2+, HTTP redirected | SECURITY-02 | C-07 | template review |
| SEC-3 | Access logging incl. WAF | SECURITY-03 | C-07 | template review |
| SEC-4 | Structured application logging | SECURITY-04 | C-01, C-03 | code review |
| SEC-5 | Request validation via a closed allowlist | SECURITY-05 | C-03 | **Automated** — property test on `route` |
| SEC-6 | Least-privilege IAM, per function, scoped to one key | SECURITY-06 | C-01, C-03 | template review |
| SEC-7 | **Deny-by-default** WAF allowlist over site and API | SECURITY-07, FR-5.1/5.2 | C-07 | **Deployed** |
| SEC-8 | No CORS surface — same-origin by construction | SECURITY-08 | C-07 | N/A by design |
| SEC-9 | No internals in error bodies; Block Public Access | SECURITY-09 | C-03, C-02 | **Automated** + review |
| SEC-10 | Supply chain: Python and images pinned/scanned/SBOM'd; **npm pinned only** | SECURITY-10, Q11 = B | all | see `tech-stack-decisions.md` |
| SEC-11 | Security response headers, strict CSP | SECURITY-11 | C-07 | **Automated** — template assertion |
| SEC-12 | Rate limiting | SECURITY-12 | C-03 | template review |
| SEC-13 | No identity system | accepted exception §4.6 | — | N/A |
| SEC-14 | JSON only; no CDN scripts so nothing needs SRI | SECURITY-14 | C-01, C-03, C-06 | **Automated** — grep |
| SEC-15 | Fail closed: partial results never presented as complete | SECURITY-15 | C-01 | **Automated** — P8 + unit tests |

**SEC-7 can only be verified by deploying.** A deny-by-default allowlist either admits the right people or
it does not, and no template review establishes which — this is the item most likely to look like an
outage, and the reason DR-04's runbook needs its WAF entry.

**SEC-11's CSP** permits no `unsafe-inline` and no `unsafe-eval`. Vite's modulepreload polyfill emits an
inline script by default and must be disabled — the build is configured to satisfy the header, not the
reverse.

---

## Reliability and observability

| ID | Requirement | Source | Verified by |
|---|---|---|---|
| R-1 | Collector: complete-or-fail; one `PutObject`; no read-modify-write | CR-05, SECURITY-15 | **Automated** |
| R-2 | `api.handler` is **total** — no path escapes without a response | Functional Design totality table | **Automated** |
| R-3 | Collector failure alarms on the **first** failure | OR-01, US-13 | template review |
| R-4 | Staleness alarm at **3 × interval**, `TreatMissingData: breaching` | OR-02 | template review |
| R-5 | Alarms on Lambda errors, throttles, quota utilization | OR-03, RESILIENCY-07 | template review |
| R-6 | **No** alarm on `skipped_count > 0` | OR-04 | review (absence) |
| R-7 | Alarms publish to the existing `notify-topic` | OR-05 | template review |
| R-8 | Metrics: duration, pages, resources, skipped, snapshot age | CR-06, US-14, RESILIENCY-05 | **Deployed** |
| R-9 | Rollback = revert the PR; all-at-once; deploy **by digest** | DR-03, RESILIENCY-04 | process |
| R-10 | Runbook in the README covering collector failure, staleness, **WAF lockout**, unreadable snapshot, and **first-deploy-without-images** | DR-04, RESILIENCY-15, Part A2 Interaction 4 | review |
| R-11 | Distributed tracing **not applicable** | RESILIENCY-05 | N/A — recorded |

**R-4's `TreatMissingData: breaching` is the single most important line in this table.** A collector that
never *runs* emits no metric and no error, so R-3 stays green — nothing failed; nothing ran. With the
default (`missing`), this alarm would sit in `INSUFFICIENT_DATA` looking green forever. It is the only
alarm that detects that case.

**RESILIENCY-04, -14 and -15 are discharged, not open**: -14 at U-01's NFR Design (the property suite),
-04 and -15 here via R-9 and R-10. Deferral count stopped at 2.

---

## Explicitly N/A

| Category | Why |
|---|---|
| Autoscaling, sharding, partitioning | Managed services scale without configuration; the only useful bound is downward (S-1, S-2) |
| Multi-region, DR, failover | RESILIENCY-02: snapshot rebuildable, RTO/RPO N/A |
| Authentication, authorization, sessions | No identity system anywhere (FR-5.5) |
| Database selection, schema, migrations | No database — one S3 object |
| Messaging, queues, async processing | None; collector scheduled, API synchronous |
| Accessibility targets | **Not ours to set.** `contracts/ui-design-language.md` §2 fixes WCAG 2.2 AA with no exemption path |
| PBT properties for U-02 | Mostly I/O; property tests over mocks test the mocks (Functional Design) |
| Cost budget | Estimated at Units Generation; Q1–Q6 move it by cents. Q2's rejected option B would have roughly doubled it |

---

## Verification summary

| | Count |
|---|---|
| Automated (`cfn-lint`, `tools/check`, unit tests, template assertions) | **14** |
| Review-only | **19** |
| **Deployed** — verifiable only against a running stack | **4** |
| N/A by design, recorded | **12** |
| **Total** | **49** |

**The four `deployed` rows are the honest weak point of this unit**, and they are not minor: SEC-7 (the
allowlist actually admits the right people), A-4 (a collector failure really does degrade to labelled
stale), P-6 (the cache behaves), and R-8 (metrics arrive). U-01 finished with 60 executed tests and a 9/9
mutation score. **U-02 cannot reach that standard without a merge to `main`, which deploys to the shared
account** — and that asymmetry should be stated rather than smoothed over when U-02's Build and Test
reports.

Review-only outnumbering automated is a property of the unit, not a shortfall in effort: most of U-02 is
CloudFormation, and `cfn-lint` checks that a template is *valid*, not that a cache policy is the right way
round.
