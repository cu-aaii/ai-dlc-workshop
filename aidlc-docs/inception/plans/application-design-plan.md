# Application Design Plan — `dashboard` Blueprint (Cost & Usage Dashboard)

**Stage**: INCEPTION → Application Design (EXECUTE per `inception/plans/execution-plan.md`)
**Date**: 2026-08-03
**Inputs**: `inception/requirements/requirements.md` (approved), `inception/user-stories/stories.md`
and `personas.md` (approved), `inception/plans/execution-plan.md` (approved)

---

## How to use this document

**Part A** holds **8 questions** about design decisions the requirements deliberately left open.
Fill in each `[Answer]:` tag directly in this file. Every question must be answered before
generation starts. If none of the options fit, choose **X) Other** and describe what you want.

Where I have a view, the recommended option is listed **first and marked**. The recommendation is
not the default — nothing is chosen for you.

**Part B** is the execution checklist that runs once you approve the plan.

### What is deliberately not asked here
- **Detailed business rules.** The stage rules put those in Functional Design (CONSTRUCTION,
  per-unit). So the exact tag-gap classification edge cases (US-04's empty/whitespace values,
  whether a per-tag or combined "missing" group is shown in US-03), the precise staleness
  threshold, and the exact shape of each aggregation are named as inputs to Functional Design
  rather than settled now.
- **RESILIENCY-04 (rollback mechanism, deployment style), RESILIENCY-14 (resiliency testing),
  RESILIENCY-15 (incident response).** These are user decisions already recorded as deferred to
  NFR Design in `aidlc-state.md` and the execution plan. Asking them here would move a gate that
  was already placed.
- **Anything already settled by the requirements.** The collector and API are two separate
  components because SECURITY-12 requires separating write from read — that is not reopened below.

---

## Part A — Questions

### Question 1 — What stores the snapshot?

FR-2 requires a snapshot in durable storage; FR-2.4 requires it to be extensible so a cost dataset
can later sit alongside inventory joined on `cornell:deployment-id`. The requirements deliberately
do not name the technology. RESILIENCY-12 mentions "S3 versioning where a bucket holds the
snapshot", which anticipates but does not decide this.

A) **A single JSON object in S3** *(recommended)* — the collector writes one object per run,
   the API reads the current one. Versioning gives you snapshot history for free, encryption and
   Block Public Access are already required for the site bucket, and a later cost dataset is just
   another key or another top-level field. Round-trip and idempotence properties (PBT) are
   straightforward against a byte-for-byte object. *Cost*: no query capability — the API reads the
   whole snapshot every time. At tens-to-hundreds of resources that is a non-issue; at ten
   thousand it would be.

B) **A DynamoDB table** — one item per resource, plus aggregate items. Queryable, so the API can
   fetch one deployment's resources without reading everything. *Cost*: materially more design
   (partition/sort key choice, aggregate maintenance, and the write path becomes a batch of writes
   that can partially fail — which collides with US-02's "an incomplete inventory is never
   presented as complete"). Buys scale the requirements explicitly say not to build for (§4.4).

C) **An SSM Parameter** — cheapest possible, no bucket needed. *Cost*: a hard 4KB (standard) /
   8KB (advanced) limit, which a few dozen resources with ARNs and tag maps would exceed. Also the
   `Tags`-as-a-map gotcha. Recorded here mainly to rule it out explicitly rather than leave you
   wondering why it wasn't considered.

D) **S3 object for inventory now, with the option of DynamoDB later if cost data needs querying** —
   defer the harder decision to when cost data actually arrives. *Cost*: two storage models
   eventually, or a migration.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 2 — Is aggregation computed when the snapshot is written, or when it is read?

US-03 needs grouping by `cornell:deployment-id`, `cornell:owner`, and `cornell:blueprint`; US-04
needs the tag-gap list. Something has to compute those. This is the most consequential question
here, because it decides where the logic PBT tests lives and how much the API does.

A) **At read time — the API computes groupings from the stored inventory** *(recommended)* — the
   snapshot holds raw inventory only. Groupings become a pure function of it, which is exactly what
   §4.5 asks for ("pure and unit-testable independently of AWS calls") and what the PBT properties
   in §4.2 are written against. Adding a grouping later needs no re-collection, and US-03's
   "totals across groups equal the ungrouped total" is trivially true because both come from one
   list. *Cost*: recomputed per request. At this data volume that is microseconds.

