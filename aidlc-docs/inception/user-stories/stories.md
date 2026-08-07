# User Stories — `dashboard` Blueprint (Cost & Usage Dashboard)

**Stage**: INCEPTION → User Stories, Part 2 (Generation)
**Date**: 2026-08-03
**Persona**: `P-01` Dashboard viewer (see `personas.md`)
**Methodology**: per `aidlc-docs/inception/plans/story-generation-plan.md` Part A2 — classic
format, user-journey organization, thin vertical slices, Given/When/Then criteria, no priority or
dependency markers.

**Conventions**
- `US-nn` — a v1 story delivering user-visible capability
- `US-nn [Enabler]` — cross-cutting work with no user-visible slice (per plan Q9 = B)
- `US-Dn [Deferred]` — placeholder for the cost stretch goal, criteria intentionally TBD
- Requirement IDs are **not** cited in story text (plan Q3 = A); traceability is in §Coverage

---

# Journey 1 — Reaching the dashboard

## US-01 — Open the dashboard from a Cornell network connection

**As a** Dashboard viewer,
**I want** to open the dashboard in my browser from a Cornell network connection,
**so that** I can see platform inventory without needing an AWS account, credentials, or a login.

**Acceptance criteria**
- **Given** I am on an allowlisted Cornell network range, **when** I request the dashboard URL over
  HTTPS, **then** the dashboard page loads and no login or credential prompt appears at any point.
- **Given** I am on a network range that is not allowlisted, **when** I request the dashboard URL,
  **then** the request is blocked at the edge and I receive no dashboard content and no inventory
  data.
- **Given** I request the dashboard over plain HTTP, **when** the request reaches the edge, **then**
  I am redirected to HTTPS, and no dashboard content is ever served over an unencrypted connection.
- **Given** the dashboard page has loaded, **when** I inspect the response headers, **then**
  Content-Security-Policy, Strict-Transport-Security, X-Content-Type-Options, X-Frame-Options and
  Referrer-Policy are all present.
- **Given** I know or guess the storage location backing the site, **when** I request an object from
  it directly rather than through the dashboard's distribution, **then** the request is denied.
- **Given** the allowlisted ranges need to change, **when** a new set of ranges is supplied to the
  stack, **then** admission changes accordingly without editing the blueprint's template.

---

# Journey 2 — Seeing what has been deployed

## US-02 — See every tagged resource the platform has deployed

**As a** Dashboard viewer,
**I want** to see the complete list of AWS resources carrying `cornell:*` tags,
**so that** I know what actually exists in the shared account rather than what I assume exists.

**Acceptance criteria**
- **Given** the account contains resources tagged with any `cornell:*` tag, **when** I open the
  inventory view, **then** every such resource appears with its ARN, resource type, region, and the
  values of all four `cornell:` tags it carries.
- **Given** the account contains more tagged resources than a single upstream API response can
  return, **when** the inventory is collected, **then** the list is complete across all pages and no
  resource is silently omitted.
- **Given** collection of one page of results fails partway through, **when** the inventory is
  assembled, **then** an incomplete inventory is never presented as complete.
- **Given** a resource carries `cornell:*` tags, **when** I read its row, **then** the tag values
  shown are the values currently recorded in the snapshot, with no reformatting that changes their
  meaning.

## US-03 — Group inventory by deployment, owner, or blueprint

**As a** Dashboard viewer,
**I want** to group the inventory by `cornell:deployment-id`, `cornell:owner`, or
`cornell:blueprint`,
**so that** I can attribute a set of resources to one deployment, one person, or one blueprint.

**Acceptance criteria**
- **Given** the inventory contains resources spanning several deployment ids, **when** I group by
  `cornell:deployment-id`, **then** each distinct id appears once with its resources and a count.
- **Given** I have grouped the inventory by any of the three tags, **when** I total the counts
  across all groups, **then** the total equals the number of resources in the ungrouped inventory.
- **Given** a resource is present in the inventory, **when** I group by a tag it carries, **then**
  that resource appears in exactly one group and no group is empty.
- **Given** resources exist that lack the tag I am grouping by, **when** I group by that tag,
  **then** those resources are shown in an explicit "missing this tag" group rather than being
  dropped from the view.

## US-04 — Spot resources missing required tags

**As a** Dashboard viewer,
**I want** to see which resources are missing one or more of the four required `cornell:*` tags,
**so that** I can get them fixed before they become invisible to cost attribution.

**Acceptance criteria**
- **Given** a resource carries all four required tags, **when** I view the tag-gap list, **then**
  that resource does not appear in it.
