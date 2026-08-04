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