B) **At write time — the collector precomputes and stores the groupings** — the API becomes a
   near-passthrough. Fastest reads. *Cost*: the snapshot now contains derived data that can
   disagree with its own raw inventory, which is a new failure mode US-03's count-consistency
   criterion exists to catch; and adding a grouping later requires re-collection or a migration.

C) **Both — store precomputed groupings and let the API recompute on demand** — *Cost*: two code
   paths that can disagree, and no rule for which wins. Listed for completeness; I would not
   recommend it.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 3 — What fronts the read API?

FR-3 needs an HTTP API. FR-3.5 and SECURITY-12 require **rate limiting**, which is the deciding
constraint rather than a detail.

A) **API Gateway HTTP API** *(recommended)* — built-in throttling satisfies the rate-limiting
   requirement directly, has native CloudFront integration as an origin, and supports stage-level
   and per-route limits. *Cost*: one more resource type in the template.

B) **Lambda Function URL** — simplest possible; no API Gateway at all. *Cost*: **no request
   throttling**. Function URLs have no usage plans, so the only lever is reserved concurrency,
   which caps concurrent executions rather than request rate. That is a weaker instrument than
   FR-3.5 asks for, and it would need recording as another accepted exception. It also puts the
   burden of rate limiting on WAF rate-based rules.

C) **API Gateway REST API** — more features (request validators, usage plans with API keys).
   *Cost*: more expensive and more configuration than this needs; API keys imply an identity model
   v1 deliberately does not have.

D) **Lambda Function URL plus a WAF rate-based rule** — keeps the simplicity of B and gets rate
   limiting from the WAF you are already deploying for FR-5. *Cost*: WAF rate-based rules count
   per source IP over a fixed window, which is coarser than API-level throttling and behaves oddly
   when many viewers share a campus NAT egress IP — plausible here, and it would throttle a
   building rather than a caller.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 4 — Does the API sit behind the same CloudFront distribution as the UI?

FR-5.2 requires the network allowlist to cover the API path, not just the static site, and FR-5.1
attaches the WAF web ACL to CloudFront. SECURITY-08 forbids a CORS wildcard.

A) **Yes — one distribution, two origins: S3 for the site, the API for `/api/*`** *(recommended)* —
   one WAF web ACL then covers both, satisfying FR-5.2 with no second control to keep in sync. The
   browser calls a same-origin path, so **CORS does not arise at all** rather than being restricted
   correctly, which is the stronger way to satisfy SECURITY-08. *Cost*: cache-behaviour
   configuration has to be right — the API path must not be cached, or viewers get stale JSON
   under a fresh timestamp, which is precisely the failure US-05 exists to prevent.

B) **No — separate endpoints; the UI calls the API's own domain** — simpler cache configuration.
   *Cost*: the API needs its own protection to satisfy FR-5.2 (a regional web ACL on API Gateway,
   separate from the CloudFront one), so there are two allowlists that must agree; and CORS becomes
   real and must be restricted to the distribution origin. Two ways to be wrong that option A does
   not have.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 5 — What is the API's surface shape?

FR-3.2 requires the full inventory plus aggregation by three tags. RESILIENCY-06 requires a health
endpoint with a deep check that the snapshot store is readable.

A) **Distinct paths** *(recommended)* — e.g. `/api/inventory`, `/api/groups/deployment-id`,
   `/api/groups/owner`, `/api/groups/blueprint`, `/api/tag-gaps`, `/api/health`. Each path has a
   fixed, enumerable contract, which makes SECURITY-05's allowlist validation nearly structural —
   an unknown path is a 404 rather than a parameter to validate. *Cost*: more routes.

B) **One path with a query parameter** — `/api/inventory?groupBy=deployment-id`. Fewer routes.
   *Cost*: `groupBy` becomes a value to allowlist-validate, which is exactly the class of thing
   SECURITY-05 exists for — workable, but it converts a structural guarantee into a code path that
   can be got wrong.

C) **One path returning everything** — inventory, all three groupings, and tag gaps in a single
   response. Simplest possible API; the UI filters client-side. *Cost*: the response carries data
   most requests don't need, and it forecloses server-side paging if the account ever grows.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 6 — Where does the health endpoint live?

A) **Same Lambda and same API as the read endpoints** *(recommended)* — a health check that shares
   the read path's code and IAM role actually tests what viewers depend on. *Cost*: it is behind the
   WAF allowlist like everything else, so it cannot be polled from outside — already recorded in
   RESILIENCY-06 as why synthetic canary monitoring is N/A.

B) **A separate Lambda** — isolated, so a failure in the read path doesn't affect it. *Cost*: it
   then tests a different code path and role from the one users hit, so it can report healthy while
   the API is broken. That is the failure mode US-06 is about.

