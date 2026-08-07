# Functional Design Plan — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Functional Design (second and final unit)
**Date**: 2026-08-03
**Unit**: U-02 — C-01 Collector, C-02 Snapshot Store, C-03 Read API, C-06 Web UI, C-07 Edge,
C-08 Deployment Marker, C-09 Observability Set
**Stories**: US-01, US-02, US-06, US-07, US-08, US-09, US-11, US-12, US-13, US-14, US-15 (+ US-D1,
US-D2 deferred)
**Approach**: one pass over the whole unit, as Units Generation approved.

---

## What U-02 inherits before a single question is asked

U-01 is complete and approved, and it arrives with **four obligations U-02 must discharge**. They are
listed first because each one is a thing a fresh Functional Design would silently omit:

| # | Obligation | Source |
|---|---|---|
| 1 | `Freshness.INVALID` needs a **sixth row** in C-03's degraded-state table: **503 / `error`**, not 200. A future `collected_at` is a fault, not a state of the world. | U-01 NFR Design, Q6 |
| 2 | `skipped_count`, `duplicates_removed` and `raw_returned` must reach the **UI**. If they stop at the API, the "surface the count" half of the skip-and-count decision is never delivered and the honesty guarantee ends at a boundary nobody sees. | U-01 Functional Design, Q1 |
| 3 | **C-01 must log enough at its own boundary to identify a skipped resource.** U-01 deliberately cannot — its exceptions carry a category only, because `cornell:owner` holds a NetID and an exception message can reach a log group. So if C-01 does not log it, malformed ARNs become undebuggable. | U-01 NFR Requirements, Q6 |
| 4 | **RESILIENCY-04 and -15 are assigned here** — rollback mechanism and deployment style, incident response. Deferral count: **2**. A third would be a pattern. | U-01 NFR Design, Q6 |

Also inherited, and not reopened: U-01's `__all__` is the contract. U-02 imports from
`dashboard.core` and never from `dashboard.core.model` or `.aggregation`, so U-01's internals can move
without breaking a unit boundary. U-02 **must not** reimplement anything U-01 exports — if a grouping
loop appears in the API handler, the boundary has been crossed.

## New constraint that arrived mid-workflow

`contracts/ui-design-language.md` is now binding on C-06, and its §2 (WCAG 2.2 AA) and §3 (Cornell
logo) have **no exemption path**. A dashboard addendum already exists at
`blueprints/dashboard/docs/design-language.md`, written by another team ahead of the template, and it
commits this blueprint to conformance.

It also imposes something the approved design never considered: a **two-accent series ceiling**. Once
green/orange/red are reserved for status, Cornell's palette leaves blue `#006699`, navy `#073949`, and
dark gray for de-emphasis. **US-03's grouping views will routinely exceed two categories** — grouping
by `cornell:blueprint` across a shared account produces many. Question 5 is that problem.

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

---

### Question 1 — What is the pagination bound, and what happens when it is hit?

`component-methods.md` gives `collect_all_resources(client, page_limit)` and says breaching
`page_limit` is an **error, not a truncation** — because a silent truncation is the
under-reporting-while-looking-successful failure the whole design exists to avoid. But the number was
never chosen.

Context: §4.4 states the expected volume as **tens to low hundreds** of resources. The Tagging API
returns up to 100 resources per page by default.

**A) 50 pages (~5,000 resources), breach raises and the snapshot is not written** ← *recommended*
   *Why*: an order of magnitude above the stated ceiling, so it will not fire in normal operation, but
   low enough to stop a runaway from becoming an unbounded Lambda bill. Breaching means something is
   badly wrong — either the account grew 50× or pagination is looping — and both deserve a failed
   invocation and an alarm rather than a quietly partial snapshot.
   *Cost*: if the account genuinely grows past ~5,000 tagged resources, the dashboard stops updating
   until someone raises the parameter. That is the intended behaviour, but it *will* look like an
   outage, so the alarm text needs to say which limit was hit.

**B) 10 pages (~1,000 resources)** — tighter, fires sooner, cheaper worst case.
   *Cost*: closer to plausible real growth, so more likely to fire as a false alarm.

**C) No limit; rely on the Lambda timeout instead.**
   *Cost*: a timeout mid-pagination is indistinguishable from any other timeout, so the specific
   diagnosis "pagination did not terminate" is lost. The design's whole stance is that failures should
   name themselves.

X) Other

[Answer]:A

---

### Question 2 — What is the default refresh interval?

