# Services — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 3 of 5)
**Date**: 2026-08-03

A *service* here is a unit of behaviour with its own trigger, lifecycle, and failure domain — not a
deployment artifact. Two of them exist, and the whole design rests on their being separate.

---

## Service map

| ID | Service | Trigger | Components | Failure domain |
|---|---|---|---|---|
| S-01 | Collection Service | EventBridge schedule | C-01, C-04, C-02 (write) | Own. Failure leaves the last good snapshot in place. |
| S-02 | Query Service | HTTP request via C-07 | C-07, C-03, C-04, C-05, C-02 (read), C-06 | Own. Failure means no answers, but no data loss. |

They share exactly one thing: the snapshot object (C-02). That is the entire coupling surface.

---

## S-01 — Collection Service

**What it is for**: the account's tagged inventory becomes knowable without anyone opening a console.

**Lifecycle**
1. EventBridge fires on the configured interval (a stack parameter — FR-2.3)
2. C-01 paginates the Tagging API to exhaustion
3. C-04 normalizes, stamps, and serializes
4. One `PutObject` to C-02
5. Metrics emitted; the invocation ends

**Success** is a complete snapshot written. **Failure** is an exception — no partial write, ever.

**Why failure is designed this way**: the alternative — write what you got — produces a snapshot that
looks fresh and is wrong. A viewer cannot tell. A stale snapshot, by contrast, is *labelled* stale
(FR-2.2, US-05), so the user knows what they are looking at. Preferring visible staleness to
invisible incompleteness is the central resiliency choice in this blueprint, and it is what
RESILIENCY-15's graceful-degradation intent means concretely here.

**Bounded on purpose**: concurrency 1 (RESILIENCY-09), explicit SDK timeouts, bounded retries with
backoff (RESILIENCY-10), and a page limit whose breach is an error rather than a truncation. A
scheduled job with no bounds is a cost incident waiting for an upstream slowdown.

**Upstream dependency it does not control**: the Resource Groups Tagging API. It can throttle, and it
is eventually consistent — a resource created seconds ago may not appear. This is a property of the
data source, not a defect, and the design's answer is the visible `collected_at` rather than a
promise of real-time accuracy the blueprint cannot keep.

---

## S-02 — Query Service

**What it is for**: turning the stored snapshot into the four views, on demand, for anyone inside the
allowlist.

**Lifecycle**
1. Request arrives at C-07; WAF evaluates it — **default block** (FR-5.1)
2. Path routes: `/api/*` → API Gateway → C-03; everything else → S3 (C-06)
3. C-03 matches the route table; unmatched paths 404 without reading S3
4. C-03 reads the snapshot once and classifies the outcome into three states
5. C-05 derives the requested view; C-03 shapes the response with status code **and** body status
6. C-06 renders it, including the degraded cases

**Read-only by construction.** No method on any component in this service writes anything. FR-2.1 and
US-07 are satisfied by there being no write path to omit, rather than by a check that could be
removed later.

**The cache obligation, again**: `/api/*` no-cache, site behaviour cached. This service is where an
inverted cache policy does its damage — CloudFront would serve a stale JSON body carrying a stale
`collected_at`, and the staleness notice would be correct about the *snapshot* while lying about
*when the reader last looked*. Two viewers would then disagree, which is exactly what Q8 = A's
server-side judgement was chosen to prevent.

**Bounded on purpose**: API Gateway throttling (FR-3.5, SECURITY-12), Lambda concurrency capped
(RESILIENCY-09), SDK timeouts explicit (RESILIENCY-10). The rate limit is not anti-abuse theatre —
the allowlist admits a whole network, so an accidental refresh loop from one workstation is the
realistic threat, not an attacker.

---

## The invariant between them

> **A read never causes a write. A write never waits for a read.**

Which yields:

- Load on S-02 cannot increase Tagging API cost or trip its throttles
- S-01 failing does not make S-02 fail — it makes S-02 *report* staleness
- S-02 failing does not lose data; the snapshot keeps being written
- Neither service needs to know the other is running

The single shared object is the seam, and it is a plain S3 key. That is what makes each one testable
alone: S-01 against a bucket, S-02 against a fixture object, and C-04/C-05 against neither.

---

## Deployment services (supporting, not runtime)

Not services of the blueprint, but the blueprint does not exist without them.

| Concern | Where it lives | Note |
|---|---|---|
| Container image build | New Build stage action in `pipeline/pipeline.yml` | `ContainerBuildProject` and `ContainerRepository` are defined and known-good but **no stage invokes them** — `CLAUDE.md` states this outright, so the finding raised at Workflow Planning is corroborated by the repo's own documentation, not just by my reading of the template. Wiring is a Build stage action plus a Dockerfile. **⚠️ SUPERSEDED — see `inception/amendments/repo-baseline-2026-08-03.md` §A1.2.** A `Build` stage now exists and invokes `ArmContainerBuildProject`; the dashboard adds an **action to an existing stage**, not a new stage. A root `Dockerfile` with one named target per component is the established pattern. |
| Site build + upload | The **same** Build stage action | Q10 = A. Vite build, then `aws s3 sync` to the site bucket. One `pipeline.yml` edit for both, per the execution plan's coordination point. |
| Stack deployment | New BlueprintDeploy action + `pipeline/stacks.yml` entry | FR-7. A registry entry without a matching action deploys nothing while reporting success. |
| Pre-push validation | `tools/check` | Stays `uv`-only. Node is **not** added to it, so template-only contributors are unaffected. |

