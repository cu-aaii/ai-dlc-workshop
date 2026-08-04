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