FR-2.3 makes it a stack parameter. This sets the default, and it also sets the staleness threshold,
which U-01's BR-07 fixed at **3 × interval**.

**A) 1 hour → stale after 3 hours** ← *recommended*
   *Why*: tag inventory changes when someone deploys, which during a workshop is a handful of times a
   day. Hourly is well inside "fresh enough to trust" while costing 24 Lambda invocations a day —
   effectively nothing. Three hours to stale tolerates one missed run plus jitter.
   *Cost*: a resource deployed two minutes ago may not appear for an hour. `collected_at` is displayed
   precisely so that is visible rather than confusing.

**B) 15 minutes → stale after 45 minutes** — much fresher; 96 invocations/day, still negligible.
   *Cost*: 4× the Tagging API calls, and a tighter staleness window means transient collector trouble
   shows as "stale" more often.

**C) 6 hours → stale after 18 hours** — cheapest.
   *Cost*: during a two-day workshop, a 6-hour-old inventory is close to useless for "did my deploy
   land?"

X) Other

[Answer]:A

---

### Question 3 — Where do the Cornell IP ranges for the WAF allowlist come from?

FR-5.1 requires **deny-by-default** with an allowlist of Cornell ranges, and this is the single control
standing between the dashboard and the internet. It is also the item most likely to look like an
outage when wrong — `execution-plan.md` names exactly that as a Medium-risk reason.

**A) A CloudFormation parameter taking a comma-separated CIDR list, with no default** ← *recommended*
   *Why*: no ranges are baked into a public repo; the pipeline passes them explicitly like every other
   parameter; and changing the allowlist is a normal reviewed template change. No default means a
   misconfigured deploy **fails** rather than silently admitting everyone or nobody.
   *Cost*: the pipeline action must carry the list, so the real ranges live in `pipeline.yml` — which
   is public. CIDR ranges are not secret, but they are reconnaissance-useful, and that should be a
   conscious acceptance rather than a discovery.

**B) An AWS-managed prefix list referenced by ID** — ranges live outside the repo entirely.
   *Why*: cleanest for the public-repo concern; updated without a template change.
   *Cost*: the prefix list must be created and maintained out of band, which is click-ops or a
   separate stack, and `CLAUDE.md` forbids the former. Also a WAF IPSet cannot reference a VPC prefix
   list, so this needs verification before it is chosen.

**C) A hardcoded IPSet in the template.**
   *Cost*: ranges in a public repo with no way to change them without a code change. Rejected in
   advance unless you want it.

**D) You choose** — I pick and record the reasoning. (That lands on A, with the public-repo
   acceptance recorded explicitly.)

X) Other

[Answer]:A

---

### Question 4 — How does the UI fetch and hold state?

C-06 is React + Vite (Q9 of Application Design). Q5 of Application Design gave it **distinct API paths
per view**, so each view is one fetch. This is genuinely undecided and shapes most of the UI code.

**A) One fetch per view on mount, plain `useState` + `useEffect`, no client-side router** ← *recommended*
   Tabs switch a local `view` variable; each view fetches its own endpoint and holds
   `{loading, data, error}`.
   *Why*: four read-only views with no shared mutable state and no forms. A store or a data-fetching
   library would be infrastructure for a problem this UI does not have, and every dependency added is
   dependency surface that Q11 = B decided not to scan. Keeps the bundle small and the code legible to
   whoever picks it up after the workshop.
   *Cost*: switching tabs refetches. At this data size that is a non-issue, but it is a real
   behaviour, not a hidden one.

**B) A client-side router (`react-router`) with per-route data loading** — deep-linkable views.
   *Why*: a URL per view means someone can share a link to the tag-gap report.
   *Cost*: a dependency, plus CloudFront must rewrite unknown paths to `index.html` for an SPA — which
   interacts with the `/api/*` behaviour split and is easy to get subtly wrong.

**C) A data-fetching library (SWR / React Query)** — caching, revalidation, retries for free.
   *Cost*: client-side caching directly contradicts the design's decision that `/api/*` is
   **no-cache**, and would reintroduce "two views disagreeing about freshness" — the exact failure
   US-05 exists to prevent. Not recommended for this reason specifically.

X) Other

[Answer]:A

---

### Question 5 — Grouping views will exceed two accent colours. What gives?

The UI contract leaves **two** identity-safe accents (blue, navy) plus dark gray, because
green/orange/red are reserved for status. US-03 groups by `cornell:blueprint` and `cornell:owner`,
which in a shared workshop account will produce five, ten, twenty groups.