- **Given** a resource is missing at least one of the four required tags, **when** I view the
  tag-gap list, **then** it appears, and the specific tags it is missing are named.
- **Given** a resource carries a required tag whose value is empty or whitespace only, **when** I
  view the tag-gap list, **then** it is treated as missing that tag rather than as compliant.
- **Given** no resources are missing tags, **when** I view the tag-gap list, **then** I see an
  explicit "no tag gaps found" state rather than an empty area I could mistake for a broken page.

---

# Journey 3 — Trusting what I am looking at

## US-05 — Know how fresh the data is

**As a** Dashboard viewer,
**I want** every view to tell me when its data was collected,
**so that** I never draw a conclusion from figures that are older than I assume.

**Acceptance criteria**
- **Given** a snapshot exists, **when** I open any view of the data, **then** the snapshot's
  collection timestamp is displayed without my having to look for it.
- **Given** I request the data as JSON rather than in the browser, **when** I read the response,
  **then** it carries the same collection timestamp as the browser view.
- **Given** the snapshot is older than the configured refresh interval by a clear margin, **when** I
  open the dashboard, **then** the data is visibly marked as stale in addition to showing its
  timestamp.
- **Given** two views are open on the same snapshot, **when** I compare their stated timestamps,
  **then** they agree.

## US-06 — Get an honest answer when the data is unavailable

**As a** Dashboard viewer,
**I want** the dashboard to tell me plainly when it cannot show me the data,
**so that** I never mistake a failure for an empty account.

**Acceptance criteria**
- **Given** no snapshot has been written yet, **when** I open the dashboard, **then** I see an
  explicit "no data collected yet" state, clearly distinguished from "no resources found".
- **Given** the snapshot cannot be read, **when** I open the dashboard, **then** I see an explicit
  error state and **no** partial or placeholder inventory that could be read as real data.
- **Given** a request fails for any reason, **when** I read the error shown to me, **then** it tells
  me what to do next without exposing internal identifiers, resource paths, account details, or
  diagnostic traces.
- **Given** the most recent collection attempt failed but an older snapshot exists, **when** I open
  the dashboard, **then** I am shown the older snapshot with its true timestamp and a clear
  indication that the latest refresh did not succeed.

## US-07 — Have the inventory refresh itself

**As a** Dashboard viewer,
**I want** the inventory to refresh on its own schedule,
**so that** I can just open the dashboard instead of asking someone to run a collection for me.

**Acceptance criteria**
- **Given** the blueprint is deployed, **when** the configured interval elapses, **then** a fresh
  collection runs and the snapshot's timestamp advances, without anyone triggering it.
- **Given** I open the dashboard, **when** the page loads, **then** it serves the stored snapshot
  and my visit does not itself trigger a collection.
- **Given** the refresh interval needs to change, **when** a new interval is supplied to the stack,
  **then** the schedule changes accordingly without editing the blueprint's template.
- **Given** the same tag data is collected twice in succession, **when** the second snapshot is
  written, **then** the data I see is unchanged.

---

# Journey 4 — Using the data outside the browser

## US-08 — Pull the inventory as JSON

**As a** Dashboard viewer,
**I want** to fetch the same inventory and groupings as JSON,
**so that** I can use the data in my own tooling instead of reading it off a page.

**Acceptance criteria**
- **Given** I am on an allowlisted network range, **when** I request the inventory endpoint,
  **then** I receive JSON containing the same resources, groupings, and collection timestamp shown
  in the browser.
- **Given** I am not on an allowlisted network range, **when** I request the endpoint, **then** the
  request is blocked at the edge exactly as the browser view is.
- **Given** I supply a parameter that is not one of the expected names, types, or values, **when**
  the request is handled, **then** it is rejected and no data is returned.
- **Given** I issue requests faster than the configured limit, **when** the limit is exceeded,
  **then** further requests are throttled rather than served.
- **Given** an error occurs while serving my request, **when** I read the response, **then** it is
  generic and free of stack traces, internal paths, and account identifiers.

---

# Enabler stories

These carry no user-visible slice, so they name no persona. Each exists because the requirements
make it blocking, and each is listed here rather than force-fitted onto a journey story (story plan
Q9 = B).

## US-09 [Enabler] — Supply-chain integrity
*Satisfies SECURITY-10.*

- **Given** the blueprint's Python dependencies, **when** the build runs, **then** every dependency
  resolves to a pinned version and is verified against a recorded hash.
- **Given** the Lambda container images, **when** they are built, **then** their base image is
  pinned by digest rather than by a mutable tag.
- **Given** a build of the blueprint, **when** it completes, **then** a vulnerability scan has run
  against the produced image and an SBOM has been generated.
