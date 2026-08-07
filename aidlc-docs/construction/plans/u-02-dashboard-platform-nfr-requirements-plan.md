# NFR Requirements Plan — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Requirements
**Date**: 2026-08-03
**Unit**: U-02 — C-01, C-02, C-03, C-06, C-07, C-08, C-09
**Inputs**: `u-02-dashboard-platform/functional-design/` (approved 2026-08-03) · `requirements.md`
§4.1–§4.4 · amendments A1–A3

---

## Unlike U-01, nearly every category applies here

U-01's NFR pass recorded ten categories as inapplicable, because a pure library has no uptime, no
endpoint and no storage. **U-02 has all three.** Scalability, availability, performance, security,
reliability, and observability are all live, and the questions below are correspondingly concrete: memory
sizes, retention periods, throttle numbers, TTLs.

Two things shape the answers before any question is asked:

- **§4.4 puts the expected volume at tens to low hundreds of resources.** Nearly every sizing question
  therefore has a generous answer that is also the cheap one. Where a number below looks small, that is
  usually why.
- **§4.1's SECURITY-01..15 and §4.3's RESILIENCY-01..15 already bind.** This stage sets the numbers those
  rules left open; it does not revisit the rules.

## Precedent found, so not asked

`tiny-chatbot` is already a Lambda container blueprint and `aisei-site` is a second one. Between them and
`builder-mcp`, several choices are settled. Re-deciding them would create a second convention for no gain.

| Choice | Established value | Source |
|---|---|---|
| Lambda base image (Python) | **`public.ecr.aws/lambda/python:3.13`** — provides the runtime interface client; handler in `${LAMBDA_TASK_ROOT}`; `CMD` names it | `blueprints/tiny-chatbot/Dockerfile` |
| Base image pinning | **By digest** (`@sha256:…`) | `packages/builder-mcp/Dockerfile`; tiny-chatbot records it as owed |
| Lambda packaging | `PackageType: Image`, `ImageUri` as a parameter | both Lambda blueprints |
| Architecture | **arm64** | Units Generation Q8, confirmed by both |
| Node for a UI build | **`node:24-alpine`**, multi-stage build then runtime | `blueprints/aisei-site/Dockerfile` |
| Container build wiring | `CONTAINER_TARGET` + `CONTAINER_CONTEXT` | `pipeline/pipeline.yml` |
| Alarm destination | the existing `notify-topic` SNS topic | OR-05, decided at Functional Design |

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

---

### Question 1 — Lambda memory and timeout for each function

`tiny-chatbot` uses 128 MB / 10 s; `aisei-site` uses 512 MB / 15 s. The two dashboard functions have
different shapes: the collector makes up to 50 sequential paginated API calls; the API reads one object
and derives one view.

Memory also buys CPU on Lambda, so a larger size can be *cheaper* when the work is CPU-bound, because it
finishes proportionally faster.

**A) Collector 512 MB / 120 s · API 512 MB / 10 s** ← *recommended*
   *Why*: the collector's 50 sequential round trips are latency-bound, and at ~1 s each a 10 s timeout
   would fail on a large account while 120 s leaves headroom without permitting a runaway (Q1 of
   Functional Design already bounds pages). 512 MB gives enough CPU that JSON serialization of a few
   thousand records is not the bottleneck. The API does one `GetObject` plus one pure derivation — 10 s is
   already generous.
   *Cost*: 512 MB on a function that may only need 256 MB. At 24 invocations/day this is cents.

**B) Both 256 MB · collector 60 s · API 5 s** — tighter, marginally cheaper.
   *Cost*: 60 s risks a timeout on a slow upstream day, and a timeout mid-pagination is the failure that
   Q1 of Functional Design specifically wanted to be diagnosable rather than generic.

**C) Collector 1024 MB / 300 s · API 1024 MB / 30 s** — maximum headroom.
   *Cost*: 300 s is five minutes of a runaway before Lambda stops it, and the whole point of the page
   limit was bounding exactly that.

X) Other

[Answer]:A

---

### Question 2 — Is a container cold start acceptable on the API?

Container-image Lambdas cold-start slower than zip — commonly 1–3 s for a small Python image. The API is
user-facing, and a viewer opening the dashboard after an idle period will hit one.