This is a genuine conflict between an approved requirement and a contract that arrived afterwards, and
§2/§3 of that contract cannot be waived.

**A) Do not encode group identity in colour at all** ← *recommended*
   Grouping views become sorted tables/bars with **text labels** and a single accent for emphasis.
   Colour carries only *status* (fresh/stale/error, tagged/untagged).
   *Why*: it dissolves the conflict instead of negotiating with it — there is no palette to run out
   of, and it is strictly better for accessibility, since colour is never the sole carrier of meaning
   (a WCAG 2.2 requirement anyway, so §2 pushes this way independently). Also honest: twenty
   categorical colours would be unreadable even if the palette allowed them.
   *Cost*: no at-a-glance colour coding across views. A chart with twenty series is not really
   at-a-glance regardless.

**B) Top 2 groups get the accents, everything else "Other" in dark gray** — matches the addendum's
   stated approach for charts.
   *Cost*: collapses the long tail, which for a *tag inventory* is often the interesting part — the
   one-off resource nobody owns is exactly what US-04 is for.

**C) Request a §5-and-below deviation** to add accents, documented in `docs/`.
   *Cost*: the contract permits deviation only at §5 and below, and the palette is **§4** — so this
   may not be declarable at all. Would need the mob, not just us.

X) Other

[Answer]:A

---

### Question 6 — What does "pull the inventory as JSON" (US-08) actually mean?

US-08 says a user wants the inventory as JSON. Ambiguous between a machine interface and a UI feature.

**A) The existing `/api/inventory` endpoint is the answer; the UI adds a visible "copy URL" affordance** ← *recommended*
   *Why*: the endpoint already exists for the UI, so US-08 costs almost nothing and stays a real
   capability rather than a separate export path that could drift from what the UI shows. The
   affordance makes it discoverable, which is the part a bare endpoint misses.
   *Cost*: the consumer must be inside the WAF allowlist, so it is not a public API. That is a
   feature, not a gap.

**B) A download button producing a `.json` file** — friendlier for a non-technical user.
   *Cost*: a second serialization path in the browser that can disagree with the API's bytes.

**C) Both.**

X) Other

[Answer]:A

---

### Question 7 — What exactly alarms, and on what threshold?

US-13 and RESILIENCY-07 require alarms on the two silent degradations. Thresholds were never set, and a
badly-set threshold is either noise or nothing.

**A) Collector failure: 1 failed invocation. Staleness: snapshot age > 3 × interval. Plus Lambda errors and throttles** ← *recommended*
   *Why*: the collector runs hourly, so a single failure is already a real signal and waiting for two
   doubles the blind window. Staleness reuses the *same* threshold as the UI's judgement, so the alarm
   and the screen can never disagree — which matters, because "the dashboard says stale but nothing
   alarmed" destroys trust in both.
   *Cost*: a single transient Tagging API throttle that exhausts retries pages someone. Given
   RESILIENCY-10's bounded retries, this should be rare.

**B) Collector failure: 2 consecutive.** Fewer false pages.
   *Cost*: up to two hours of blindness, and the whole point of the alarm is that a dead collector is
   otherwise invisible.

**C) Also alarm on `skipped_count > 0`** — any malformed resource pages someone.
   *Cost*: turns a designed-for degradation into an alert. Skipping is *expected* behaviour with a
   visible count; alarming on it is how people learn to ignore alarms.

X) Other

[Answer]:A

---

### Question 8 — RESILIENCY-04: rollback and deployment style. Due here, second deferral.

Assigned to this unit rather than deferred a third time.

**A) Rollback = revert the PR and let the pipeline redeploy; deployment style = all-at-once** ← *recommended*
   *Why*: it is what the pipeline already does, and Lambda deploy-by-digest means a revert restores
   the exact previous image rather than rebuilding something similar. The storage stack being separate
   (Q4 of Units Generation) means an application rollback cannot touch the data. All-at-once is honest
   for a single-region, single-account, non-SLA internal tool; canary or blue/green would be
   machinery with no traffic to split.
   *Cost*: a bad deploy is user-visible until the revert lands, which is one pipeline run. And
   `CLAUDE.md` now requires **zero approving reviews**, so a bad revert can also self-merge.

**B) All-at-once + a manual approval action in the pipeline before BlueprintDeploy.**
   *Why*: restores a human gate that branch protection no longer provides.
   *Cost*: changes the pipeline's shape for every blueprint, not just this one. Not ours to impose.