- **Given** a dependency with a known vulnerability above the agreed threshold, **when** the build
  runs, **then** the failure is surfaced rather than passing silently.

## US-10 [Enabler] — Property-based test suite
*Satisfies PBT-01 through PBT-10.*

- **Given** the tagging and aggregation logic, **when** the test suite runs, **then** property-based
  tests execute alongside example-based tests, neither replacing the other.
- **Given** the candidate properties recorded in the requirements, **when** the suite is written,
  **then** each has a corresponding property test: snapshot round-trip, aggregation count
  invariants, collection idempotence, comparison against a reference implementation, and
  tag-completeness classification.
- **Given** a property test generates inputs, **when** it runs, **then** it uses domain-specific
  generators — realistic ARNs and `cornell:*` tag maps of varying completeness — not raw primitives.
- **Given** a property test fails, **when** the failure is reported, **then** the input has been
  shrunk to a minimal case and the seed is recorded so the failure can be reproduced exactly.
- **Given** the aggregation logic, **when** it is tested, **then** it is exercised without network
  access to AWS.

## US-11 [Enabler] — Access logging
*Satisfies SECURITY-03.*

- **Given** a request reaches the distribution, **when** it is served or blocked, **then** it is
  recorded in access logs.
- **Given** a request is blocked by the network allowlist, **when** I inspect the logs, **then** the
  block is visible, so a legitimate viewer being turned away can be diagnosed rather than guessed at.
- **Given** the storage holding the site and snapshot, **when** it is accessed, **then** that access
  is logged.
- **Given** access logs exist, **when** their retention is checked, **then** it is at least the
  period the requirements set.

## US-12 [Enabler] — Application logging
*Satisfies SECURITY-04.*

- **Given** the collector or the API runs, **when** it emits a log line, **then** the line is
  structured JSON in a centralized log group.
- **Given** any log line produced by the blueprint, **when** it is inspected, **then** it contains
  no credentials, secrets, or personal data.
- **Given** a request or collection run, **when** I trace it through the logs, **then** its start,
  outcome, and any error are all present.
- **Given** a collection run partially fails, **when** I read the logs, **then** what succeeded and
  what did not is distinguishable.

## US-13 [Enabler] — Resiliency alarms
*Satisfies RESILIENCY-07.*

- **Given** a scheduled collection fails, **when** the failure occurs, **then** an alarm raises
  rather than the dashboard quietly continuing to serve an old snapshot.
- **Given** the snapshot has not been refreshed within its expected window, **when** that window
  passes, **then** a staleness alarm raises.
- **Given** the collector or API function errors or is throttled, **when** the rate crosses the
  configured threshold, **then** an alarm raises.
- **Given** a service quota relevant to this blueprint approaches its limit, **when** utilization
  crosses the agreed threshold, **then** that is alarmed before it causes a failure.

## US-14 [Enabler] — Operational monitoring
*Satisfies RESILIENCY-05, RESILIENCY-06, RESILIENCY-09.*

- **Given** the blueprint is deployed, **when** its operational health is reviewed, **then** metrics
  for latency, error rate, throughput, and invocation counts are collected for both functions.
- **Given** those metrics, **when** an operator looks for a single view, **then** a dashboard
  definition exists showing the blueprint's key health indicators.
- **Given** the API is running, **when** its health endpoint is called, **then** it reports whether
  the snapshot store is readable, not merely that the process is alive.
- **Given** the functions are deployed, **when** their configuration is inspected, **then**
  concurrency limits are set, bounding both blast radius and cost.
- **Given** this is a single-service blueprint, **when** distributed tracing is considered, **then**
  it is recorded as not applicable rather than left unaddressed.

## US-15 [Enabler] — Deploy through the pipeline
*Satisfies FR-6 and FR-7. Every other story in this document depends on this one: until the stack
actually deploys through the pipeline, no other story can be demonstrated. Per story plan Q8 = A
that dependency is stated here in prose rather than as a marker on each story.*

- **Given** the blueprint's templates, **when** the repository's validation runs, **then** every
  template is registered in the stack registry and every registered template exists.
- **Given** a template registered as pipeline-deployed, **when** validation runs, **then** it has a
  matching pipeline action — so the failure mode of a green build that deploys nothing cannot occur
  silently.
- **Given** the stack is deployed by the pipeline, **when** its name is checked, **then** it follows
  the `<application>-<environment>-<name>` convention the pipeline's role is scoped to.
- **Given** the stack is deployed, **when** its parameters are inspected, **then** every one was
  passed explicitly by the pipeline rather than falling back to a template default.