**A) Accept cold starts. No provisioned concurrency** ← *recommended*
   *Why*: provisioned concurrency bills for warm capacity **continuously**, which for a dashboard used a
   few times a day would dominate the entire cost estimate — and this blueprint's own purpose is cost
   visibility, so it should not be gratuitously expensive. A 1–3 s first load, then fast, is the right
   trade for an internal tool with a handful of users.
   *Cost*: the first view after idle feels slow. Worth stating in the README so it reads as expected
   rather than broken.

**B) Provisioned concurrency of 1 on the API** — consistently fast.
   *Cost*: a fixed monthly charge for capacity that is idle almost always. Would roughly rival the WAF
   charge that already dominates the estimate.

**C) A scheduled warmer invocation every N minutes.**
   *Cost*: a cron job whose only purpose is defeating a platform behaviour, plus invocations that do no
   work. Also muddies the collector-failure alarm signal if it shares a function.

X) Other

[Answer]:A

---

### Question 3 — API Gateway throttle limits

FR-3.5 and SECURITY-12 require rate limiting. The realistic threat is not an attacker — the WAF allowlist
already restricts origin — it is **an accidental refresh loop or a script from one workstation** inside
the allowlist.

**A) 20 requests/second, burst 40** ← *recommended*
   *Why*: comfortably above any human usage of four views, low enough that a runaway loop is capped
   quickly. Each request is a Lambda invocation plus an S3 read, so the throttle is the thing standing
   between a stuck browser tab and a surprising bill.
   *Cost*: a legitimate burst — say a demo where twenty people open the dashboard at once — could clip.
   Twenty concurrent first-loads is ~20 requests, right at the limit, so this is worth a moment's thought
   if a live demo is planned.

**B) 100 requests/second, burst 200** — generous headroom.
   *Cost*: a runaway loop can do real work before being capped.

**C) 5 requests/second, burst 10** — very tight.
   *Cost*: four views loading in parallel plus a refresh could trip it, which would look like the
   dashboard breaking.

X) Other

[Answer]:A

---

### Question 4 — Site cache TTL, and does deploy invalidate CloudFront?

ER-03 fixed `/api/*` as no-cache and the site as cached. The site TTL is unset, and it decides how long a
newly deployed UI takes to appear. **Without invalidation, a cached `index.html` means a deploy is
invisible until the TTL expires.**

**A) Long TTL on hashed assets, short TTL on `index.html`, no invalidation** ← *recommended*
   Vite emits content-hashed filenames (`index-a1b2c3.js`), so those are immutable and safe to cache for
   a year. `index.html` — which references them — gets a short TTL, e.g. 60 s.
   *Why*: this is the standard SPA pattern and it is self-correcting: a new deploy changes `index.html`,
   which is re-fetched within a minute and points at new hashed assets. **No invalidation step to
   forget**, and no per-invalidation charge.
   *Cost*: up to a minute between deploy and visibility. For this audience, irrelevant.

**B) Invalidate `/*` on every deploy** — immediate visibility.
   *Cost*: an extra pipeline step that can fail independently, invalidation charges beyond the free tier,
   and — worse — if anyone forgets to add it for a future asset path, the failure is a *stale UI*, which
   is confusing rather than loud.

**C) No caching on the site at all** — always fresh.
   *Cost*: throws away CloudFront's main benefit and puts every asset request on the origin.

X) Other

[Answer]:A

---

### Question 5 — Log retention

SECURITY-04 and US-12 require retention to be set explicitly. Three log groups: collector, API, and the
edge's access/WAF logs.

**A) 30 days for Lambda logs; 30 days for access and WAF logs** ← *recommended*
   *Why*: long enough to investigate anything a workshop surfaces, short enough that cost stays trivial
   and no personal data lingers. Access logs contain **source IPs**, which are personal data under most
   readings, so a shorter retention is a feature rather than a saving.
   *Cost*: an incident discovered five weeks later has no logs.

**B) 90 days** — more forensic room.
   *Cost*: three times the IP retention for a two-day workshop's teaching infrastructure.

**C) 7 days for Lambda, 30 for access logs** — cheapest.
   *Cost*: a Friday failure noticed the following week is already gone.

X) Other

[Answer]:A

---

### Question 6 — Do old snapshot versions expire?

SR-01 turns on bucket versioning (RESILIENCY-12), so every collection writes a new version of the same
key. At one write per hour that is ~8,760 versions a year, growing without bound.

