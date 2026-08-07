# Application Design — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 5 of 5 — consolidating)
**Date**: 2026-08-03
**Status**: Awaiting user approval

**Companion artifacts**: `components.md` · `component-methods.md` · `services.md` ·
`component-dependency.md`
**Inputs**: `inception/requirements/requirements.md` (approved) ·
`inception/user-stories/stories.md` (approved) · `inception/plans/execution-plan.md` (approved) ·
`inception/plans/application-design-plan.md` Part A2 (Q1–Q8) ·
`inception/plans/application-design-plan-clarification.md` (Q9–Q11)

---

## 1. The design in one paragraph

A scheduled Lambda paginates the Resource Groups Tagging API to exhaustion and writes **one**
versioned, encrypted JSON snapshot to S3 — complete or not at all. A second Lambda behind a throttled
API Gateway HTTP API reads that object and derives every view at read time. Two AWS-free pure Python
modules do all the actual logic: one owns the record and snapshot types plus serialization, the other
owns grouping, tag-gap classification, and the staleness judgement. A React + Vite static bundle in S3
renders it. **One** CloudFront distribution fronts everything — S3 for the site, API Gateway for
`/api/*` — with a deny-by-default WAF IP allowlist of Cornell ranges as the only access control. No
identity, no login, no VPC.

---

## 2. Decisions and where they came from

| # | Decision | Answer | Consequence in this design |
|---|---|---|---|
| Q1 | Snapshot = one S3 object | A | C-02 is passive storage; C-04's round-trip property is about **bytes**, the simplest form it can take |
| Q2 | Aggregation at read time | A | C-05 is pure and read-only; C-01 never derives anything |
| Q3 | API Gateway HTTP API, not a Function URL | A | FR-3.5 rate limiting has a direct mechanism, so **§4.6 stays at four exceptions** |
| Q4 | One CloudFront distribution, two origins | A | Same-origin `/api/*`, no CORS — **at the cost of a cache-policy obligation** |
| Q5 | Distinct path per view | A | Input surface reduces to one allowlisted `{tag_key}`; SECURITY-05 becomes near-structural |
| Q6 | `/api/health` in the same function | A | One image, one role; health reports liveness, not data quality |
| Q7 | A framework with a build step | B | Adds a Node toolchain and a pipeline Build stage — the only answer that adds scope |
| Q8 | Status code **and** body status field | A | Staleness is a server judgement; `LoadOutcome` is three-state, not boolean |
| Q9 | React + Vite | B | Largest dependency tree of the three options; a runtime ships to the browser |
| Q10 | New Build stage action in the pipeline | A | Same `pipeline.yml` edit as the container build — one change, not two |
| Q11 | npm pinned, not scanned | B | Lockfile with integrity hashes; **no npm vulnerability scan, no npm SBOM** |

---

## 3. Architecture

Diagrams, the dependency matrix, and the deployment-order constraints are in
`component-dependency.md`. The three structural claims worth restating here:

- **The pure core has no dependencies.** C-04 depends on nothing; C-05 depends only on C-04. Neither
  imports an AWS SDK, opens a socket, or reads a clock. `requirements.md` §4.5 asked for this and PBT
  §4.2 is unimplementable without it.
- **The two services touch at exactly one point.** C-01 writes an S3 key; C-03 reads it. They do not
  reference each other. A read therefore cannot cost Tagging API quota, and a collector failure
  degrades the dashboard to *labelled stale* rather than *broken*.
- **The graph is acyclic**, rooted at the edge and terminating in pure logic.

---

## 4. The five requirement-driven design choices

Each of these exists because a specific requirement would otherwise be satisfiable only by accident.

**Complete-or-fail collection** (FR-1.1, US-02). Pagination that stops early under-reports inventory
*while reporting success*. C-01 raises instead: no partial write, the previous snapshot survives, the
alarm fires, and the UI says "stale". Visible staleness beats invisible incompleteness — the central
resiliency choice here, and the concrete meaning of graceful degradation for this blueprint.

**Three-state snapshot loading** (US-06, FR-3.3). A bare `try/except` collapses "the collector has
never run" and "the object is corrupt" into one failure, and an empty resource list renders
identically to both. So `load_current_snapshot` returns `PRESENT` / `ABSENT` / `UNREADABLE`, and the
response table in `component-methods.md` gives five distinguishable outcomes — including "no data
collected yet" ≠ "no tagged resources found".