X) Other (describe after [Answer]: tag below)

[Answer]:A

### Question 7 — How is the UI built?

FR-4.1 requires a static site. SECURITY-14 requires Subresource Integrity on any third-party
script, and says "preferably: load none".

A) **Hand-written HTML, CSS and vanilla JS, no build step, no third-party scripts** *(recommended)*
   — satisfies SECURITY-14 by having nothing to add SRI to, and keeps the CSP in US-01 tight
   because there is no framework needing `unsafe-inline` or `unsafe-eval`. No build tooling to add
   to a repo whose only build prerequisite today is `uv`. *Cost*: grouping tables and state
   handling written by hand. At this UI's size that is a modest amount of code.

B) **A framework with a build step** (React/Vue/Svelte + bundler) — more idiomatic for larger UIs.
   *Cost*: introduces Node/npm into a repo that has none, adds a build stage to a pipeline that
   currently builds nothing, and expands the supply-chain surface SECURITY-10 makes blocking —
   for a UI with roughly four views.

C) **Vanilla JS plus one CDN-hosted library** for table rendering — less hand-written code.
   *Cost*: a third-party script, so SRI becomes mandatory and the CSP must permit the CDN origin.
   Trades the strongest reading of SECURITY-14 for convenience.

X) Other (describe after [Answer]: tag below)

[Answer]:B

### Question 8 — How does the API signal the degraded states in US-06?

US-06 needs four distinguishable states: no snapshot yet, snapshot unreadable, stale-but-present,
and normal. SECURITY-15 requires failing closed with no fabricated or partial-looking-complete
data, and FR-3.4 requires generic errors that leak nothing.

A) **HTTP status codes plus a status field in the body** *(recommended)* — normal and
   stale-but-present return 200 with an explicit `stale` flag and the true collection timestamp;
   no-snapshot-yet and unreadable return distinct error statuses with a generic message. Standard
   HTTP semantics, and monitoring can alarm on status codes without parsing bodies. *Cost*: the UI
   handles both a status code and a body field.

B) **Always 200, with the state in the body** — one response shape; the UI reads `state`. *Cost*:
   an error is invisible to anything that watches status codes, including CloudFront metrics and
   the alarms in US-13, so a failure looks like success to exactly the layer meant to catch it.

C) **HTTP status codes only** — no status field; staleness is inferred by the UI from the
   timestamp. *Cost*: "stale" becomes a client-side judgement, so two clients with different
   thresholds disagree about the same snapshot — which breaks US-05's requirement that two views on
   one snapshot agree.

X) Other (describe after [Answer]: tag below)

[Answer]:A

---

## Part A2 — Resolved decisions (Q1–Q8)

Step 8 analysis found Q1–Q6 and Q8 clean: single selections, no vagueness, no contradiction, no
option-merging, mutually consistent. **Q7 = B is a clean selection but incomplete**, so three
follow-ups were raised in `application-design-plan-clarification.md` (Step 9). Generation does not
begin until those are answered.

| # | Decision | Answer | Consequence for the design |
|---|---|---|---|
| Q1 | Snapshot store | **A** | One JSON object in S3, versioned and encrypted. A later cost dataset is another key or top-level field (FR-2.4). No query layer; the API reads the whole snapshot. |
| Q2 | Aggregation timing | **A** | Computed at **read time**. The snapshot holds raw inventory only, so grouping is a pure function of it — satisfying §4.5 and giving the PBT properties in §4.2 a clean target. No derived data can disagree with its own source. |
| Q3 | API front door | **A** | API Gateway HTTP API. Built-in throttling satisfies FR-3.5 / SECURITY-12 directly — **no rate-limiting exception is needed**. |
| Q4 | Distribution topology | **A** | One CloudFront distribution, two origins: S3 for the site, API Gateway for `/api/*`. One web ACL covers both (FR-5.2), and the browser call is same-origin so **CORS does not arise** (SECURITY-08 satisfied structurally). Requires a no-cache behaviour on `/api/*`. |
| Q5 | API surface | **A** | Distinct paths: `/api/inventory`, `/api/groups/{tag}`, `/api/tag-gaps`, `/api/health`. Makes SECURITY-05 validation largely structural — an unknown path is a 404, not a value to validate. |
| Q6 | Health endpoint | **A** | Same Lambda and same API as the read endpoints, so the check exercises the code path and IAM role viewers actually depend on (RESILIENCY-06 deep check). |
| Q7 | UI build | **B** — pending Q9–Q11 | A framework with a build step. Diverges from the recommendation; consequences recorded in the clarification file. Framework/bundler, the S3 deployment mechanism, and SECURITY-10's scope over npm all need settling. |
| Q8 | Degraded-state signalling | **A** | HTTP status codes **plus** a body status field. Normal and stale-but-present are 200 with an explicit stale flag and true timestamp; no-snapshot and unreadable are distinct error statuses with generic messages — so US-13's alarms can watch status codes, and "stale" stays a server judgement (US-05 consistency). |