**C) Blue/green via Lambda aliases and weighted routing.**
   *Cost*: real complexity for a dashboard with a handful of users; also needs a CloudFront origin
   story per version.

X) Other

[Answer]:A

---

### Question 9 — RESILIENCY-15: incident response. Also due here.

**A) A runbook section in the blueprint README: what each alarm means, and the first thing to check** ← *recommended*
   Covers collector failure, staleness, WAF lockout, and unreadable snapshot. No rota, no paging tier,
   no severity matrix.
   *Why*: proportionate to workshop teaching infrastructure with no external customers and no SLA
   (which is the same basis on which RESILIENCY-02 recorded RTO/RPO as N/A). A runbook written while
   the design is fresh is worth more than a process nobody rehearses. **Specifically include the
   WAF-lockout case**, because a deny-by-default allowlist failure looks exactly like an outage and
   the person locked out cannot read the dashboard to diagnose it.
   *Cost*: no formal escalation path. If this ever gains real users, that gap becomes real.

**B) A full incident-response process** — severities, roles, escalation, comms.
   *Cost*: ceremony for a system whose worst failure is that organizers cannot see an inventory they
   can also get from the console.

**C) Defer to Operations.**
   *Cost*: this is the third deferral of RESILIENCY-15. Recorded as such if chosen.

X) Other

[Answer]:A

---

## Part A1 — Categories evaluated and NOT asked about

| Category | Why not |
|---|---|
| Domain model / entities | **U-01 owns every entity.** U-02 adds no domain type; it adds handlers, templates and views over U-01's types. Asking again would invite a duplicate model, which is exactly what the boundary forbids. |
| Business rules for grouping, gaps, freshness | BR-01..BR-08, decided and **implemented and tested** in U-01. Not reopened. |
| The API's degraded-state semantics | Decided at Application Design Q8 and extended by U-01's obligation 1. The five-row table plus the `INVALID` row is settled; U-02 implements it. |
| Snapshot storage shape | Application Design Q1: one versioned encrypted JSON object. Settled. |
| Whether reads trigger collection | FR-2.1 / US-07: never. Settled, and enforced by there being no write path. |
| Authentication | No identity system anywhere (FR-5.5). Nothing to design. |
| Cost figures | FR-8 deferred with the data source undecided; US-D1/US-D2 stay unbuilt. |
| §6.4 site-sync ordering | Genuinely open, but it is a **pipeline-topology** decision and belongs to Infrastructure Design, which for this unit will execute. Carried, not asked here. |
| The container build mechanics | `CONTAINER_TARGET` + `CONTAINER_CONTEXT` are established and proven by `builder-mcp`. Infrastructure Design wires it. |

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] All nine `[Answer]:` tags filled
- [x] Mandatory answer analysis — vagueness, undefined terms, contradiction, missing detail,
      option-merging — with follow-ups raised rather than assumptions made
- [x] Record resolved decisions and interactions in a `Part A2`
- [x] **Confirm each of the four inherited obligations is addressed by a specific artifact section**,
      not merely acknowledged

### B2. `domain-entities.md`
- [x] State plainly that **U-02 introduces no domain entities** and why, then document the
      non-domain types it does add: `LoadOutcome` (PRESENT/ABSENT/UNREADABLE), the HTTP response
      envelope, the collector's result type, and the UI's view-state shape
- [x] The import contract: `from dashboard.core import ...` only, never a submodule

### B3. `business-rules.md`
- [x] Collector rules: pagination to exhaustion, the Q1 page limit and its breach behaviour, bounded
      retries with backoff, single `PutObject`, previous snapshot preserved on failure
- [x] Q3 logging rule — what C-01 logs about a skipped resource, and what it must **not** log
- [x] API rules: the route table, the closed `{tag_key}` allowlist, the **six-row** response mapping
      including `INVALID` → 503, generic error bodies with no internals
- [x] Edge rules: deny-by-default, `/api/*` **no-cache** while the site is cached, security headers,
      HTTPS-only, OAC to a private bucket
- [x] Observability rules: the Q7 alarm set and thresholds, structured log shape, retention
- [x] Each rule mapped to its requirement and story; no orphans

### B4. `business-logic-model.md`
- [x] Collector algorithm end to end, with a totality note per function as U-01's has
- [x] API request lifecycle: route → load → classify → derive → respond, showing that **derivation is
      delegated to U-01**, never reimplemented