**Injected clock** (US-05, Q8 = A). `evaluate_freshness(collected_at, now, stale_after)` reads no
clock and no config. The server decides staleness so two viewers agree, and the decision is testable
without waiting for time to pass.

**Closed-allowlist routing** (SECURITY-05, Q5 = A). The only user-supplied value the API accepts is
`{tag_key}`, validated against the four `cornell:*` tags. Unmatched paths 404 without touching S3.

**Deny-by-default at one control point** (FR-5.1, FR-5.2, SECURITY-07). One WAF web ACL on one
distribution covers both the site and the API. Two controls that must agree eventually disagree.

---

## 5. The obligations most likely to be lost

Recorded here because each is silent when wrong.

1. **`/api/*` must be no-cache while the site behaviour is cached.** Inverted, CloudFront serves a
   stale JSON body carrying a stale `collected_at` — the staleness notice stays truthful about the
   snapshot while lying about when the reader last looked, and two viewers disagree. This is the price
   of Q4 = A and the single most important line in this design.
2. **A `stacks.yml` entry without a matching `pipeline.yml` action deploys nothing and reports
   success.** `validate_stacks.py` now fails in both directions, so it is review-time rather than
   mysterious — but the mirroring is still manual.
3. **Build must precede BlueprintDeploy.** Backwards yields a CloudFormation error about a missing
   image tag, which reads as a template bug.
4. **Stack name must be `aidlc-<env>-dashboard`.** Outside the convention, `BuildPipelineRole` gives
   an opaque authorization failure, not a naming complaint.
5. **Vite's modulepreload polyfill emits an inline script by default** and must be disabled or
   hash-allowlisted. US-01's CSP is not being loosened to accommodate the bundler.

---

## 6. Findings

### 6.1 The container build has never run — corroborated, not just inferred

> **⚠️ SUPERSEDED 2026-08-03 — see `inception/amendments/repo-baseline-2026-08-03.md` §A1.2.**
> A branch rebase onto `main` brought in a `Build` stage that invokes `ArmContainerBuildProject`, and
> `builder-mcp` now proves build → digest → deploy-by-digest end to end. This finding no longer holds
> in general. It **does** still hold for the x86 `ContainerBuildProject`, which remains uninvoked —
> which is why Lambda architecture (arm64 vs x86) became a new open question, asked as Q8 in
> `unit-of-work-plan.md`. The original text is preserved below as approved.

`pipeline/pipeline.yml` defines `ContainerRepository` (line 103) and `ContainerBuildProject`
(line 191), and has three stages — `Source`, `PipelineDeploy`, `BlueprintDeploy` — none of which
invokes the build. `CLAUDE.md` states the same thing directly: *"`ContainerBuildProject`,
`ContainerRepository` and `pipeline/codebuild.yml` **are** defined and known-good, but no stage
invokes them yet because nothing needs an image."* This blueprint is the first to need one, and it
needs two. Never-executed pipeline machinery is the largest single unknown in the execution plan's
Medium risk rating.

### 6.2 Q9 = B and Q11 = B compound

These two answers were given independently and interact. React + Vite is, by the description in the
question itself, the **largest dependency tree** of the three options offered. Q11 = B is the answer
that declines vulnerability scanning and SBOM coverage **of that tree**. So the largest dependency
surface in the blueprint receives the least scrutiny of any dependency surface in it — the Python
dependencies and the container base images get pinning *and* scanning *and* an SBOM under US-09; npm
gets pinning alone.

This is a defensible posture and it is not being second-guessed here. Two things make it defensible:
npm packages are build-time only, so a scan of the produced runtime images would not see them
regardless; and exact pinning with integrity hashes gives reproducibility, which is the mitigation
that matters most against a *changed* dependency. The residual risk it does not cover is a build-time
dependency that is compromised at a pinned version — which can inject arbitrary code into the
delivered bundle, and which pinning detects only if someone is comparing against a known-good hash
they have independently verified.

Recorded so the exposure is a decision on the record rather than an emergent property of two answers
given in different rounds. **No change requested.**

### 6.3 Q11 = B narrows SECURITY-10 and US-09 — needs the user's call, non-blocking