- **Given** the leftover copy of the `hello-world` template in this blueprint's directory, **when**
  the blueprint is complete, **then** it has been repurposed as this blueprint's deployment marker —
  retagged to `dashboard`, redescribed, and version-reset — rather than deleted or left claiming to
  be `hello-world`.
- **Given** every resource this blueprint creates, **when** its tags are checked, **then** all four
  required `cornell:*` tags are present.
- **Given** the blueprint is ready to push, **when** the repository's check script runs, **then** it
  passes.

---

# Deferred / Stretch — cost data

> **⚠️ SUPERSEDED 2026-08-07 — see the Round-2 section below (US-16 … US-25).** The decision these two
> placeholders were blocked on has been made: **Cost Explorer**, per decision T1 in
> `requirements/requirement-amendment-questions-telemetry-round-2.md`. US-D1 and US-D2 are therefore
> replaced by real stories with real criteria — US-16/US-17 carry US-D1's and US-D2's intent, and the
> open questions listed under US-D1 are answered in `amendments/telemetry-fr9-2026-08-07.md` FR-10.5
> and FR-10.8. **The two stories below are kept as the record of what was approved on 2026-08-03, not
> as work to pick up**, and their exemption from INVEST no longer applies to anything live.

**These are placeholders, not ready-to-build stories.** The requirements deliberately leave the cost
data source undecided (Cost Explorer API vs. Cost and Usage Report), and that decision has real
consequences — cost allocation tag activation, latency, and whether this account can configure an
organization-level export at all. Acceptance criteria are therefore **TBD** until it is made.

**This section is exempt from the INVEST verification below**: with TBD criteria these stories
cannot satisfy "Testable". They are recorded so the intended shape is visible, not so they can be
picked up. v1 stories and enabler stories are held to INVEST in full.

## US-D1 [Deferred] — See cost alongside inventory

**As a** Dashboard viewer,
**I want** to see cost figures next to the resources they came from, joined on
`cornell:deployment-id`,
**so that** I can tell what a deployment actually costs rather than only what it contains.

**Acceptance criteria**: TBD — blocked on the cost data source decision.

**Open questions to resolve first**
- Cost Explorer API or Cost and Usage Report?
- If Cost Explorer: have `cornell:*` been activated as user-defined cost allocation tags in the
  Billing console, and has the activation delay elapsed?
- If CUR: does this account have access to configure a payer/organization-level export?
- What granularity and time window should be shown?
- What is shown for resources whose tags were only recently applied, and whose cost data therefore
  predates their attribution?

## US-D2 [Deferred] — See cost grouped by owner and blueprint

**As a** Dashboard viewer,
**I want** cost totalled by `cornell:owner` and `cornell:blueprint` as well as by deployment,
**so that** spend can be attributed the same three ways inventory already is.

**Acceptance criteria**: TBD — blocked on the same decision as US-D1.

---

# INVEST verification

Applied to US-01 through US-15. The Deferred / Stretch section is exempt, as stated above.

| Criterion | How it holds |
|---|---|
| **Independent** | Each story is demonstrable on its own once the stack deploys. US-15 is the shared precondition for demonstrating anything, which is a deployment fact rather than a story-to-story coupling. |
| **Negotiable** | Stories state what the viewer needs and what must be observably true. They avoid naming specific AWS services, table shapes, or function layouts — those are Application Design's decisions. |
| **Valuable** | Every US-01..US-08 story names the gain for `P-01`. US-09..US-15 are labelled `[Enabler]` and name the blocking requirement they discharge instead, per plan Q9 = B. |
| **Estimable** | Each story's scope is bounded by its criteria; none says "and everything related". |
| **Small** | US-01..US-08 are single-capability vertical slices. The enabler stories are each scoped to one rule family. |
| **Testable** | Every criterion is observable and can pass or fail. No criterion says "works correctly", "is secure", or "is performant". |

---

# Coverage

Story plan Q3 = A keeps requirement IDs out of story text, so traceability lives here.

## Functional requirements → stories