### Interactions worth recording
- **Q1 = A + Q2 = A compose cleanly.** A whole-object read plus read-time aggregation means the API
  has exactly one dependency on storage — read the current object — and everything else is pure. That
  is the simplest arrangement that satisfies §4.5's testability requirement, and it makes the
  round-trip and idempotence properties in §4.2 assertions about bytes rather than about a schema.
- **Q3 = A removes a threatened exception.** Had Q3 = B been chosen, FR-3.5's rate limiting would have
  had no direct mechanism and would have needed recording as a fifth accepted exception in §4.6. It
  does not; §4.6 stays at four.
- **Q4 = A + Q5 = A interact with the cache.** Distinct paths under one distribution means the
  `/api/*` behaviour must be no-cache while the site behaviour is cached. Getting that backwards
  serves stale JSON under a fresh-looking timestamp — the exact failure US-05 exists to prevent — so
  it is called out in `component-dependency.md` rather than left to Infrastructure Design to notice.
- **Q7 = B is the only answer that adds scope.** Every other answer either matches the requirements'
  expectations or reduces work. Q7 = B introduces a second dependency ecosystem, a build step, and a
  second thing that must reach S3 — which is what Q9–Q11 exist to pin down.

---

## Part B — Execution checklist (runs after you approve)

### B1. Preparation
- [x] Re-read `requirements.md` §3–§5 and `stories.md` to extract every component-level obligation
- [x] Run the mandatory Step 8 answer analysis: check every answer for vagueness, undefined terms,
      contradictions, missing detail, and option-merging; raise a follow-up question file if any
      is found, and do not proceed to approval until resolved (Step 9)
- [x] Consolidate the resolved answers into a decision table in this document, as was done for the
      story plan's Part A2

### B2. `components.md` (mandatory artifact)
- [x] Component name, purpose, and responsibilities for each: collector, snapshot store, read API,
      static UI, edge (CloudFront + WAF), and the deployment marker from FR-6
- [x] Component interfaces — what each exposes and what it consumes
- [x] Name the pure, AWS-free aggregation component explicitly, since §4.5 and PBT both depend on
      its existence as a separable unit
- [x] Record which components are new vs. which are existing shared files being edited
      (`pipeline/stacks.yml`, `pipeline/pipeline.yml`)

### B3. `component-methods.md` (mandatory artifact)
- [x] Method signatures with input/output types for each component
- [x] High-level purpose per method; **no** detailed business rules — those are Functional Design's
      output, and the boundary is stated in the document
- [x] Name the methods the PBT properties in `requirements.md` §4.2 attach to, so Functional Design
      inherits a concrete target rather than a category
- [x] Include pagination handling as an explicit method concern, since silent truncation is the
      failure US-02 guards against

### B4. `services.md` (mandatory artifact)
- [x] Service definitions and responsibilities
- [x] Orchestration: the scheduled collection flow, and the request-serving flow
- [x] State the invariant that read requests never trigger collection (FR-2.1, US-07)
- [x] Record where the degradation ladder from US-06 is decided and where it is rendered

### B5. `component-dependency.md` (mandatory artifact)
- [x] Dependency matrix
- [x] Communication patterns, including the resolved answer to Question 4 (one distribution or two
      endpoints) and its consequence for CORS and for the number of allowlists
- [x] Data flow diagram: schedule → collector → Tagging API → snapshot store → API → UI, and the
      edge controls each hop sits behind
- [x] Mark the upstream dependency (Resource Groups Tagging API) and the RESILIENCY-10 obligations
      on it — explicit timeouts, bounded retries with backoff, graceful degradation
- [x] Record that nothing depends on this blueprint (RESILIENCY-01), so its blast radius is inward

### B6. `application-design.md` (mandatory artifact)
- [x] Consolidate B2–B5 into a single document, per the stage's Step 10
- [x] Include the resolved decision table and the reasoning for each choice
- [x] Carry forward the four accepted exceptions from `requirements.md` §4.6 so the design does not
      read as though they were forgotten