**A) Expire non-current versions after 30 days** ← *notably, this needs a real decision*
   *Why*: version history exists so a bad snapshot can be inspected or rolled back, and that need is
   measured in hours, not months. 30 days is generous for it while bounding growth.
   *Cost*: no snapshot archaeology beyond 30 days. Given the snapshot is `state: derived` and fully
   rebuildable by re-running the collector, there is little to archive.

**B) Expire after 7 days** — tighter, still covers any realistic rollback.

**C) Keep everything** — no lifecycle rule.
   *Cost*: unbounded object count in a bucket nobody is watching. The snapshots are small, so the *cost*
   stays low for a long time, but "unbounded by design" is the kind of thing that is embarrassing to
   explain later on a dashboard whose purpose is cost visibility.

X) Other

[Answer]:A

---

### Question 7 — Adopt `tiny-chatbot`'s `Condition: HasImage` pattern?

`tiny-chatbot` declares its Lambda with `Condition: HasImage`, so **the stack deploys successfully before
any image exists** — the function is simply absent until an `ImageUri` is supplied.

That is a direct answer to a first-deployment ordering problem, and this blueprint has a related one open
(§6.4: the Build stage runs before the site bucket exists).

**A) Adopt it for both Lambdas** ← *recommended*
   *Why*: the first deployment of this blueprint necessarily happens before its images have ever been
   built, and without the condition that deploy fails on an unresolvable `ImageUri`. It also makes the
   stack independently deployable for template debugging, which `CLAUDE.md` explicitly wants ("a
   blueprint should deploy identically by hand and by pipeline"). It follows a pattern already in the
   repo rather than inventing one.
   *Cost*: a stack can be in a state where the dashboard is deployed but has **no compute** — no
   collector, no API — and the CloudFront origin for `/api/*` would then point at an API Gateway with no
   integration. That partial state must be visibly distinguishable from a broken one, or it becomes a
   confusing outage. It also means "the stack deployed" stops implying "the dashboard works".

**B) Require images first; no condition.**
   *Why*: no partial state; if the stack is up, the dashboard exists.
   *Cost*: the first deploy is a chicken-and-egg — the Build stage must have produced images before
   BlueprintDeploy ever runs, which is true in steady state but awkward on day one and for anyone
   deploying by hand.

X) Other

[Answer]:A

---

### Question 8 — Availability target

RESILIENCY-02 already records **RTO/RPO as N/A** and availability as "best-effort in-region, not
SLA-bound", on the basis that the snapshot is fully rebuildable. This confirms it for the deployed unit
rather than assuming the earlier answer covers it.

**A) Confirm: best-effort, single region, no SLA, no multi-AZ work** ← *recommended*
   *Why*: every component chosen is already regionally redundant by default — S3, CloudFront, Lambda and
   API Gateway are multi-AZ without configuration — so there is nothing to build. The honest statement is
   that availability is whatever those services provide, and that a total loss costs organizers a view
   they can also get from the console.
   *Cost*: none identified. Recording it prevents a later reader assuming an SLA exists.

**B) Add a documented availability objective** (e.g. 99% during workshop hours) with monitoring against
   it.
   *Cost*: an objective nobody measures is worse than none. Measuring it means a synthetic canary, which
   RESILIENCY-06 already recorded as **not applicable** because the endpoint is WAF-restricted and not
   publicly reachable.

X) Other

[Answer]:A

---

## Part A1 — Categories evaluated and NOT asked about

| Category | Why not |
|---|---|
| Scaling triggers, autoscaling | Nothing to configure. Lambda scales per invocation; CloudFront and S3 scale without input. The only bound worth setting is *downward* — reserved concurrency (RESILIENCY-09), which limits blast radius and cost, and is Infrastructure Design's number. |
| Multi-region, failover, DR | RESILIENCY-02 recorded RTO/RPO N/A because the snapshot is rebuildable. Q8 confirms rather than reopens. |
| Authentication, authorization, session, token | No identity system anywhere (FR-5.5). The only control is the WAF allowlist. |
| Encryption algorithm choice | SECURITY-01/-02 already require encryption at rest and TLS 1.2+. S3 SSE and CloudFront TLS policy are Infrastructure Design settings, not open requirements. |
| Database selection, schema, migrations | No database. One S3 object (Application Design Q1). |
| Messaging, queues, async | No queue anywhere. The collector is scheduled; the API is synchronous. |
| Cost budget | Estimated at Units Generation (~$10–15/mo, WAF-dominated). Q1–Q6 here move it by cents, except Q2's option B which would roughly double it — stated in that question. |
| Accessibility targets | Fixed and **non-waivable** by `contracts/ui-design-language.md` §2 (WCAG 2.2 AA). Not a requirement to set; already set, by someone else, with no exemption path. |
| PBT properties | U-02 is mostly I/O. Functional Design recorded honestly that property tests over mocks test the mocks, and named the table-driven six-state mapping plus two template assertions as the high-value tests instead. |

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] All eight `[Answer]:` tags filled
- [x] Mandatory analysis for vagueness, contradiction, option-merging, and this stage's watch-list
      ("standard", "typical")