| Requirement | Covered by |
|---|---|
| FR-1 Resource inventory from `cornell:*` tags | US-02 (FR-1.1, FR-1.2, and pagination completeness), US-03 (FR-1.3), US-04 (FR-1.4) |
| FR-2 Periodic snapshot | US-07 (FR-2.1, FR-2.3), US-05 (FR-2.2), US-D1/US-D2 shape the extensibility in FR-2.4 |
| FR-3 Read API | US-08 (all of FR-3.1–FR-3.5) |
| FR-4 Web UI | US-01 (FR-4.1, FR-4.2, FR-4.5), US-02/US-03/US-04/US-05 (FR-4.3), US-06 (FR-4.4) |
| FR-5 Network-layer access control | US-01 (FR-5.1, FR-5.3, FR-5.5), US-08 (FR-5.2). FR-5.4 — no VPC/subnet/VPN/Direct Connect/Transit Gateway resources — is a prohibition, so it is verified by the absence of such resources rather than by a story. |
| FR-6 Repurpose the stray template | US-15 |
| FR-7 Platform wiring | US-15 |
| FR-8 Cost data (stretch goal) | US-D1, US-D2 — deliberately placeholders |

**No v1 functional requirement is uncovered.**

## Non-functional requirements → stories

| Rule | Covered by |
|---|---|
| SECURITY-01 encryption at rest | Application Design / Infrastructure Design — a template property with no observable behaviour to write a criterion against |
| SECURITY-02 encryption in transit | US-01 |
| SECURITY-03 access logging | US-11 |
| SECURITY-04 application logging | US-12 |
| SECURITY-05 input validation | US-08 |
| SECURITY-06 least-privilege IAM | Application Design / Infrastructure Design; the documented `tag:GetResources` exception is recorded in `requirements.md` §4.6 |
| SECURITY-07 restrictive network config | US-01, US-08 |
| SECURITY-08 application access control (no CORS wildcard) | US-08 |
| SECURITY-09 hardening | US-01 (origin not directly reachable), US-06 (generic errors) |
| SECURITY-10 supply chain | US-09 |
| SECURITY-11 security headers | US-01 |
| SECURITY-12 secure design (rate limiting) | US-08 |
| SECURITY-13 authentication | **Accepted exception** — `requirements.md` §4.6. US-01 states the absence of a login as expected behaviour rather than implying auth exists; `personas.md` records who that excludes. |
| SECURITY-14 integrity | US-10 (no unsafe deserialization is exercised by the round-trip property), Application Design for SRI |
| SECURITY-15 fail-safe defaults | US-06 |
| PBT-01..10 | US-10 |
| RESILIENCY-01, -02, -03, -11, -12, -13 | Documented decisions and justifications in `requirements.md` §4.3 — not story-shaped |
| RESILIENCY-04, -14, -15 | Deferred to NFR Design per the extension's own scoping |
| RESILIENCY-05, -06, -09 | US-14 |
| RESILIENCY-07 | US-13 |
| RESILIENCY-08 multi-zone | Satisfied inherently by the managed services chosen; verified at Infrastructure Design |
| RESILIENCY-10 dependency isolation | US-06 (graceful degradation), US-02 (no silently truncated inventory); timeouts and bounded retries are verified at Application Design |

**Requirements deliberately not story-covered**, and why: rules that are template properties or
recorded decisions rather than observable behaviours cannot be given a criterion that passes or
fails at the story level. They are named above so the gap is visible rather than implied, and each
is carried by a later stage that can verify it.

## Persona → stories

`P-01` Dashboard viewer appears in every story in Journeys 1–4 (US-01..US-08) and in both deferred
stories. US-09..US-15 name no persona by design, being labelled `[Enabler]`.

---
---

# Round 2 (2026-08-07) — usage telemetry and cost

**Source**: `amendments/telemetry-fr9-2026-08-07.md` (FR-9, FR-10), from decisions T1–T8 in
`requirements/requirement-amendment-questions-telemetry-round-2.md`. This is the second
Requirements → Stories pass that the 2026-08-03 telemetry amendment queued (Q3 = B).

**Same conventions as above**: classic format, Given/When/Then, thin vertical slices, no priority or
dependency markers, requirement IDs kept out of story text. Persona is still `P-01` — the pass adds
goals, not an audience (see the amendment note in `personas.md`).

> **⚠️ PARTLY AMENDED same day — see `amendments/telemetry-a3-measured-2026-08-07.md`.** Measurement
> against the real account changed two things here. **US-20 and US-21 get real data on delivery after
> all** — `AWS/Bedrock` supplies requests-by-model, input/output tokens and error counts per model with
> no instrumentation, so their data-present criteria are testable against the account rather than only
> against fixtures (volume is tiny: 2 invocations / 14 days). **US-17 needs one more criterion**: a
> Cost Explorer tag grouping *succeeds* and returns 100% of spend under an empty-value key
> (`cornell:blueprint$`), which a naive reader would render as a real attributed group — see the added
> criterion in that story. US-18, US-19, US-22 and US-23 are unchanged and still render
> *not instrumented*.