- [x] Where the three accounting counts travel: snapshot → API response → UI (obligation 2)
- [x] Any properties worth testing at this level, and honestly which are integration tests rather
      than properties — U-02 is mostly I/O, so it will not have ten
- [x] Deployment marker's role (C-08) and the `deployed_by: manual` → `pipeline` flip

### B5. `frontend-components.md` — **mandatory for this unit**
- [x] Component hierarchy, props and state per component (Q4)
- [x] The four views, plus **all six** distinguishable states — including "no data collected yet"
      versus "no resources found", which mean opposite things and render identically if nobody insists
- [x] Where `collected_at`, staleness, and the three accounting counts appear on screen (obligation 2)
- [x] The Q5 decision on colour, and how grouping is encoded instead
- [x] `data-testid` naming per the code-generation automation rules
- [x] UI-contract conformance: §2 WCAG 2.2 AA and §3 logo (**no exemption path**), §4 palette, and the
      strict-CSP consequence — Vite's modulepreload polyfill emits an inline script and must be
      disabled or hash-allowlisted
- [x] API integration points: which endpoint each view calls

### B6. Validation and honest reporting
- [x] Every US-01/02/06/07/08/09/11/12/13/14/15 acceptance criterion maps to a rule or component
- [x] No rule duplicates or contradicts U-01's BR-01..BR-08
- [x] Confirm no design element requires a VPC, subnet, VPN, Direct Connect, Transit Gateway, or any
      identity system
- [x] Report what cannot be settled here with the stage that carries it — expected: §6.4, the WAF
      ranges themselves, and the arm64 image contents

### B7. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 🔧 Functional Design Complete - U-02 Dashboard Platform` and wait for approval

---

## Part A2 — Resolved decisions (Q1–Q9)

All nine clean single selections, all **A**. No vagueness, contradiction, or option-merging. Eight
interactions recorded, **three of which are defects or gaps in my own questions**.

| # | Decision | Answer |
|---|---|---|
| Q1 | Pagination bound | 50 pages (~5,000 resources); breach raises, no snapshot written |
| Q2 | Refresh interval | 1 hour → stale after 3 hours |
| Q3 | WAF allowlist source | CFN parameter, comma-separated CIDRs, **no default** |
| Q4 | UI state | `useState`/`useEffect` per view; no router, no data library |
| Q5 | Grouping colour | **Do not colour-encode group identity at all** |
| Q6 | US-08 JSON | The existing `/api/inventory` endpoint + a copy-URL affordance |
| Q7 | Alarms | Collector failure on 1; staleness > 3 × interval; Lambda errors and throttles |
| Q8 | Rollback | Revert the PR, pipeline redeploys; all-at-once |
| Q9 | Incident response | Runbook section in the blueprint README |

### Interaction 1 — The staleness alarm needs `TreatMissingData: breaching`, or it cannot fire

Q2 = A and Q7 = A deliberately share one threshold (3 hours), so the alarm and the screen can never
disagree. Good. But working out *how* the alarm evaluates snapshot age exposes a trap:

**A collector that never runs emits no metric and no error.** If the EventBridge rule is disabled,
deleted, or its target permission breaks, there are zero invocations — so the *collector failure* alarm
(which watches `Errors`) stays green, because nothing failed. Nothing ran.

The staleness alarm is the safety net for exactly that case, and it only works if **missing data is
treated as breaching**. A CloudWatch alarm on a custom age metric defaults to `missing`, which means an
alarm watching a metric that stops being published sits in `INSUFFICIENT_DATA` — green-looking —
forever.

> **Rule for `business-rules.md`**: the staleness alarm sets `TreatMissingData: breaching`. This is the
> only alarm in the set that detects "the collector is not running at all", as opposed to "the
> collector ran and failed".

Not derivable from either answer alone. It comes from asking what the alarm actually watches.

### Interaction 2 — Q1 = A's breach must be distinguishable, not just an error

Q1 = A raises on breach, which surfaces as a Lambda error, which trips Q7 = A's collector-failure alarm.
The chain works. But Q1's own cost note said a breach "*will* look like an outage, so the alarm text
needs to say which limit was hit" — and an alarm on `Errors` cannot say that, because it sees a count,
not a reason.

So the **collector must log the breach distinguishably** (a dedicated reason code, and the limit value),
and the Q9 = A runbook entry for collector-failure must say "check whether the page limit was hit"
as its first step. Otherwise the operator sees "collector failed" and starts debugging IAM.

### Interaction 3 — GAP IN MY QUESTION: Q3 = A does not cover IPv6

