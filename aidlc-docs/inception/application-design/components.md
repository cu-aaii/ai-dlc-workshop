# Components — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 1 of 5)
**Date**: 2026-08-03
**Resolved decisions**: `inception/plans/application-design-plan.md` Part A2 (Q1–Q8) and
`application-design-plan-clarification.md` (Q9 = React + Vite, Q10 = pipeline Build stage,
Q11 = npm pinned but not scanned)

---

## Component inventory

| ID | Component | Kind | New / Existing |
|---|---|---|---|
| C-01 | Tag Inventory Collector | Lambda (container image) | New |
| C-02 | Snapshot Store | S3 object | New |
| C-03 | Inventory Read API | Lambda (container image) + API Gateway HTTP API | New |
| C-04 | Inventory Model | Pure Python module (no AWS) | New |
| C-05 | Aggregation Core | Pure Python module (no AWS) | New |
| C-06 | Web UI | React + Vite static bundle in S3 | New |
| C-07 | Edge | CloudFront distribution + WAF web ACL + response headers policy | New |
| C-08 | Deployment Marker | CloudFormation resources (repurposed) | **Existing artifact, repurposed** (FR-6) |
| C-09 | Observability Set | CloudWatch alarms, metrics, log groups, dashboard | New |
| — | `pipeline/stacks.yml` | Registry entry | **Existing shared file, edited** |
| — | `pipeline/pipeline.yml` | Build stage action + BlueprintDeploy action | **Existing shared file, edited** |

C-04 and C-05 are called out as first-class components rather than "helper code" because
`requirements.md` §4.5 and every PBT property in §4.2 depend on their existence as units separable
from AWS. If they are not components, PBT-01..10 has nothing to attach to.

---

## C-01 — Tag Inventory Collector

**Purpose**: produce a complete, timestamped snapshot of every `cornell:*`-tagged resource in the
account, on a schedule.

**Responsibilities**
- Call the Resource Groups Tagging API and **paginate to exhaustion** (FR-1.1, §4.4)
- Normalize each raw result into a stable record shape — delegated to C-04, not done inline
- Stamp the collection time and schema version
- Write the snapshot to C-02 as one object
- Fail loudly and completely rather than writing a partial snapshot (US-02, SECURITY-15)

**Explicitly not responsible for**
- Grouping, tag-gap classification, or staleness judgement — all read-time under Q2 = A
- Serving anything to anyone