**One thing to hold in mind while reading these.** Decision T6 means **no blueprint is instrumented
in this pass**, so US-19 … US-22 have no live emitter and will render their empty state on delivery.
That does **not** make them TBD placeholders the way US-D1/US-D2 were: their criteria are fully
writable and testable today, because each specifies behaviour for *data present* (against fixtures)
**and** for *data absent* (the state a real deployment will actually show). The absent case is not a
consolation criterion — with T6 it is the one a viewer sees first, which is why it is written first
in each story.

---

# Journey 5 — Knowing what the platform costs

## US-16 — See what the platform is costing right now

**As a** Dashboard viewer,
**I want** to see total platform cost for today, this month, and the year so far,
**so that** I can answer "what is this costing us" without a Billing console login I do not have.

**Acceptance criteria**
- **Given** cost data has been collected, **when** I open the financial view, **then** I see a
  today, a month-to-date, and a year-to-date total, each with the currency stated.
- **Given** the upstream cost data lags behind real time, **when** I read the "today" figure,
  **then** it is labelled as of the last finalized day rather than presented as up-to-the-minute, and
  the date it covers is shown.
- **Given** cost data has never been collected, **when** I open the financial view, **then** I see an
  explicit "no cost data collected yet" state, distinguishable from a genuine zero spend.
- **Given** the cost data source cannot be read at all, **when** I open the financial view, **then** I
  see an explicit unavailable state, and **no** figure that could be mistaken for real spend.
- **Given** a cost figure is displayed, **when** I look for its age, **then** its collection timestamp
  is shown, exactly as the inventory views show theirs.

## US-17 — See cost attributed to an application and a deployment

**As a** Dashboard viewer,
**I want** platform cost broken down by blueprint and by deployment,
**so that** I can tell which application is responsible for the spend rather than only the total.

**Acceptance criteria**
- **Given** cost data grouped by tag is available, **when** I view the breakdown, **then** cost is
  totalled per blueprint and per deployment, and the parts sum to the stated total.
- **Given** spend exists that carries no attribution tag, **when** I view the breakdown, **then** it
  appears in an explicit unattributed group rather than being dropped or silently folded into
  another group.
- **Given** the required tags have not been activated for cost attribution upstream, **when** I view
  the breakdown, **then** I am told attribution is unavailable and why — and I am **not** shown zeros
  that would read as "this blueprint costs nothing".
- **Given** attribution was activated part-way through the period I am viewing, **when** I read a
  year-to-date breakdown, **then** the period before attribution began is identified as
  unattributable rather than shown as zero spend.
- **Given** several agents run inside one deployment, **when** I view infrastructure cost, **then** it
  is **not** split per agent, because the underlying billing cannot support that split.
- **Given** the upstream returns a tag grouping in which the tag value is empty — a successful response,
  not an error — **when** that group is read, **then** it is treated as the unattributed bucket and is
  **never** rendered as a named tag value. *(Added by A3: measured against the real account, grouping
  by `cornell:blueprint` returns HTTP 200 with a single group keyed `cornell:blueprint$` holding 100%
  of spend. A reader that trusts the response shape would display one confident, wrong attribution.)*
- **Given** the unattributed bucket accounts for all spend in the period, **when** I open the
  breakdown, **then** I see the attribution-unavailable state rather than a breakdown with one group.

## US-18 — See estimated model cost, clearly marked as an estimate

**As a** Dashboard viewer,
**I want** to see what the language-model usage is costing, and to know it is an estimate,
**so that** I can reason about model spend without mistaking a derived figure for a bill.

**Acceptance criteria**
- **Given** no application is reporting token usage, **when** I open the model-cost panel, **then** I
  see the not-instrumented state naming which blueprints are not reporting, and **not** a figure of
  zero.
- **Given** token counts and a configured rate table are available, **when** model cost is shown,
  **then** it is labelled an estimate everywhere it appears, including in any total it contributes to.
- **Given** both estimated model cost and billed platform cost are on screen, **when** I read them,
  **then** the two are visually distinguishable and are not silently summed into one unqualified
  figure.
- **Given** the rates used to produce the estimate, **when** they need correcting, **then** they can
  be changed without a code change or a redeploy of the application logic.
- **Given** a model has no rate configured, **when** its usage is priced, **then** that is surfaced as
  a known gap rather than counted as zero cost.

## US-19 — See what a deployment costs per completed task

**As a** Dashboard viewer,
**I want** cost expressed per completed task,
**so that** I can judge whether a deployed application earns what it costs.

**Acceptance criteria**
- **Given** no application reports completed tasks, **when** I open this panel, **then** I see the
  not-instrumented state, and **no** figure, zero, blank, or division error.