**WAF IPSets are per-address-family.** A single `AWS::WAFv2::IPSet` declares `IPAddressVersion` as
either `IPV4` or `IPV6`; one set cannot hold both. My Q3 asked "where do the ranges come from" and never
asked "which address families".

This matters precisely as much as Q3 said it did: an IPv4-only allowlist **silently locks out any
IPv6-only client**, and that is indistinguishable from an outage to the person affected — the failure
mode Q3 was written to guard against, reintroduced through the question's own blind spot.

Recorded as a decision for **Infrastructure Design**, with the shape stated so it cannot be missed:
either two parameters and two IPSets referenced by one rule group, or an explicit, documented
IPv4-only scope. It is not a detail to be discovered while debugging a lockout.

### Interaction 4 — Q3 = A's mechanics, so the "no default" behaviour actually holds

- The parameter is a `String` of comma-separated CIDRs with `AllowedPattern` and **no `Default`**, so a
  deploy that omits it **fails at CloudFormation** rather than admitting everyone or nobody.
- `AWS::WAFv2::IPSet.Addresses` takes a list, so the template needs `!Split [',', !Ref ...]`.
- The real ranges land in `pipeline.yml`, which is public. **Accepted consciously**: CIDR ranges are not
  secrets, but they are reconnaissance-useful. Recorded here rather than left to be noticed later.

### Interaction 5 — Q4 = A and Q6 = A together mean there is no shareable view link

No router means one URL for the whole app, so nobody can send a colleague a link to the tag-gap view.
Under Q6 = A the copy-URL affordance therefore copies the **API** URL (`/api/inventory`), not a UI
location.

That is coherent — Q6 = A's whole point is that the endpoint *is* the answer — but it is a real
usability consequence of Q4 = A, and it should be recorded rather than discovered as a complaint. The
cheap mitigation if it ever bites is a `?view=` query parameter read on mount, which needs no router.

### Interaction 6 — Q5 = A diverges from the addendum ANOTHER TEAM wrote in this blueprint

`blueprints/dashboard/docs/design-language.md` was written by someone else, ahead of the template, and
it specifies a **two-accent series with dark gray for "Other"** for charts, describing this blueprint as
"the reason §9 exists".

Q5 = A goes further: **no colour encoding of group identity at all.**

This does **not** contradict the contract — it is strictly more conservative than §4 requires, and §2's
"colour is never the sole carrier of meaning" pushes the same way independently. But it does diverge
from that addendum's stated approach, and **that file is not mine to silently rewrite.** Recorded here,
and flagged for the user to relay: the addendum's chart section needs updating, or Q5 = A needs
revisiting, and the people who wrote it should be the ones to decide which.

### Interaction 7 — the alarm destination already exists; do not create a second one

Q7 = A specifies what alarms, but not where the notification goes. Rather than invent an SNS topic:

**`blueprints/notify-topic/` already exists, is registered `deployed_by: pipeline`, and is actively
deployed.** Its own summary is "a single SNS topic other blueprints, scripts, or people can publish to
… the simplest way to wire 'tell me when X happens'", and its `TopicArn` output is described as *"ARN to
publish to, **or to hand to another stack that needs to publish here**"*.

So C-09's alarms publish there. One caveat found by reading the template: **its outputs carry no
`Export:`**, so `Fn::ImportValue` is not available. The ARN must arrive either as a parameter or be
constructed from the naming convention
(`arn:${AWS::Partition}:sns:${AWS::Region}:${AWS::AccountId}:${Application}-${Environment}-notify-topic`).
Choosing between those is **Infrastructure Design's**; the functional rule "alarms reach a human via the
existing notify-topic" is settled here.

### Interaction 8 — Q8 = A's rollback is safe on data, exposed on review

Two halves worth stating together:

- **Safe**: rollback is a PR revert, and Lambda deploys **by digest**, so a revert restores the exact
  previous image rather than rebuilding something similar. Because the storage resources live in a
  separate stack (Q4 of Units Generation), an application rollback structurally cannot touch the
  snapshot or site data.
- **Exposed**: `CLAUDE.md` now requires **zero approving reviews**, so the revert PR can be self-merged
  by the same person — and so could the bad change that caused it. Q8 = A is the right mechanism; the
  gate around it is weaker than when the execution plan was written. Already recorded in amendment
  §A1.1; repeated here because rollback is where it bites.

**Nothing in U-01 is reopened.** BR-01..BR-08, the ten properties, the entities and the `__all__`
contract all stand unchanged.