- [x] Record resolved decisions and interactions in a `Part A2`
- [x] Re-check that no answer contradicts an approved decision or a §4.1/§4.3 rule

### B2. `nfr-requirements.md`
- [x] Requirements with IDs, each traced to a source, and each marked **automated / review-only** — the
      same discipline as U-01, because an NFR nothing checks is an aspiration
- [x] Per-component sizing, limits, retention and TTLs from Q1–Q6
- [x] Security requirements mapped from §4.1 to the specific component that satisfies each
- [x] Resiliency requirements mapped from §4.3, with RESILIENCY-04/-14/-15 shown as **discharged at
      Functional Design** (DR-03, DR-04) rather than open
- [x] Explicitly mark each Part A1 category N/A with its reason
- [x] State which requirements can only be verified **after deployment**, since unlike U-01 many can

### B3. `tech-stack-decisions.md`
- [x] The seven precedent-established choices, cited not re-argued
- [x] Decisions from Q1–Q8 with rationale and rejected alternatives
- [x] Full dependency inventory: `boto3` for both Lambdas; React + Vite for the UI; **U-01 as an
      in-process import with no runtime dependencies of its own**
- [x] Supply-chain position per US-09 and Q11 = B — Python and images pinned, scanned, SBOM'd; npm pinned
      only. Note the **51 Dependabot findings** already on the default branch as live context
- [x] The `Condition: HasImage` decision and its partial-state consequence

### B4. Validation and honest reporting
- [x] Every requirement traceable; none without a source
- [x] Confirm nothing requires a VPC, subnet, VPN, Direct Connect, Transit Gateway, or identity system
- [x] Confirm the four inherited obligations remain discharged and are not weakened by any NFR here
- [x] Report what cannot be settled, naming the stage that carries it — expected: §6.4, WAF IPv6, the
      notify-topic ARN mechanism, and reserved-concurrency numbers

### B5. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 📊 NFR Requirements Complete - U-02 Dashboard Platform` and wait for approval

---

## Part A2 — Resolved decisions (Q1–Q8)

All eight clean single selections, all **A**. Watch-list terms ("standard", "typical", "depends") absent.
No blocking follow-up. Six interactions, **two of which are gaps in my own questions** and one of which
quietly unblocks something Code Generation had recorded as stuck.

| # | Decision | Answer |
|---|---|---|
| Q1 | Sizing | Collector 512 MB / 120 s · API 512 MB / 10 s |
| Q2 | Cold start | Accepted; no provisioned concurrency |
| Q3 | Throttle | 20 rps, burst 40 |
| Q4 | Site cache | Long TTL on hashed assets, 60 s on `index.html`, no invalidation |
| Q5 | Retention | 30 days, Lambda and edge logs alike |
| Q6 | Snapshot versions | Non-current expire after 30 days |
| Q7 | `Condition: HasImage` | Adopted for both Lambdas |
| Q8 | Availability | Best-effort, single region, no SLA |

### Interaction 1 — Q1 = A and the page limit can fire in the wrong order

Two independent bounds now guard the collector: **50 pages** (Functional Design Q1) and a **120 s Lambda
timeout** (Q1 = A here). Whichever is reached first decides what the failure *looks like*, and only one of
them is diagnosable.

At ~1 s per page, 50 pages costs ~50 s and the page limit fires first — the intended behaviour, producing
`PAGE_LIMIT_EXCEEDED` in the log so the runbook's first question has an answer. But **if the upstream
slows to beyond ~2.4 s per page, the 120 s timeout arrives before page 50**, and the failure becomes a
bare Lambda timeout: no reason code, nothing for CR-04 to log, and the runbook's "was the page limit hit?"
step has nothing to check. The precise outcome Functional Design Q1 chose option A to avoid, reintroduced
by a number chosen in a different stage.

