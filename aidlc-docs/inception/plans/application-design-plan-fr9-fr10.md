# Application Design Plan — FR-9 (usage telemetry) + FR-10 (cost)

**Stage**: INCEPTION → Application Design, **second pass** (FR-9/FR-10 only)
**Date**: 2026-08-07
**Inputs**: `amendments/telemetry-fr9-2026-08-07.md` (A2, approved) as corrected by
`amendments/telemetry-a3-measured-2026-08-07.md` (A3, measured), stories US-16…US-25.
**Scope**: extends the approved v1 design (C-01…C-09). Does **not** revisit it.

This plan is Part 1. Part 2 generates the artifacts and executes nothing else.

---

## Part A1 — What the requirements add, before any decision

New capability, mapped to the existing component model:

| Need | Existing home? |
|---|---|
| Read Cost Explorer daily (FR-10.1, 10.4) | **none** — new |
| Read CloudWatch metrics: `AWS/Bedrock`, `AWS/Bedrock-AgentCore`, `Cornell/Blueprints/*` (A3.1, A3.2, FR-9.5) | **none** — new |
| Estimate model cost = tokens × rates (FR-10.6) | **none** — new, and must be pure |
| Know what counters a blueprint declares (FR-9.4) | **none** — new, and see Q2 |
| Hold cost + telemetry sections durably (FR-9.5.3) | C-02, but see Q1 |
| Serve new views (US-16…US-23) | C-03 extends |
| Render two dashboards | C-06 extends |
| Alarms/metrics for the new collectors | C-09 extends |

So: **four genuinely new components**, two extended, one under question.

---

## Part A2 — Questions

### Q1 — Snapshot layout, and the read-modify-write problem it creates

**This is the most consequential question here, and A2 wrote a requirement that cannot be built as
literally stated.**

FR-9.5.3 says telemetry MUST land as an *"additive sibling section"* in the existing snapshot, under
the existing `schema_version` — which is what C-02's headroom was reserved for. But FR-10.4 puts cost
on a **daily** schedule while inventory (and telemetry) stay **hourly**. That means two writers on
different cadences.

If all three sections live in **one S3 object**, the daily cost writer must read the current object,
splice its section in, and write the whole thing back — a **read-modify-write**. C-01's design forbids
exactly that: components.md C-01 says *"Write the snapshot to C-02 as one object"* and the code
comment records *"single `put_object` (complete-or-fail, CR-05, **no read-modify-write**)"*. RMW also
introduces a lost-update race the moment two writers overlap, and S3 has no compare-and-swap here.

A) **One object per section** — `inventory/current.json`, `telemetry/current.json`,
   `cost/current.json`. Each writer owns its own key and still does a single complete-or-fail
   `PutObject`; no writer ever reads another's data. The API reads 1–3 objects and composes the
   response. *Cost*: three `GetObject` calls per request instead of one, and "the snapshot" becomes a
   set rather than a thing — `collected_at` is now per-section, which the UI must show honestly
   (arguably an improvement, since cost really is a day stale while inventory is an hour stale).
   **Requires amending FR-9.5.3's "sibling section in the snapshot" wording.**

B) **One object, one writer** — collapse cost collection into the existing hourly collector so there
   is a single writer and no RMW. *Cost*: violates FR-10.4 — the collector would call Cost Explorer
   hourly at $0.01/request (~$7.20/month against a **$9.02/month account**, per A3.6). Could be
   mitigated by calling CE only on the first run of each day, but then the collector carries
   scheduling logic and a partial failure in the CE call taints the inventory snapshot too.

C) **One object, RMW with versioning** — keep the single object, accept read-modify-write, rely on S3
   versioning to recover. *Cost*: contradicts CR-05 explicitly, and "recover from versions" is a
   manual runbook step, not a design.

[Answer]: **A** — one object per section (`inventory/current.json`, `telemetry/current.json`, `cost/current.json`). Each writer keeps a single complete-or-fail `PutObject`; no RMW, no lost-update race. `collected_at` becomes per-section, which is more honest than one timestamp over data of three different ages. **FR-9.5.3's "sibling section" wording must be amended** (step B6).