### B7. Validation and honest reporting
- [x] Validate design completeness against FR-1..FR-7 and against US-01..US-15
- [x] Validate internal consistency — no component with an unowned responsibility, no method
      without a caller, no dependency without a communication pattern
- [x] Confirm the design creates **no** VPC, subnet, VPN, Direct Connect, or Transit Gateway
      resource (FR-5.4)
- [x] Confirm the design implies **no** login, user pool, identity pool, or browser-side SigV4
      (FR-4.5, SECURITY-13 exception)
- [x] Carry the container-build finding from the execution plan forward as an input to
      Infrastructure Design rather than letting it lapse
- [x] Report anything that cannot be settled at this stage, naming the later stage that carries it,
      instead of inventing a decision to look complete

### B8. Completion
- [x] Mark every step above `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Log the approval prompt in `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present the `# 🏗️ Application Design Complete` message and wait for explicit approval

---

## Part A3 — Resolved decisions (Q9–Q11)

Step 8 analysis of `application-design-plan-clarification.md`. All three are clean single selections
with no vagueness, undefined terms, contradiction, missing detail, or option-merging. No third round
of blocking follow-ups was needed.

| # | Question | Answer | Effect on the design |
|---|---|---|---|
| Q9 | Framework and bundler | **B — React + Vite** | Diverges from my recommendation (A, Svelte + Vite). Fine: legibility to whoever picks this up after the workshop is a real criterion, and it was the stated reason option B existed. Cost is a larger dependency tree and a runtime shipped to the browser. |
| Q10 | How built files reach S3 | **A — new Build stage action in the pipeline** | Confirms the coordination point: one `pipeline.yml` edit covering the container images *and* the Vite build + `s3 sync`, not two. Consistent with "everything deploys through the pipeline". |
| Q11 | SECURITY-10 over npm | **B — pinning yes, scanning and SBOM no** | Lockfile committed with integrity hashes; no npm vulnerability scan, no npm SBOM. |

### Recorded interactions

1. **Q9 = B and Q11 = B compound.** React + Vite is, by the description in Q9 itself, the largest
   dependency tree of the three options. Q11 = B is the answer that declines scanning and SBOM
   coverage *of that tree*. So the blueprint's largest dependency surface gets its least scrutiny.
   The posture is defensible — npm here is build-time only and invisible to a runtime image scan, and
   exact pinning is the mitigation that matters most against a *changed* dependency — but the residual
   risk is real: a build-time dependency compromised at a pinned version can inject arbitrary code
   into the delivered bundle. Recorded in `application-design/application-design.md` §6.2 as a
   decision on the record rather than an emergent property of two answers given in different rounds.
   **No change requested.**

2. **Q11 = B narrows two approved artifacts.** Q11's own text said option C would need recording in
   `requirements.md` §4.6; option B declines two of SECURITY-10's four provisions for one ecosystem,
   so the same logic partly applies. And **US-09's fourth acceptance criterion** is written
   unqualified — under Q11 = B it is true of Python and container images and false of npm, so an
   implementer reading only the story would build npm scanning the answer says not to build. Both are
   approved artifacts, so amending either is the user's call. Raised as Q12/Q13 in
   `application-design-plan-clarification-2.md`, explicitly **non-blocking** — the design is complete
   and consistent under Q11 = B either way.

3. **Q10 = A surfaces a real ordering problem, deferred not guessed.** The Build stage must precede
   BlueprintDeploy so the images exist, but the site bucket is created *by* the stack BlueprintDeploy
   deploys — so `aws s3 sync` targets a bucket that does not yet exist on a first deployment. Three
   resolutions exist and choosing is an infrastructure-topology decision. Recorded in
   `services.md` and `application-design.md` §6.4 as deferred to Infrastructure Design.

4. **Q9 = B makes US-01's CSP obligation concrete.** Vite's modulepreload polyfill emits an inline
   script by default, so it must be disabled or hash-allowlisted. Written into `components.md` in
   those terms because "keep the CSP strict" is not actionable and "disable the polyfill" is. The CSP
   is not being loosened to match the tooling.

5. **The container-build finding is corroborated by `CLAUDE.md`, not only by my reading of the
   template.** It states outright that `ContainerBuildProject`, `ContainerRepository` and
   `pipeline/codebuild.yml` are defined and known-good but that no stage invokes them, and that wiring
   one is a Build stage action plus a Dockerfile. Recorded so the execution plan's Medium risk rating
   rests on documented fact.