- **Given** completed-task counts and cost are both available, **when** the per-task figure is shown,
  **then** it states which cost it divides — estimated model cost, billed platform cost, or both.
- **Given** a period in which cost exists but no task was completed, **when** the figure is computed,
  **then** I am shown that no tasks completed rather than an infinite or blank result.

---

# Journey 6 — Knowing whether it is used, and whether it works

## US-20 — See how much each model is used

**As a** Dashboard viewer,
**I want** request counts and token usage broken down by model,
**so that** I can see which models are actually being used and how heavily.

**Acceptance criteria**
- **Given** no application reports usage, **when** I open the adoption view, **then** I see the
  not-instrumented state naming the blueprints found and not reporting.
- **Given** an application reports usage, **when** I view the breakdown, **then** request counts,
  input tokens, and output tokens are each shown per model.
- **Given** an application declares a counter but has sent no datapoints in the window I am viewing,
  **when** I read that counter, **then** I see a no-data-yet state distinct from both
  not-instrumented and from a failed read.
- **Given** the counters cannot be read at all, **when** I open the view, **then** I see an explicit
  read-failure state and no fabricated figures.
- **Given** an application not previously reporting begins to report, **when** its data arrives,
  **then** it appears without any change to this dashboard.

## US-21 — See how often requests fail or time out

**As a** Dashboard viewer,
**I want** error rate and timeout rate for model calls,
**so that** I can tell whether a deployed application is actually working for its users.

**Acceptance criteria**
- **Given** no application reports these counters, **when** I open the panel, **then** I see the
  not-instrumented state rather than a reassuring zero-percent rate.
- **Given** an application reports failures and total requests, **when** a rate is shown, **then** it
  is derived from both counts, and the counts behind it are available to me — not only the ratio.
- **Given** I change the time window, **when** the rate is recomputed, **then** it reflects that
  window rather than a pre-computed ratio that cannot be re-aggregated.
- **Given** these rates concern the model call, **when** I read them, **then** they are
  distinguishable from the dashboard's own operational error metrics, so a failing model call is not
  read as a failing dashboard.

## US-22 — See whether the application's answers are any good

**As a** Dashboard viewer,
**I want** human approval rate and prompt success rate,
**so that** I have a signal about usefulness and not merely about volume.

**Acceptance criteria**
- **Given** no application reports these counters, **when** I open the panel, **then** I see the
  not-instrumented state, because no platform metric can substitute for them.
- **Given** an application reports them, **when** I read a rate, **then** the definition of success
  or approval that the application declared is shown alongside it — these are application-defined
  and are not comparable across applications without it.
- **Given** two applications define success differently, **when** both are displayed, **then** their
  rates are not aggregated into a single cross-application figure.

## US-23 — See usage attributed to the right agent

**As a** Dashboard viewer,
**I want** usage and estimated model cost attributed per agent within a deployment,
**so that** attribution still holds when one blueprint runs several agents.

**Acceptance criteria**
- **Given** a deployment runs exactly one agent, **when** I view its usage, **then** it is attributed
  correctly with no extra configuration on the emitting side.
- **Given** a deployment runs several agents, **when** I view its usage, **then** each agent's
  counters are attributed separately rather than collapsed into one deployment total.
- **Given** usage is attributed per agent, **when** I total the agents within a deployment, **then**
  the total equals the deployment's figure.
- **Given** estimated model cost is attributed per agent, **when** I look for infrastructure cost per
  agent, **then** it is absent by design rather than estimated or implied.

---

# Round-2 enabler stories

## US-24 [Enabler] — The telemetry emission contract
*Satisfies FR-9.1 through FR-9.4, and NFR-T3, NFR-T5.*

- **Given** a blueprint that wants to be visible to usage telemetry, **when** it consults the
  contract, **then** it finds a declaration format for what it emits and a runtime convention for how
  to emit it, without needing to read this dashboard's code.
- **Given** a blueprint that declares no telemetry, **when** the contract is applied to it, **then**
  it is treated as reporting nothing, and remains fully inventoried and cost-attributed.
- **Given** an emitted measurement, **when** its dimensions are inspected, **then** they identify the
  deployment and the agent, and contain no tag value, ARN, personal identifier, or other
  high-cardinality value.
- **Given** a deployment that runs one agent, **when** it emits without configuring an agent
  identifier, **then** the agent identifier defaults to the deployment identifier.
- **Given** the reader, **when** it collects telemetry, **then** it reads only counters a manifest
  declares plus a fixed list of platform namespaces, and never discovers and renders arbitrary
  metrics.