**Ordering constraint**: the images and the site bundle must exist before the stack that references
them deploys. The Build stage therefore precedes BlueprintDeploy. Getting this backwards yields a
CloudFormation failure about a missing image tag, which reads like a template bug rather than a stage
ordering bug — worth stating because that misdiagnosis is expensive.

**One open sequencing question, deferred to Infrastructure Design**: `aws s3 sync` needs the site
bucket to exist, but the bucket is created by the stack the Build stage precedes. Either the bucket
moves to a separately-deployed stack, or the sync moves after BlueprintDeploy, or the bucket name is
resolved at sync time from a known convention. This is genuinely an infrastructure-topology decision
and is recorded rather than guessed here.

---
---

# FR-9 / FR-10 extension (2026-08-07)

Three flows are added. The v1 inventory flow is unchanged.

## Flow 4 — Daily cost collection (C-10)

```
EventBridge (daily, stack parameter)
  └─> C-10 Cost Collector
        ├─> ce:GetCostAndUsage  x N   (N bounded and counted -- $0.01 each)
        │     ├─ windows: day / month-to-date / year-to-date        (US-16)
        │     ├─ GROUP BY SERVICE                                    (US-16)
        │     ├─ GROUP BY USAGE_TYPE   -> per-model cost             (A3.4)
        │     └─ GROUP BY TAG cornell:blueprint / :deployment-id     (US-17)
        ├─> C-12.split_attribution()  -- "cornell:blueprint$" => UNATTRIBUTED, not a group name
        ├─> EMF: ce_calls, outcome, unattributed_fraction
        └─> ONE PutObject -> cost/current.json          (complete-or-fail, no RMW)
```

**Orchestration rule**: any CE call failing fails the whole run and writes **nothing** — the previous
`cost/current.json` survives and the next day retries, exactly as C-01 treats inventory (A-4,
SECURITY-15). A partially-populated cost object would be worse than a stale one, because the missing
groups would read as zero spend.

## Flow 5 — Hourly telemetry collection (C-11)

```
EventBridge (hourly)
  └─> C-11 Telemetry Collector
        ├─> cloudwatch:ListMetrics    -> ModelId VALUES only (never which metrics)
        ├─> cloudwatch:GetMetricData
        │     ├─ FIXED allowlist: AWS/Bedrock, AWS/Bedrock-AgentCore      (A3.1, A3.2)
        │     └─ catalog-declared only: Cornell/Blueprints/*              (NFR-T5)
        ├─> C-13.classify() per counter -> NOT_INSTRUMENTED / NO_DATA_YET / CANNOT_READ / OK
        └─> ONE PutObject -> telemetry/current.json
```

**Orchestration rule, and it differs from Flow 4 deliberately**: the two halves are **independent**.
If `Cornell/Blueprints/*` cannot be read, the AWS half still writes, and vice versa — each counter
carries its own state. Failing the whole run would erase real AWS data because an uninstrumented
namespace returned nothing, which is the opposite of the honesty NFR-T7 requires.

## Flow 6 — Read-time composition (C-03)

```
Browser -> C-07 edge -> API Gateway -> C-03
  ├─> load inventory/current.json    (may be ABSENT/UNREADABLE -- independent)
  ├─> load telemetry/current.json    (independent)
  ├─> load cost/current.json         (independent)
  ├─> C-12.estimate_model_cost(tokens from telemetry, rates from SSM)   <- FR-10.6, at read time
  ├─> C-13 derivations (rates, per-agent aggregation)
  └─> response: per-section data + per-section collected_at + per-section state
```

**The rate table** is read from SSM (`/<app>/<env>/dashboard/model-rates`) and cached per invocation.
A missing or malformed table yields C-12's missing-rate result and the *not instrumented* state for
estimated cost — **never** a zero price (FR-10.6.6, NFR-T2).

**Why estimation is read-time, not collection-time**: it mirrors the v1 decision (Q2 = A, "aggregation
at read time; the snapshot holds raw data"). Storing an estimate would freeze it against the rate table
in force at collection, so correcting a wrong rate would not correct history. Rates change; tokens do
not.

## Service boundaries — what must not happen

| Rule | Why |
|---|---|
| No writer reads another writer's object | Keeps every write complete-or-fail; removes the lost-update race that made Q1 = A necessary |
| A read never triggers a collection | v1's invariant (FR-2.1, US-07), unchanged and now covering three sections |
| No section's failure degrades another | US-16/US-17 must be able to show cost while usage is uninstrumented, and vice versa |
| Rates are never baked into stored data | NFR-T2 — configuration must be correctable without a redeploy or a rewrite |
| The CE call count is bounded and emitted | NFR-T8 — a cost dashboard must be able to prove it is not itself a material cost |
