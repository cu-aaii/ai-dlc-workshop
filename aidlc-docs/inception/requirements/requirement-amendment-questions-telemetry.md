# Requirements Amendment — Custom Telemetry

**Request**: "I want to add some custom telemtry to the dashboard"
**Received**: 2026-08-03, at the User Stories approval gate
**Status**: new functional requirement, not yet in the approved `requirements.md`

---

## Two things to know before answering

### 1. Part of this may already be specified
"Custom telemetry" could mean something already covered, in which case you don't need a new
requirement — you need to know it's there:

- **US-14 [Enabler]** already requires metrics for latency, error rate, throughput, and invocation
  counts on both the dashboard's Lambdas, plus a health dashboard definition (RESILIENCY-05, -06, -09)
- **US-12 [Enabler]** already requires structured JSON application logging from both functions
  (SECURITY-04)
- **US-13 [Enabler]** already requires alarms for collector failure, snapshot staleness, Lambda
  errors/throttles, and quota utilization (RESILIENCY-07)
- **US-11 [Enabler]** already requires CloudFront, S3 and WAF access logging (SECURITY-03)

So *operational* telemetry about the dashboard's own health is specified. What isn't specified is
anything **custom** — metrics you define, rather than metrics AWS emits by default.

### 2. There's an existing hook for this, and a boundary question
Your very first answer in this workflow (R1-Q1) was **"C, plus other metrics to be defined later"** —
so `requirements.md` already requires the snapshot store to be extensible to further metrics
(FR-2.4). This request may be you defining those. If so, it's a natural extension rather than a
change of direction.

The boundary question is separate: `CLAUDE.md` lists **`observability/`** under "Deliberately not
built — don't pre-build them without being asked." Custom telemetry is arguably that directory's
job rather than this blueprint's. You're asking now, so the "don't pre-build" bar is cleared — but
whether the work lands *inside* `blueprints/dashboard/` or in a separate `observability/` component
is a real decision with consequences for both, and it isn't mine to make.

---

## Question 1 — What does "custom telemetry" mean here?

A) **Custom metrics from deployed blueprints, surfaced on the dashboard** — blueprints emit their
   own metrics (e.g. a chatbot's query count, a Lambda's business-level counters), and the dashboard
   displays them alongside inventory, joined on `cornell:deployment-id`. This is the direct reading
   of R1-Q1's "other metrics to be defined later".

B) **Usage telemetry about the dashboard itself** — how often it's viewed, which views are used,
   which queries are run. Note the constraint: v1 has **no identity** (single persona, WAF IP
   allowlist), so this can only ever be aggregate counts. It cannot answer "who looked at this",
   and building it toward that would need the identity work that was deliberately deferred.

C) **Custom operational metrics for the dashboard's own components** — beyond the AWS defaults
   already in US-14: e.g. resources-collected count, collection duration, tag-gap count over time,
   pages fetched from the Tagging API. Emitted as custom CloudWatch metrics.

D) **A generic telemetry ingestion path** — the dashboard (or a sibling component) accepts arbitrary
   metrics that any blueprint can push, and renders whatever arrives. Broadest scope by a wide
   margin; effectively a small platform capability rather than a dashboard feature.

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 2 — Where should it live?

A) **Inside `blueprints/dashboard/`** — the dashboard collects and displays it, self-contained like
   the rest of the blueprint. Simplest, keeps one deployable unit. *Cost*: pushes the blueprint
   toward being the platform's telemetry component by accretion rather than by design.

B) **A new `observability/` component**, with the dashboard reading from it — matches the structure
   `CLAUDE.md` anticipates, and keeps the dashboard a *view* rather than a *collector* of telemetry.
   *Cost*: a second component to design, register, and wire, and it's explicitly listed as not-yet-built,
   so it's greenfield work rather than an extension.

C) **Inside the dashboard for now, with `observability/` explicitly noted as the eventual home** —
   ship it where it's cheap, record the intended move. *Cost*: the move later is real work, and
   "eventual" has a way of not arriving.

X) Other (describe after [Answer]: tag below)

[Answer]:

## Question 3 — When?

A) **Amend requirements now** — add this as FR-9 to `requirements.md`, re-approve it, extend
   `stories.md` with the new stories, then approve stories once. Nothing gets approved stale, at the
   cost of returning to a stage that was closed.

B) **Approve the current v1 stories first, then amend** — bank the inventory work as approved, treat
   telemetry as a second pass through Requirements → Stories. Keeps v1 clean and shippable; means
   two approval cycles.

C) **Add it as a deferred/stretch item only** — record it next to the cost stretch goal (US-D1/US-D2)
   with criteria TBD, and don't specify it further until v1 inventory is actually deployed and
   working.

X) Other (describe after [Answer]: tag below)

[Answer]:

## Question 4 — What decision does the telemetry need to support?

This one is free-text and it's the most useful of the four. Knowing what you'd *do* with the numbers
determines what's worth collecting far better than a list of candidate metrics does — and it's the
difference between a requirement I can write acceptance criteria for and one I can only guess at.

For example: "tell me if a builder's blueprint is broken without them reporting it", "show me which
blueprints people actually deploy so we know what to invest in", "prove the workshop stayed inside
its budget", "spot a runaway Lambda before the bill does".

[Answer]:

---

## What I'm not doing yet

Nothing is being written to `requirements.md` or `stories.md` until these are answered. The
User Stories approval gate stays open — I'd rather not have you approve a story set that a new
requirement is about to invalidate, and Question 3 is where you decide whether that's actually a
concern or whether v1 should be banked as-is.