- **Given** a new emitting blueprint, **when** its counters arrive, **then** the dashboard renders
  them generically with no blueprint-specific code — which is the test of whether this contract is
  correct.

## US-25 [Enabler] — Cost collection that does not itself cost much
*Satisfies FR-10.4 and NFR-T4, NFR-T6.*

- **Given** the upstream cost API is billed per request and its data advances only daily, **when**
  cost collection is scheduled, **then** it runs on its own daily cadence and not on the inventory
  schedule.
- **Given** the cost cadence needs changing, **when** a new value is supplied to the stack, **then**
  the schedule changes without editing the blueprint's template.
- **Given** the new permissions this pass requires, **when** they are inspected, **then** they are
  read-only and least-privilege, and any unavoidable account-wide breadth is documented as an
  accepted exception.
- **Given** the operating cost of collection, **when** the blueprint's documentation is read, **then**
  the per-request charge, the upstream lag, and the manual attribution-activation step are all stated.

---

# Round-2 INVEST verification

Applied to US-16 … US-25. Nothing in this section is exempt — unlike US-D1/US-D2, which were exempt
because their criteria were TBD.

| Criterion | How it holds |
|---|---|
| **Independent** | Each story is demonstrable alone. US-24 is a shared precondition for US-20…US-23 in the same way US-15 is for everything — a delivery fact, not story coupling. |
| **Negotiable** | Criteria name observable behaviour, not services. "The upstream cost API", not "Cost Explorer"; "declares a counter", not a YAML schema. The mechanisms are in the amendment, where design can revisit them. |
| **Valuable** | US-16…US-23 each name P-01's gain. US-24/US-25 are `[Enabler]` and name the requirement they discharge. |
| **Estimable** | Each is bounded by its criteria. The riskiest unknowns — usage-type strings, per-model rates — are quarantined in FR-10.8 as verify-before-build rather than hidden inside a story. |
| **Small** | Each covers one panel or one contract concern. Cost and usage are deliberately not one story. |
| **Testable** | Every criterion can pass or fail. **The T6 case is what makes this hold**: because each story specifies the data-absent behaviour, every story is testable against the system as it will actually be delivered, not only against fixtures. |

---

# Round-2 coverage

| Requirement | Covered by |
|---|---|
| FR-9.1 contract-not-feature, graceful non-participation | US-24, US-20 |
| FR-9.2 EMF emission mechanism | US-24 (as observable behaviour; the mechanism itself is verified at design/build) |
| FR-9.3 dimensions incl. `agent_id` default | US-23, US-24 |
| FR-9.4 manifest declaration, `emits: false` first-class | US-24 |
| FR-9.5 reader, closed allowlist, additive snapshot section | US-24, US-20 |
| FR-9.6 the required counters | US-20 (requests/tokens), US-21 (error/timeout), US-22 (approval/success), US-19 (completed tasks) |
| FR-9.7 no emitter this pass; three distinct empty states | US-20 (all three states named), and the absent-data criterion opening US-18…US-22 |
| FR-10.1 Cost Explorer chosen | US-16 (behaviourally); the decision itself is recorded in the amendment, not story-shaped |
| FR-10.2 today / month / YTD, no budget | US-16 |
| FR-10.3 breakdown by blueprint + deployment; no department; asymmetric agent split | US-17, US-23 |
| FR-10.4 separate daily schedule | US-25 |
| FR-10.5 activation, non-retroactivity, lag, denied access | US-16, US-17, US-25 |
| FR-10.6 estimated model cost, labelled, configurable rates | US-18 |
| FR-10.7 cost per completed task | US-19 |
| FR-10.8 verify-before-build items | **Not story-covered, deliberately** — these are open verification tasks, not behaviours. Named here so the gap is visible. |
| FR-10.9 no per-user attribution | **Not story-covered** — a prohibition, verified by the absence of the feature, as FR-5.4 was |
| NFR-T1 estimates distinguishable | US-18 |
| NFR-T2 rate table configurable | US-18 |
| NFR-T3 low-cardinality, no PII dimensions | US-24 |
| NFR-T4 bounded cost-API calls | US-25 |
| NFR-T5 closed allowlist | US-24 |
| NFR-T6 least-privilege IAM | US-25 |
| NFR-T7 three distinct empty states | US-20, and every data panel's absent-data criterion |

**Superseded**: US-D1 → US-16/US-17; US-D2 → US-17. US-D1's five open questions are answered in
FR-10.5 (attribution activation, lag, granularity, late-tagged resources) and FR-10.1 (source
choice); the CUR access question is answered by rejecting CUR.