### Q2 — How does the dashboard learn what a blueprint declares? (FR-9.4 has no runtime path)

FR-9.4 says a blueprint declares its counters in **`blueprint.yaml`**, and FR-9.5.2 says the reader
MUST read *only* declared counters — a closed allowlist (NFR-T5).

**`blueprint.yaml` lives in git. The dashboard runs in Lambda and cannot read the repo.** A2 specified
the declaration and the allowlist without specifying how the declaration reaches the reader, and there
is no existing mechanism: this repo has no runtime config distribution, and `validate_stacks.py` is a
PR-time check, not a deploy-time publisher.

A) **Bake at build time** — the pipeline's site/image build collects every
   `blueprints/*/blueprint.yaml` `telemetry:` block into one catalog file baked into the API image (or
   uploaded beside the site). *Pro*: no new runtime dependency, no IAM, and the catalog is versioned
   with the deploy that produced it. *Con*: a blueprint that starts emitting is invisible until the
   dashboard is redeployed — though a merge to `main` redeploys everything anyway, so the lag is one
   pipeline run.

B) **Publish to SSM at deploy time** — each blueprint's own stack writes its telemetry declaration to
   a `/<app>/<env>/telemetry/<blueprint>` SSM parameter; the dashboard reads the path prefix at
   runtime. *Pro*: each blueprint owns its own declaration at deploy time, and the dashboard picks up a
   new emitter with no dashboard deploy. Precedent exists — `knowledgebase` already mirrors its data
   source id into SSM. *Con*: requires **every other blueprint's template** to add a resource, i.e.
   cross-track changes T6 explicitly declined to make; the dashboard would ship reading an empty prefix.

C) **Skip declarations; discover from CloudWatch** — `list-metrics` on `Cornell/Blueprints/*` and
   `AWS/Bedrock*` and render whatever is found. *Pro*: zero coordination, and it is how the **pull**
   path (A3.1) must work anyway, since AWS's own metrics are not declared anywhere. *Con*: directly
   contradicts FR-9.5.2/NFR-T5's closed allowlist, and loses the units and human-readable descriptions
   that FR-9.4.3 requires for generic rendering.

D) **A + C, split by source** — bake the declared-counter catalog for `Cornell/Blueprints/*` (closed
   allowlist preserved), and use a **fixed, code-level** allowlist of AWS namespaces/metrics for the
   pull path (`AWS/Bedrock`, `AWS/Bedrock-AgentCore`), discovering only *dimension values* (which
   models exist) rather than which metrics to read. *Pro*: honours NFR-T5 for both sources — the metric
   set is closed in both cases, only the model list is dynamic. *Con*: two mechanisms to understand.

[Answer]: **A** — bake the declared-counter catalog at build time for `Cornell/Blueprints/*`, **plus** a fixed code-level allowlist of AWS namespaces (`AWS/Bedrock`, `AWS/Bedrock-AgentCore`) whose *metric set* is closed and whose only dynamic part is which `ModelId` dimension values exist. NFR-T5's closed allowlist holds for both sources; only the model list is discovered.

### Q3 — Cost collection: new Lambda or a second event on the existing collector?

FR-10.4.4 explicitly deferred this here.

A) **A new Lambda (C-10)**, its own schedule, its own role with `ce:GetCostAndUsage` only. Cleanest
   least-privilege story (NFR-T6) and an independent failure domain — a CE outage cannot affect
   inventory. *Cost*: a third image target, a third log group, a third alarm set.

B) **Reuse the collector image with a different `CMD`/handler** — one Dockerfile target, two Lambda
   resources from the same image, separate roles and schedules. Precedent: the existing Dockerfile
   already has two targets (`collector`, `api`) from one base. *Cost*: slightly more template.