**Interfaces**
- *In*: EventBridge scheduled event. Interval is a stack parameter (FR-2.3), not hardcoded.
- *Out*: one S3 `PutObject` to C-02; structured JSON logs; custom metrics
- *Depends on*: Resource Groups Tagging API (upstream, outside this account's control), C-02, C-04

**Constraints carried**
- Container image, base pinned by digest (repo constraint, SECURITY-10)
- IAM limited to `tag:GetResources` plus write to the one snapshot key. `tag:GetResources` cannot be
  ARN-scoped — the accepted exception in `requirements.md` §4.6(2), not an oversight.
- Explicit SDK timeouts, bounded retries with backoff on throttling (RESILIENCY-10)
- Reserved/maximum concurrency set (RESILIENCY-09) — a scheduled collector needs 1, and bounding it
  bounds both blast radius and cost

**The failure mode this component exists to avoid**: silently stopping at page 1. That under-reports
inventory while looking successful, which §4.4 calls worse than failing.

---

## C-02 — Snapshot Store

**Purpose**: hold the current snapshot durably and let exactly one reader read it.

**Design**: a single versioned, encrypted JSON object in S3 (Q1 = A).

**Responsibilities**
- Durability and encryption at rest (SECURITY-01)
- Version history, which comes free from bucket versioning (RESILIENCY-12)
- Nothing else. It is passive storage with no logic.

**Interfaces**
- *In*: `PutObject` from C-01 only
- *Out*: `GetObject` to C-03 only
- No public access; Block Public Access on (SECURITY-09)

**Schema obligations** (FR-2.4, and the queued telemetry amendment)
- A top-level `schema_version` so a later reader can tell what it is looking at
- `collected_at` at the top level, since every response must expose it (FR-2.2)
- `resources`: the raw inventory list
- Room for a sibling top-level key — `costs`, `metrics` — added without restructuring. This is what
  makes FR-2.4 and the telemetry amendment's "other metrics later" cheap rather than a migration.

**Deliberately absent**: no query capability. The API reads the whole object. At the expected volume
(§4.4: tens to low hundreds of resources) that is the right trade; at ten thousand it would not be,
and that threshold is recorded here so a future reader knows when to revisit rather than discovering
it as a performance surprise.

---

## C-03 — Inventory Read API

**Purpose**: serve the stored snapshot, and views derived from it, as JSON.

**Design**: one Lambda behind an API Gateway HTTP API (Q3 = A), reached through C-07 at `/api/*`
(Q4 = A), with distinct paths per view (Q5 = A).

**Responsibilities**
- Read the current snapshot from C-02 — **and classify the outcome**, since US-06 needs four
  distinguishable states rather than success/failure
- Delegate all grouping, classification, and staleness judgement to C-05
- Shape HTTP responses: status code plus a body status field (Q8 = A)
- Validate requests against the route table (SECURITY-05, made largely structural by Q5 = A)
- Serve `/api/health` from this same function and role (Q6 = A)

**Explicitly not responsible for**
- Triggering collection. A read never causes a write (FR-2.1, US-07) — this is an invariant, not a
  preference.
- Computing anything itself. The API is orchestration; the logic is C-05.

**Interfaces**
- *In*: HTTP via API Gateway, only ever through C-07
- *Out*: JSON responses; structured JSON logs; custom metrics
- *Depends on*: C-02 (read), C-04 (deserialize), C-05 (derive)

**Constraints carried**
- Container image, digest-pinned base (repo constraint)
- IAM limited to `GetObject` on the one snapshot key — no bucket-wide read
- API Gateway throttling satisfies FR-3.5 / SECURITY-12 directly
- Generic error bodies; no stack traces, ARNs, paths, or account identifiers (FR-3.4, SECURITY-09)
- Explicit SDK timeouts (RESILIENCY-10); concurrency bounded (RESILIENCY-09)

---

## C-04 — Inventory Model (pure)

**Purpose**: define what a resource record and a snapshot *are*, and convert between them and bytes.
No AWS SDK, no network, no clock.

**Responsibilities**
- The record and snapshot types
- Normalizing a raw Tagging API result into a record
- Serializing a snapshot to bytes and deserializing it back
- JSON only — no `pickle`, no `yaml.load` (SECURITY-14)

**Why it is a component**: it is the round-trip property's subject. `deserialize(serialize(s)) == s`
is an assertion about this module and nothing else, which is only possible because it has no AWS
dependency. Under Q1 = A the snapshot is one object, so that property is about bytes rather than
about a schema mapping — the cleanest form it could take.

**Interfaces**: called by C-01 (build, serialize) and C-03 (deserialize). Depends on nothing in this
blueprint.

---

## C-05 — Aggregation Core (pure)

**Purpose**: every derivation the UI needs, as pure functions over a snapshot. No AWS, no network.
The clock is passed in, never read.

**Responsibilities**
- Group by `cornell:deployment-id`, `cornell:owner`, `cornell:blueprint` (FR-1.3, US-03), including
  the explicit "missing this tag" group so no resource is dropped from a view
- Classify tag gaps — which of the four required tags each resource lacks (FR-1.4, US-04)
- Evaluate freshness: given `collected_at`, a supplied `now`, and a threshold, return a verdict

**Why freshness lives here**: Q8 = A makes staleness a **server** judgement so two views on one
snapshot agree (US-05). Putting it in a pure function with an injected clock makes that judgement
testable without waiting for time to pass.

**PBT targets** (§4.2 candidate properties, now with a concrete home)
- *Invariant*: grouped counts sum to the ungrouped total; every resource in exactly one group; no
  empty groups
- *Oracle*: grouping matches a naive reference implementation
- *Easy-verification*: the gap classifier flags exactly those resources lacking ≥1 required tag
- *Idempotence*: grouping a grouped result changes nothing

**Interfaces**: called by C-03 only. Depends on C-04's types.

---

## C-06 — Web UI

**Purpose**: render the inventory, the three groupings, tag gaps, freshness, and the degraded states.

**Design**: React + Vite (Q9 = B), built in the pipeline (Q10 = A), served as static files from S3
through C-07.

**Responsibilities**
- The four views: inventory, grouping, tag gaps, and status
- Display `collected_at` without the user hunting for it (US-05)
- Render all four of US-06's states distinguishably — including "no data collected yet" as visibly
  different from "no resources found", which is the mistake that story exists to prevent
- Call `/api/*` same-origin; no credentials, no login, no SigV4 (FR-4.5)

**Build constraints**
- No `unsafe-inline`, no `unsafe-eval` in the CSP (US-01). Concretely for Vite: the modulepreload
  polyfill emits an inline script by default, so it must be disabled or hash-allowlisted. Recorded
  here because "keep the CSP strict" is not actionable and "disable the polyfill" is.
- `package-lock.json` committed with integrity hashes (Q11 = B)
- No third-party CDN scripts — nothing to add SRI to (SECURITY-14)

---

## C-07 — Edge

**Purpose**: the single front door, and the only access control this blueprint has.

**Design**: one CloudFront distribution with two origins (Q4 = A) — S3 for the site, API Gateway for
`/api/*` — plus a WAF web ACL and a response headers policy.

**Responsibilities**
- Admit only allowlisted Cornell ranges; **default action block** (FR-5.1, SECURITY-07)
- Cover the API path with the same ACL (FR-5.2) — one control, not two that must agree
- HTTPS only, TLS 1.2+, HTTP redirected (SECURITY-02)
- Set CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy (SECURITY-11)
- Reach the S3 origin via origin access control; the bucket stays private (FR-4.2)
- Access logging, including WAF logs, so a block is diagnosable (SECURITY-03, US-11)

**The cache obligation**: `/api/*` must be **no-cache** while the site behaviour is cached. Inverted,
this serves stale JSON under a fresh-looking timestamp — the precise failure US-05 exists to prevent,
and the one thing Q4 = A buys convenience at the cost of. It is stated here, in
`component-dependency.md`, and in the consolidated design, because it is easy to get wrong and
silent when wrong.

**What it is not**: authentication. It admits by network position, not identity (FR-5.5, and
`personas.md`). The accepted SECURITY-13 exception rests entirely on this component.

---

## C-08 — Deployment Marker

**Purpose**: satisfy FR-6 — repurpose `blueprints/dashboard/infra/hello-world.yml` rather than delete
it.

**Responsibilities**: carry the blueprint's identity as deployed — `cornell:blueprint` corrected from
`hello-world` to `dashboard`, description rewritten, `cornell:blueprint-version` reset, and the
resources renamed out of the `hello-world` namespace.

Recorded as a component rather than a chore because R1-Q6 = B made keeping it an explicit
requirement, and a reviewer who does not know that will read it as a leftover and delete it.

---

## C-09 — Observability Set

**Purpose**: make the two silent degradations visible — collector failure and snapshot staleness.

**Responsibilities**
- Alarms: collector failure, snapshot staleness, Lambda errors/throttles, quota utilization (US-13,
  RESILIENCY-07)
- Metrics: latency, error rate, throughput, invocations for both functions (US-14, RESILIENCY-05)
- A health dashboard definition (US-14)
- Log groups with retention for both functions (US-12, SECURITY-04)

Distributed tracing is **not applicable** and recorded as such rather than left unaddressed
(RESILIENCY-05). This is *this blueprint's* observability, not the platform-wide `observability/`
component, which stays unbuilt.

---

## Existing shared files edited

Neither is a component of this blueprint, but both must change for it to exist at all.

- **`pipeline/stacks.yml`** — register the template(s), in the same PR (FR-7.1)
- **`pipeline/pipeline.yml`** — a matching BlueprintDeploy action (FR-7.2; its absence deploys
  nothing while reporting success), plus a **Build stage action** covering both the container images
  and the Vite site build with `s3 sync` (Q10 = A, and the gap the execution plan identified). One
  edit, not two.

`CLAUDE.md` permits changing the pipeline's *shape* for a blueprint that needs it, while forbidding
"improvements" to the source stage, artifact handling, role assumptions, and the digest export. Only
the additions above are in scope.

---
---

# FR-9 / FR-10 extension (2026-08-07)

**Source**: `amendments/telemetry-fr9-2026-08-07.md` (A2) as corrected by
`amendments/telemetry-a3-measured-2026-08-07.md` (A3). **Decisions**:
`plans/application-design-plan-fr9-fr10.md` Part A2 (Q1 = A one object per section, Q2 = A baked
catalog + fixed AWS allowlist, Q3 = B reuse the collector image, Q4 = A extend both units).

Nothing in C-01…C-09 above is revisited. Five components are added and four are extended.

## New component inventory

| ID | Component | Kind | Unit |
|---|---|---|---|
| C-10 | Cost Collector | Lambda (container image, 3rd target) | U-02 |
| C-11 | Telemetry Collector | Lambda (container image, 4th target) | U-02 |
| C-12 | Cost Model + Estimator | Pure Python (no AWS) | **U-01** |
| C-13 | Telemetry Model | Pure Python (no AWS) | **U-01** |
| C-14 | Declared-Counter Catalog | Build-time JSON artifact + pure parser | U-01 parser, pipeline build step |

## C-10 — Cost Collector

**Purpose**: read platform cost from Cost Explorer once a day and write it as its own object.

**Responsibilities**
- Call `ce:GetCostAndUsage` for the three windows US-16 needs (day, month-to-date, year-to-date)
- Group by `SERVICE`, by `USAGE_TYPE` (per-model cost — A3.4), and attempt the `cornell:blueprint` /
  `cornell:deployment-id` **TAG** groupings
- **Classify the empty-value tag group as unattributed** (FR-10.3.6) — the A3.3 trap. A successful
  response containing one group keyed `cornell:blueprint$` is 100% unattributed spend, *not* a
  blueprint named `cornell:blueprint`. This classification is the component's most important job.
- Stamp `collected_at` and the CE window actually covered, which is **not** "today" (24–48h lag)
- Write `cost/current.json` in **one** `PutObject`, complete-or-fail

**Explicitly not responsible for**
- Estimating model cost — that is C-12, and it needs token counts C-11 collects
- Any tag activation. It **cannot** activate cost allocation tags; this is a linked account and only
  the Organization payer can (A3.3). It detects and reports the consequence.

**Interfaces**
- *In*: EventBridge, **daily**, cadence a stack parameter (FR-10.4.3)
- *Out*: one `PutObject` to `cost/current.json`; JSON logs; EMF metrics
- *Depends on*: Cost Explorer (upstream), C-02, C-12

**Constraints carried**
- Same image as C-01, new Dockerfile target + `CMD` (Q3 = B)
- IAM: `ce:GetCostAndUsage` only, plus write to the one cost key. `ce:*` has no resource-level
  scoping — a **documented exception** in the same shape as `tag:GetResources` (NFR-T6)
- Reserved concurrency 1; a daily collector needs no more
- **Call budget is a design constraint, not a detail**: every request is $0.01 against a ~$9/month
  account (A3.6). The number of CE calls per run MUST be bounded and counted, and the count emitted
  as a metric so the dashboard's own cost is observable (NFR-T8, Q8)

**The failure mode this component exists to avoid**: rendering `cornell:blueprint$` as a real
attribution. That produces a confident, wrong money figure from a 200 response — undetectable by
error-checking, which is why the classification lives here rather than in the UI.

## C-11 — Telemetry Collector

**Purpose**: read usage metrics from CloudWatch — both AWS-emitted and blueprint-emitted — and write
them as their own object.

**Responsibilities**
- Read the **fixed** AWS allowlist (Q2 = A): `AWS/Bedrock` (`Invocations`, `InputTokenCount`,
  `OutputTokenCount`, `InvocationClientErrors`, `InvocationLatency`) and `AWS/Bedrock-AgentCore`
  (`Sessions`, `ActiveSessionCount`, `Invocations`, `Errors`, `Throttles`, `Latency`)
- Read **only** the counters C-14's catalog declares, in `Cornell/Blueprints/*` (FR-9.5.2, NFR-T5)
- Discover **dimension values only** — which `ModelId`s exist — never which metrics to read
- Distinguish the three states of NFR-T7 per counter: *not instrumented* (not in the catalog),
  *no data yet* (declared, no datapoints in window), *cannot read* (the call failed)
- Write `telemetry/current.json` in one `PutObject`, complete-or-fail

**Explicitly not responsible for**
- Deriving rates. It collects numerator and denominator counters separately; C-13 derives
  (FR-9.6 — a pre-computed ratio cannot be re-aggregated across agents or windows)
- Pricing anything. That is C-12.

**Interfaces**
- *In*: EventBridge, **hourly** — same cadence as inventory, deliberately a separate writer so a
  CloudWatch failure cannot fail the inventory snapshot
- *Out*: one `PutObject` to `telemetry/current.json`; JSON logs; EMF metrics
- *Depends on*: CloudWatch (upstream), C-02, C-13, C-14

**Constraints carried**
- Same image as C-01, 4th target + `CMD`
- IAM: `cloudwatch:GetMetricData` and `cloudwatch:ListMetrics`, read-only, plus write to the one
  telemetry key
- `GetMetricData` is ~$0.01 per 1,000 metrics requested — negligible, unlike CE (A3.6). The metric
  count per run MUST still be bounded, because the allowlist × discovered models is a product

**Honest status on delivery** (A3.1): the AWS-emitted half returns real but tiny numbers — 2
invocations and 14 input tokens over 14 days, because the application's real traffic goes through the
LiteLLM gateway off-account. The `Cornell/Blueprints/*` half returns *not instrumented* for every
blueprint, because T6 instrumented none. Both are correct behaviour, and both must be visibly
distinguishable from zero.

## C-12 — Cost Model + Estimator (pure)

**Purpose**: the cost record types, and the token × rate arithmetic. No AWS, no clock, no env.

**Responsibilities**
- The cost record and rate-table types, and parsing a rate table from JSON
- `estimate_model_cost(tokens, rates)` — the FR-10.6 estimate
- Deriving cost-per-completed-task (FR-10.7), including the no-tasks case
- Classifying a tag group as attributed or unattributed (the FR-10.3.6 predicate, so the rule is
  property-testable without AWS)

**Money is `Decimal`, never `float`.** Cost Explorer returns strings (`"9.0231738003"`); parsing
those to `float` introduces binary rounding into figures a human will act on. `decimal` is stdlib, so
this stays inside U-01's dependency-free boundary. Recorded here because it is the kind of decision
that is invisible until a total fails to reconcile.

**Why it is a component, and in U-01**: it is the one piece of new logic where a silent error produces
a *wrong number a person spends money on*. Being pure makes it property-testable without mocks —
Q4 = A exists for this. Candidate properties: estimate is monotonic in tokens; zero tokens ⇒ zero
cost; summing per-model estimates equals the estimate over summed tokens; a missing rate is surfaced,
never treated as zero (FR-10.6.6).

**Interfaces**: called by C-10 (types, tag classification) and C-03 (estimate at read time). Depends
on nothing in this blueprint. Must satisfy `tools/check`'s core boundary grep.

## C-13 — Telemetry Model (pure)

**Purpose**: the counter record types and every derivation over them. Clock injected, never read.

**Responsibilities**
- Counter and counter-series types, keyed by `deployment_id` / `agent_id` / `model` (FR-9.3)
- **`agent_id` defaults to `deployment_id`** (T8) — implemented here so every reader inherits it
- Rate derivation from numerator + denominator counters, re-aggregatable across agents and windows
- The three-state classification of NFR-T7 as a closed enum, not free text

**Interfaces**: called by C-11 and C-03. Depends on nothing. Boundary-grep clean.

## C-14 — Declared-Counter Catalog

**Purpose**: carry each blueprint's `telemetry:` declaration to a Lambda that cannot read git.

**Design** (Q2 = A): a pipeline build step walks `blueprints/*/blueprint.yaml`, extracts each
`telemetry:` block, and writes one catalog JSON baked into the container image. A pure parser in U-01
reads it.

**Why this component exists at all**: FR-9.4 requires the declaration to live in `blueprint.yaml` and
FR-9.5.2 requires the reader to honour it as a closed allowlist — but **`blueprint.yaml` is in git and
the reader is in Lambda**, and this repo has no runtime config distribution. A2 specified both ends
and no middle. C-14 is the middle.

**Responsibilities**
- Build step: collect declarations; treat a missing `telemetry:` block as `emits: false`
  (FR-9.4.2); fail the build on a malformed one
- Parser: expose the catalog as declared counters with units and descriptions, so the UI renders
  **generically** and a new emitting blueprint needs no dashboard code change (FR-9.4.3)

**The tradeoff, stated**: a blueprint that starts emitting is invisible until the dashboard is next
deployed. Acceptable because a merge to `main` redeploys everything, so the lag is one pipeline run —
and the alternative (SSM at deploy time) requires editing every other blueprint's template, which is
the cross-track work T6 declined.

## Extensions to existing components

### C-02 Snapshot Store → three keys, three writers, no RMW (Q1 = A)

The store becomes **three objects, one per section**, each with a single owner:

| Key | Writer | Cadence |
|---|---|---|
| `inventory/current.json` | C-01 | hourly |
| `telemetry/current.json` | C-11 | hourly |
| `cost/current.json` | C-10 | daily |

**This supersedes FR-9.5.3's "additive sibling section" wording** and the "room for a sibling
top-level key" note in C-02 above. The reason is concrete: with two cadences, one object forces a
**read-modify-write**, which C-01's design forbids in terms (*"single `put_object`, complete-or-fail,
CR-05, no read-modify-write"*) and which loses updates when writers overlap. Per-key ownership keeps
every write complete-or-fail and means no writer ever reads another's data.

**Consequence the UI must carry**: `collected_at` is now **per section**. There is no single "snapshot
age". This is more honest than the alternative — cost is genuinely ~24–48h stale while inventory is an
hour stale, and one timestamp over all three would have misrepresented two of them.

### C-03 Read API → new routes, composition, read-time estimation
- New routes (plan Q6): `/api/cost/summary`, `/api/cost/breakdown`, `/api/usage/models`,
  `/api/usage/quality`
- Reads 1–3 objects and composes; a missing or unreadable section degrades **that section only**,
  never the whole response
- Applies C-12's estimate at read time, consistent with Q2 = A of the v1 design (derive on read)
- Every section carries its own `collected_at` and its own NFR-T7 state
- IAM widens from one key to the three keys — still key-scoped, not bucket-wide

### C-06 Web UI → two new tabs
- **Financial** (US-16…US-19) and **Adoption** (US-20…US-23), alongside the existing four views
- Reuses `StateBoundary` unchanged — NFR-T7's three states map onto the component already tested for
  six, so the honest-empty-state behaviour is inherited rather than reimplemented
- Estimated figures visually distinct from billed ones (NFR-T1); unattributed spend never rendered as
  a named group (FR-10.3.6)
- Shows the dashboard's **own** cost line (plan Q8), because A3.6 makes it material

### C-09 Observability Set → the new collectors
- Alarms for C-10 and C-11 failure and staleness, mirroring C-01's
- **Two new log groups**, and CloudWatch is already ~18% of this account's spend (A3.6) — so
  retention on the new groups is a cost decision, not a default. Short retention, set explicitly.
- A metric for **CE calls per run** (C-10), so the dashboard's own cost is measurable rather than
  assumed (NFR-T8)