Q11's own text said that option **C** "would be a new accepted exception to SECURITY-10 and would need
recording in `requirements.md` §4.6." Option B declines two of SECURITY-10's four provisions
(scanning, SBOM) for one of two ecosystems, so the same logic partly applies. Two approved artifacts
are affected:

- **`requirements.md` §4.6** currently documents **four** accepted exceptions. Part A2 already records
  that Q3 = A *kept* it at four. Q11 = B is either a fifth (partial) exception or a scope clarification
  of SECURITY-10 — arguably the latter, since SECURITY-10's scan target is the produced artifact and
  npm packages are not in it.
- **US-09's fourth acceptance criterion** — *"**Given** a dependency with a known vulnerability above
  the agreed threshold, **when** the build runs, **then** the failure is surfaced rather than passing
  silently"* — now reads as Python-and-container-only. As written it is unqualified, so an implementer
  reading only the story would build npm scanning that Q11 = B says not to build.

Both are approved artifacts, so amending either is the user's decision, not mine. Raised as a question
in `inception/plans/application-design-plan-clarification-2.md`. **It does not block this stage's
approval** — the design above is complete and consistent under Q11 = B either way; what is at stake is
whether the requirement and story texts say what the design does.

### 6.4 Unresolved: how `s3 sync` finds a bucket that does not exist yet

Under Q10 = A the Build stage precedes BlueprintDeploy, but the site bucket is created *by* the stack
BlueprintDeploy deploys. Three resolutions exist — split the bucket into a separately-deployed stack,
move the sync after BlueprintDeploy, or resolve the bucket name from the naming convention at sync
time — and choosing between them is an infrastructure-topology decision. **Deferred to Infrastructure
Design and recorded rather than guessed.**

### 6.5 Story coverage gap, carried forward unchanged

US-15 covers registry registration, the BlueprintDeploy action, stack naming, explicit parameters,
tags, and `tools/check` — but **not** the Build stage action or the Dockerfiles. Already recorded at
Workflow Planning; Q10 = A adds the site build to the same uncovered action. Carried by Infrastructure
Design and Code Generation. No story amendment proposed; the user may request one.

---

## 7. Requirement coverage