C) **One Lambda, event-type dispatch** — the existing collector branches on the EventBridge event.
   *Cost*: one role needs both `tag:GetResources` **and** `ce:GetCostAndUsage`, widening the
   least-privilege surface; and it recreates Q1(B)'s failure coupling.

[Answer]: **B** — reuse the collector image: a new Dockerfile target plus handler, its own Lambda resource, its own role scoped to `ce:GetCostAndUsage`, its own daily schedule. Follows the existing `collector`/`api` two-target precedent.

### Q4 — Is this a third unit, or an extension of U-01/U-02?

The two existing units are U-01 Domain Core (pure, stdlib-only, 60 tests, 9/9 mutation) and U-02
Dashboard Platform (everything AWS-facing).

A) **Extend both** — pure additions (cost estimation, telemetry/cost models) go into U-01's
   `dashboard.core`; the new collectors and routes go into U-02. *Pro*: matches the existing purity
   boundary, which `tools/check` enforces mechanically. *Con*: reopens two "complete" units.

B) **A new unit U-03** — all FR-9/FR-10 code in its own package. *Pro*: U-01/U-02 stay closed. *Con*:
   either duplicates the model types or imports U-01 anyway, and the pure/impure split would then run
   *inside* U-03, which is the thing the U-01/U-02 boundary exists to prevent.

C) **Extend U-02 only; no new pure code in U-01** — put cost estimation in U-02 with the AWS code.
   *Pro*: U-01 stays untouched and its mutation score stays meaningful. *Con*: the rate-table
   arithmetic becomes untestable without AWS mocks, and it is the one piece of new logic most worth
   property-testing (money arithmetic).

[Answer]: **A** — extend both units on the existing purity line: pure additions into U-01 `dashboard.core`, AWS-facing code into U-02. Money arithmetic is the most valuable new thing to property-test, so it must be pure.

---

## Part A3 — Questions I am resolving with defaults unless you say otherwise

Recorded so the decisions are visible rather than silent. Each follows existing precedent.

- **Q5 rate table location** → **SSM Parameter** (`/<app>/<env>/dashboard/model-rates`), JSON, read at
  runtime and cached per invocation. Satisfies NFR-T2 (configuration, no code change), matches the
  repo's existing SSM use (`MODEL_ID_PARAM` in teams-bot, `knowledgebase`'s id mirroring), and needs
  no new resource type. A missing or malformed table surfaces FR-10.6.6's *not instrumented* state
  rather than pricing at zero.
- **Q6 new API routes** → distinct path per view, matching Q5 = A of the v1 design:
  `/api/cost/summary`, `/api/cost/breakdown`, `/api/usage/models`, `/api/usage/quality`. Keeps
  SECURITY-05 structural.
- **Q7 UI shape** → two new tabs alongside the existing four, reusing `StateBoundary` unchanged so
  NFR-T7's three states are rendered by the component already tested for six states.
- **Q8 self-cost** → the dashboard **does** show its own cost line, because A3.6 makes it material
  (~3–33% of a $9/month account) and hiding it would be the same dishonesty NFR-T1 forbids elsewhere.

[Any objection — otherwise these stand]: none raised — Q5–Q8 stand as written.

---

## Part B — Steps (execute in Part 2, after Q1–Q4 are answered)

- [x] B1 — Extend `components.md`: C-10…C-13 per Q1/Q3/Q4, and the extensions to C-02, C-03, C-06, C-09
- [x] B2 — Extend `component-methods.md`: signatures for the new components, input/output types only
- [x] B3 — Extend `services.md`: the two new collection flows and the read-time composition
- [x] B4 — Extend `component-dependency.md`: dependency matrix + data flow for both new paths
- [x] B5 — Update the consolidated `application-design.md`
- [x] B6 — Amend FR-9.5.3 if Q1 = A (the "sibling section" wording), and FR-9.4/9.5.2 per Q2
- [x] B7 — Validate: every FR-9/FR-10 clause and every US-16…US-25 criterion has a component home
- [x] B8 — Update `aidlc-state.md` + `audit.md`; present at the approval gate