> **New requirement**: the collector tracks elapsed time and raises a distinguishable
> `UPSTREAM_TOO_SLOW` when it approaches a **deadline set below the Lambda timeout** (e.g. 100 s of a
> 120 s limit). **No collector failure should ever surface as a bare platform timeout.**

Neither answer implies this alone. It comes from asking which of two bounds wins.

### Interaction 2 — GAP IN MY Q6: the site bucket accumulates too

Q6 asked about **snapshot** versions and stopped there. But Q4 = A relies on **content-hashed asset
filenames**, and `aws s3 sync` does not delete by default — so every deploy adds a new set of hashed
assets and **leaves the previous ones in the bucket forever**.

That retention is briefly *useful*: a browser holding a cached `index.html` for up to 60 s still resolves
its old asset URLs, which is exactly why option A is self-correcting rather than a hard cutover. But
useful for 60 seconds is not a reason to keep them for years.

> **New requirement**: the site bucket gets its own lifecycle rule expiring objects not modified for
> **30 days**, matching Q6's window. **`--delete` is deliberately *not* used on the sync**, because
> deleting old assets immediately would break any browser mid-rollout holding a cached `index.html` —
> the failure Q4 = A's whole design avoids.

My question covered one of two accumulating buckets. Recorded rather than quietly fixed.

### Interaction 3 — Q7 = A unblocks `blueprint.yaml`, which Code Generation recorded as stuck

At Code Generation I recorded that `blueprint.yaml` could not be created, because `CLAUDE.md` and
`check_blueprint_manifests` require a manifest to name a **registered** template, `validate_stacks.py`
requires a `deployed_by: pipeline` entry to have a matching action, and the marker was therefore
registered `manual`.

**Q7 = A dissolves that.** With `Condition: HasImage`, the application stack deploys successfully before
any image exists — so it can be registered `deployed_by: pipeline` with a real BlueprintDeploy action from
the first PR, which makes it a legal manifest target. The chain was: no images → no working deploy → no
pipeline registration → no manifest. `HasImage` breaks the first link.

Consequence recorded for Infrastructure Design: `blueprint.yaml` names `dashboard.yml`, and DR-02's flip
of `dashboard-marker` from `manual` to `pipeline` happens in the same change as its action.

### Interaction 4 — Q7 = A's partial state already has a home in the UI, and needs one in the runbook

With `HasImage` false, there is no API Lambda, so `/api/*` returns an API Gateway error rather than the
response envelope AR-03 defines. The UI is already covered: `frontend-components.md`'s **row 6**
("network failure / non-JSON → generic error, plus that the request itself failed") catches exactly this.
Nothing to change.

What is missing is the operator's side. A freshly deployed stack with no images shows a generic error on
every view, which is **indistinguishable from a real outage** unless someone knows to expect it.

> **Runbook entry (DR-04)**: "Every view shows a generic error immediately after a first deployment →
> check whether the container images have been built and their digests passed. With `HasImage`, the stack
> deploys before the images exist."

### Interaction 5 — Q2 = A and Q3 = A intersect on demo day

Cold starts are accepted (1–3 s) and the throttle is 20 rps / burst 40. Twenty people opening the
dashboard simultaneously produces ~20 concurrent cold starts — fine for Lambda — but if they then click
between all four views, that is up to 80 requests in a short window, which will clip the burst.

Not a design defect: human clicking spreads over seconds, and a clipped request retries. Recorded because
"the dashboard broke during the demo" is expensive, and the mitigation is trivial and worth writing down:
**open the dashboard once before a demo to warm it**, and raise the throttle parameter temporarily if a
large simultaneous audience is expected. Both are possible only because the throttle is a parameter.

### Interaction 6 — Q5 = A's retention is a privacy decision, and applies unevenly

30 days for Lambda logs is a cost-and-forensics trade. 30 days for **CloudFront and WAF access logs is a
personal-data decision** — those contain source IPs.

Worth stating the asymmetry: the Lambda logs contain resource ARNs and reason codes (CR-04 deliberately
excludes tag values, so **no NetIDs**), while the access logs contain IPs that identify people. If either
retention were ever extended, the access logs are the one that needs a reason beyond convenience.

**Nothing in U-01 is reopened.** BR-01..BR-08, the ten properties, and the `__all__` contract stand.