| Requirement | Component / service | Covered |
|---|---|---|
| FR-1.1 complete inventory | C-01 (`collect_all_resources`, complete-or-fail) | ✅ |
| FR-1.2 tag values captured | C-04 `ResourceRecord.tags` (all tags, not only `cornell:*`) | ✅ |
| FR-1.3 group by three tags | C-05 `group_by_tag` | ✅ |
| FR-1.4 tag-gap identification | C-05 `classify_tag_gaps` | ✅ |
| FR-2.1 read never triggers collection | S-02 has no write path | ✅ |
| FR-2.2 `collected_at` exposed | C-02 schema + C-03 responses + C-06 views | ✅ |
| FR-2.3 interval is a parameter | EventBridge schedule under C-01 | ✅ |
| FR-2.4 schema extensible | C-02 `schema_version` + sibling-key headroom | ✅ |
| FR-3.1–3.3 views and states | C-03 route table + C-06 | ✅ |
| FR-3.4 no internals in errors | C-03 `respond` | ✅ |
| FR-3.5 rate limiting | API Gateway throttling (enabled by Q3 = A) | ✅ |
| FR-4.1–4.2 private bucket, OAC | C-02, C-07 | ✅ |
| FR-4.5 read-only, no credentials | S-02 by construction | ✅ |
| FR-5.1–5.2 deny-by-default allowlist | C-07 (one ACL, both origins) | ✅ |
| FR-5.4 block is diagnosable | C-07 WAF logging + C-06 | ✅ |
| FR-5.5 no identity system | absent by design | ✅ |
| FR-6 repurpose `hello-world.yml` | C-08 | ✅ |
| FR-7.1–7.2 registry + action | `stacks.yml`, `pipeline.yml` | ✅ (design; implementation at Infra Design) |
| FR-8 cost figures | — | ⏸️ Deferred (US-D1, US-D2); data source undecided |
| §4.1 SECURITY-01..15 | see §5 obligation table in `component-dependency.md` | ✅ except SECURITY-10 npm scope (§6.3) and the four §4.6 exceptions |
| §4.2 PBT-01..10 | C-04 and C-05 own named properties | ✅ (identification completes at Functional Design per PBT-01) |
| §4.3 RESILIENCY-01..15 | C-01, C-03, C-09 | ✅ except -04, -14, -15 (deferred to NFR Design by the extension's own scoping) |
| §4.4 performance | C-01 page limit; C-02 volume note; C-03 single read | ✅ |
| §4.5 AWS-free logic | C-04, C-05 (empty dependency rows) | ✅ |

**No v1 functional requirement is unassigned.** FR-8 is deferred by prior decision, not by omission.

---

## 8. What is deliberately not in this design

- Cost figures and their data source (Cost Explorer vs. CUR) — FR-8, undecided on purpose
- Cognito, identity pools, SigV4 in the browser, any login
- VPC, subnets, VPN, Direct Connect, Transit Gateway
- Cross-account or cross-region collection
- A refresh button, or any on-demand collection trigger
- The platform-wide `observability/` component — stays unbuilt (`CLAUDE.md`)
- The telemetry amendment (queued to a second Requirements → Stories pass by Q3 = B of the telemetry
  questions; explicitly not blocking). Its shape — blueprints emit business metrics, the dashboard
  joins on `cornell:deployment-id` — is the reason C-02 has `schema_version` and sibling-key headroom
  now, so the amendment lands as an addition rather than a migration.

---

## 9. Approval

Approving this design accepts:

- The nine architectural answers in §2 as the basis for Units Generation and everything downstream
- The component set, method signatures, and dependency graph in the four companion artifacts
- The five silent-failure obligations in §5 as design requirements, not advice
- The findings in §6 as recorded — including §6.2's compounded dependency exposure, which needs **no
  action**, and §6.4's deferral to Infrastructure Design

It does **not** decide §6.3 (whether `requirements.md` §4.6 and US-09 are amended to match Q11 = B).
That is asked separately in `application-design-plan-clarification-2.md` and can be answered after
this gate.

---
---

# FR-9 / FR-10 extension — consolidated (2026-08-07)

**Second Application Design pass**, covering FR-9 (usage telemetry) and FR-10 (cost) only. The v1
design above is unchanged. Decisions: `plans/application-design-plan-fr9-fr10.md` Part A2.

## The four decisions, and what each one turned on

| # | Decision | Turned on |
|---|---|---|
| **Q1 = A** | **Three objects, one per section**, each with a single owner — not one object with sibling sections | A2's FR-9.5.3 could not be built as written. Cost is daily, inventory/telemetry hourly, so one object forces a **read-modify-write** — which C-01 forbids in terms (*"complete-or-fail, CR-05, no read-modify-write"*) and which loses updates when writers overlap. |
| **Q2 = A** | **Baked catalog + fixed AWS allowlist** | FR-9.4 puts declarations in `blueprint.yaml`; FR-9.5.2 makes them a closed allowlist. But `blueprint.yaml` is in **git** and the reader is in **Lambda**, and this repo has no runtime config distribution. A2 specified both ends and no middle; C-14 is the middle. |
| **Q3 = B** | **Reuse the collector image**, new target + handler, own role + schedule | Least-privilege stays tight (`ce:GetCostAndUsage` alone) and the failure domain stays independent, at the cost of a little template. Follows the existing `collector`/`api` two-target precedent. |
| **Q4 = A** | **Extend both units** on the existing purity line | Money arithmetic is the one new thing where a silent bug produces a wrong number someone spends against, so it must be pure and property-testable — which means U-01. |

## What is added

**Five new components**: C-10 Cost Collector (U-02), C-11 Telemetry Collector (U-02), C-12 Cost Model
+ Estimator (**U-01, pure**), C-13 Telemetry Model (**U-01, pure**), C-14 Declared-Counter Catalog
(pure parser + pipeline build step).

**Four extended**: C-02 (three keys, three owners), C-03 (four new routes, composition, read-time
estimation), C-06 (Financial + Adoption tabs), C-09 (alarms and log groups for two new collectors).

**Three new flows**: daily cost collection, hourly telemetry collection, read-time composition — see
`services.md`.

## Three design properties worth stating once, plainly

1. **`collected_at` is per-section; there is no single snapshot age.** A direct consequence of Q1 = A,
   and more honest than the alternative: cost is genuinely 24–48h stale while inventory is an hour
   stale, so one timestamp over all three would have misrepresented two of them.
2. **Money is `Decimal`, never `float`.** Cost Explorer returns decimal *strings*; parsing them to
   `float` puts binary rounding into figures a person acts on. `decimal` is stdlib, so this stays inside
   U-01's dependency-free boundary.
3. **Estimation happens at read time, not collection time.** Mirrors v1's Q2 = A. Storing an estimate
   would freeze it against the rate table in force when it was collected, so fixing a wrong rate would
   not fix history. Rates change; token counts do not.

## Two failure policies, deliberately different

Same-shaped components, opposite upstream economics:

- **Cost (Flow 4) fails whole.** Any CE call failing writes **nothing**; the previous cost object
  survives and tomorrow retries. A partially-populated cost object is worse than a stale one, because
  its missing groups read as *zero spend*.
- **Telemetry (Flow 5) degrades per counter.** The AWS half and the declared half are independent, and
  each counter carries its own state. Failing the run would erase real AWS data because an
  uninstrumented namespace returned nothing.

## Honest delivery status, carried forward from A3

- **Real data**: platform cost totals and by-service breakdown; per-model cost via `USAGE_TYPE`; AWS
  Bedrock/AgentCore request, token, error and session counts — *tiny* (2 invocations, 14 input tokens
  over 14 days), because real generation is off-account behind the LiteLLM gateway.
- **`unattributed`**: cost by blueprint/deployment, until the **Organization payer** activates
  `cornell:*` cost allocation tags. This account cannot, at any privilege level.
- **`not instrumented`**: human approval rate, prompt success rate, completed tasks, and therefore
  cost per completed task — T6 instrumented no blueprint.

All three are distinguishable states in the UI by requirement (NFR-T7), not incidental empty views.

## The namespace inconsistency FR-9.2.3 deferred here — decided

FR-9.2.3 flagged that U-02's own operational metrics use the CloudWatch namespace `Dashboard`, while
the contract requires `Cornell/Blueprints/<name>`, and left the resolution to this stage.

**Decision: keep both, unchanged, because they are not the same kind of metric.**

| Namespace | Carries | Required by |
|---|---|---|
| `Dashboard` | the dashboard's **operational** health — collector duration, outcomes, resources collected | US-14, RESILIENCY-05 |
| `Cornell/Blueprints/<name>` | a blueprint's **business usage** counters | FR-9.2.3 |

They answer different questions ("is the dashboard healthy" vs "how much is this application used"),
so one namespace holding both would conflate them. Renaming `Dashboard` was rejected on a concrete
ground: the shipped alarms name it literally, and `emf.py` records that it is *"kept short and fixed so
alarms name it literally"* — a rename is a breaking change to deployed alarms for a cosmetic gain.

**The rule this sets**: if the dashboard ever emits *usage* counters about itself — API hits, views
rendered — those go to `Cornell/Blueprints/dashboard` and are read by C-11 like any other blueprint's,
while `Dashboard` stays operational-only. The dashboard is then an emitter and a consumer at once,
which the contract already permits (`composable-dashboards.md` §3).

## Requirements amended by this stage

- **FR-9.5.3** — "additive sibling section" → three per-section objects. Recorded in
  `amendments/telemetry-a4-design-2026-08-07.md`.
- **FR-9.4 / FR-9.5.2** — gain the missing middle: the declaration reaches the reader via C-14's
  build-time catalog; the AWS-emitted half uses a fixed code-level allowlist. Same amendment.

## What this stage did NOT decide

Left to Functional Design / NFR Design / Infrastructure Design, deliberately:

- Exact CE query shapes, granularities, and the resulting call count per run (NFR-T8's budget)
- The metric window and period for `GetMetricData`, and how partial windows are presented
- Whether the two new schedules are one EventBridge rule with two targets or two rules
- Template layout: which stack the new Lambdas and schedules live in (`dashboard.yml` vs a new one)
- The per-model rate values themselves — still open per FR-10.8 item 3 (pricing-page data)

## Coverage validation (plan step B7)

Every FR-9/FR-10 clause and every US-16…US-25 story has a component home. Gaps are named, not implied.

| Requirement | Home |
|---|---|
| FR-9.1 contract + graceful non-participation | C-14 (declaration), C-11 (state), C-06 (render) |
| FR-9.2 EMF emission mechanism | **Not this blueprint's code** — the emitting side is each blueprint's. C-11 reads the result. Correct per T6. |
| FR-9.3 dimensions, `agent_id` defaults to `deployment_id` | C-13 `counter_key()` |
| FR-9.4 manifest declaration, `emits: false` first-class | C-14 (amended by A4.2) |
| FR-9.5 reader, closed allowlist, additive storage | C-11 + C-14; storage per A4.1 |
| FR-9.6 required counters, rates from two counters | C-11 (collect), C-13 (`derive_rate`) |
| FR-9.7 no emitter; three distinct states | C-13 `classify()`, C-03 `section_state()`, C-06 |
| FR-10.1 Cost Explorer | C-10 |
| FR-10.2 day / MTD / YTD, no budget | C-10 `fetch_windows()`, C-03 `cost_summary()` |
| FR-10.3 breakdown; asymmetric agent split | C-10 `fetch_groupings()`, C-03 `cost_breakdown()` |
| **FR-10.3.6 unattributed-group trap** | C-12 `is_unattributed()` / `split_attribution()` — pure, so property-testable |
| FR-10.4 separate daily schedule, bounded calls | C-10 + its EventBridge rule; call count emitted |
| FR-10.5 activation, non-retroactivity, lag, denial | C-10 classification + C-06 states |
| FR-10.6 estimate, labelled, configurable rates | C-12 `estimate_model_cost()`, rates from SSM, C-06 labelling |
| FR-10.7 cost per completed task | C-12 `cost_per_task()` |
| FR-10.8 verify-before-build | **Items 1–2 answered by A3.4.** Item 3 (per-model rates) is still open and is *data*, not design — NFR-T2's configurable table is the mitigation. |
| FR-10.9 no per-user attribution | **Prohibition** — verified by absence, as FR-5.4 is |
| NFR-T1 estimates distinguishable | C-06 |
| NFR-T2 rate table configurable | SSM + C-12 `parse_rate_table()` |
| NFR-T3 low-cardinality, no PII dimensions | C-13 key construction; no user dimension exists to leak |
| NFR-T4 / **NFR-T8** bounded own cost | C-10 call budget + `ce_calls` metric; C-09 short retention on new log groups |
| NFR-T5 closed allowlist | C-14 catalog (declared) + C-11 module constant (AWS) |
| NFR-T6 least-privilege IAM | Per-collector roles, each scoped to one CE/CW action set and one S3 key |
| NFR-T7 three states per panel | C-13 enum → C-03 → C-06 |

| Story | Home |
|---|---|
| US-16 cost totals, per-section age | C-10, C-03 `cost_summary()`, C-06 Financial |
| US-17 breakdown + **unattributed criteria** | C-10, C-12 `split_attribution()`, C-06 |
| US-18 estimated model cost, labelled | C-12, C-06 |
| US-19 cost per completed task | C-12 `cost_per_task()` |
| US-20 usage by model | C-11 (AWS half — real data), C-03 `usage_models()` |
| US-21 error / timeout rate | C-11 (`InvocationClientErrors` real; timeout push-only), C-13 `derive_rate()` |
| US-22 approval / success rate | C-14 + C-11 declared half — *not instrumented* on delivery, by design |
| US-23 per-agent attribution | C-13 `counter_key()` / `aggregate_by_agent()` |
| US-24 [Enabler] the contract | C-14, C-13, C-11's allowlist |
| US-25 [Enabler] cheap cost collection | C-10 budget + metric, C-09 retention, per-collector roles |

**Two coverage gaps, named rather than papered over:**
1. **FR-9.2's emission mechanism has no component here**, and should not — T6 put the emitting side in
   other blueprints. This blueprint specifies and reads it. A reviewer expecting an emitter should read
   FR-9.7.1.
2. **FR-10.8 item 3 (per-model rates) has no design answer** because it is pricing data, not a design
   question. NFR-T2 is the mitigation: the table is configuration, so a wrong rate is corrected without
   a deploy. Until it is populated, C-12 returns its missing-rate result and the UI shows *not
   instrumented* rather than a zero price.
