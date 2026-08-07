# Design — Dashboard Source Catalog (composing a dashboard from several sources)

**Status**: Draft for review. No code implied; a reviewable model to agree before any blueprint
skill or manifest work.
**Date**: 2026-08-04
**Companions**: `composable-dashboards.md` (two dashboards, one observability contract) and
`observability-contract.md` (the emit/consume contract). This doc is the *other direction*: how a
dashboard **pulls from** several sources, and how the blueprint **teaches a design agent** to wire
each one.

---

## 1. The goal, restated

Any dashboard should be **composable from several sources, chosen by the builder's query**. A
builder describes what they want in plain English; a **design agent** composes a dashboard by
selecting the relevant sources and wiring each one. **The blueprint's job is to inform the design
agent how to connect to each source type** — it carries the agent-facing knowledge, so the agent
does not invent connection code per request.

This is not "add three data sources to the tag-inventory dashboard." The tag-inventory dashboard
(in `aidlc-docs/inception/`) is *one composition* — a dashboard whose single source is the Resource
Groups Tagging API. This doc generalizes: **a source catalog** the agent selects from, of which
tags is simply the first entry.

---

## 2. What the blueprint carries (agent-facing knowledge)

Two artifacts, matching patterns already in the repo:

1. **`blueprints/dashboard/skills/dashboard/SKILL.md`** — prose *recipes*: for each source type, how
   to wire it (IAM, egress, client, response shape, failure handling). This is the same
   blueprint-carries-a-skill pattern the `knowledgebase` blueprint uses.
2. **`blueprints/dashboard/blueprint.yaml`** — the manifest the Cornell Builder MCP already parses
   (`packages/builder-mcp/src/builder_mcp/catalog.py`). It gains a machine-readable **`sources:`**
   catalog: each source's id, what it returns, its connection rule, and its `matches` phrases so the
   agent can select by query.

The division mirrors the observability contract's declarative/runtime split: `blueprint.yaml`
declares *what sources exist and how they connect* (structured, checkable); `SKILL.md` narrates
*how to actually wire one* (prose, for the agent). The agent reads both when composing.

---

## 3. The source-catalog model

A **source** is described to the agent by a small, uniform record — one connection rule per source
type, chosen on its own merits (not one rule for all). Proposed manifest shape, extending the
existing `blueprint.yaml`:

```yaml
# blueprints/dashboard/blueprint.yaml  (additions, alongside metadata/inputs/template)
sources:
  - id: aws-tags
    summary: cornell:* tagged-resource inventory (the v1 dashboard's source)
    matches: ["what did I deploy", "tag inventory", "untagged resources", "cost attribution"]
    returns: resource records keyed by cornell:deployment-id
    freshness: snapshot            # scheduled collector -> S3, served read-only
    connection:
      kind: aws-api
      auth: iam                    # collector role; no secret
      iam_actions: ["tag:GetResources"]

  - id: cloudwatch
    summary: CloudWatch metrics and alarm states for resources in this account
    matches: ["show metrics", "error rate", "latency", "alarm status", "is it healthy"]
    returns: metric time series and alarm states, by namespace/dimension
    freshness: snapshot            # same collector cadence as tags (see §5)
    connection:
      kind: aws-api
      auth: iam                    # no secret
      iam_actions: ["cloudwatch:GetMetricData", "cloudwatch:DescribeAlarms"]

  - id: http-health
    summary: liveness of a deployment's own HTTP endpoint (e.g. .../health)
    matches: ["is my service up", "health check", "deployment status", "uptime"]
    returns: {status, latency_ms, checked_at} per probed URL
    freshness: probe               # checked at collection time; see §5 on staleness
    connection:
      kind: http-probe
      auth: none                   # unauthenticated liveness endpoint by convention
      urls_from: input             # the builder/agent supplies the URL(s) as a manifest input

# --- deferred, present as a documented placeholder only ---
  - id: litellm
    summary: LLM usage/spend from a live LiteLLM instance
    status: BLOCKED                # see §6 — no secure secret-sharing model yet
    connection:
      kind: http-api
      auth: secret                 # requires an injected credential -> the blocker
```

The uniform fields — `id`, `summary`, `matches`, `returns`, `freshness`, `connection{kind, auth}` —
are what make this a *catalog*: adding a source is adding a record and a recipe, not rewriting the
dashboard. `matches` is what lets the agent pick sources by query, reusing the ranking the MCP
already does over blueprint `matches`.

---

## 4. The two source recipes that are buildable now

Per the connection decision (one rule per source), these two need **no shared secret** and are
unblocked.

### 4.1 CloudWatch — `kind: aws-api`, `auth: iam`
- **Connect**: the collector Lambda's execution role gets `cloudwatch:GetMetricData` and
  `cloudwatch:DescribeAlarms`. No credential, no secret — same in-account IAM model the tag
  collector already uses for `tag:GetResources`.
- **Least privilege**: scope to the metrics/alarms the composed dashboard actually reads; document
  any unavoidable breadth the way `tag:GetResources`'s account-wide scope is documented as an
  accepted exception.
- **Returns**: metric time series + alarm states, joinable to inventory on the resource dimension
  (which ties back to `cornell:deployment-id`).
- **Recipe in SKILL.md**: which API calls, pagination/period handling, timeouts + bounded retries
  (RESILIENCY-10), and how to fold the result into the snapshot section.

### 4.2 Custom `.../health` — `kind: http-probe`, `auth: none`
- **Connect**: a direct HTTPS GET to a URL supplied as a manifest input. `/health` is an existing
  repo convention — `blueprints/aisei-site/app/server/app.ts` serves `GET /health -> {status,
  uptime}`, and the dashboard's own API serves `/api/health`. The probe reads exactly that.
- **No secret**: liveness endpoints are unauthenticated by convention. If a health endpoint ever
  needs auth, it falls into the same blocked bucket as §6.
- **Returns**: `{status, latency_ms, checked_at}` per URL — deliberately minimal.
- **Recipe in SKILL.md**: explicit timeout (a hung probe must not hang the collector), treat
  non-200/timeout as `down` not as an error that fails the snapshot (fail-safe, SECURITY-15), and
  **never follow redirects to arbitrary hosts** (SSRF guard — the probed URL is data, validate it
  against an allowlist/shape).

**Own vs. others' endpoints**: v1 probes endpoints the composition is *given* (its own, or ones the
builder names). Probing *other deployments'* health across the fleet is the central-observability
concern in `composable-dashboards.md` — related, but a different scope; keep this recipe to
supplied URLs.

---

## 5. Freshness — the model split these sources force

The tag dashboard's rule is **serve a stored snapshot, never query live** (FR-2.1). The new sources
have different natural freshness, and this is the one place the catalog touches an approved
requirement:

- **`snapshot` sources (tags, CloudWatch)** fit the existing model cleanly: the scheduled collector
  fans out to each, writes one snapshot with a section per source, and the read API serves it. All
  share one cadence. **No requirements change** — it is the existing model with more collectors.
- **`probe` sources (http-health)** are awkward in a snapshot: a health status captured an hour ago
  is close to useless. Two honest options, to decide at review:
  - **(a) Snapshot-consistent**: probe at collection time, store the result with its `checked_at`,
    and show the age — consistent with FR-2.1 and the staleness-display model, at the cost of
    health being as stale as the cadence.
  - **(b) Live-on-read for probes only**: the read API probes health at request time (short cache),
    while tags/CloudWatch stay snapshotted. This **contradicts FR-2.1** and would need a small
    requirements amendment scoped to probe-type sources.

  Recommendation: **(a) for v1** (no requirements change, honest about age), revisit (b) if live
  health proves necessary. Flagged as open decision #1.

---

## 6. LiteLLM and any external authed source — deferred, and why

**Deferred by decision (2026-08-04).** Not because LiteLLM is hard, but because **there is no
established pattern for how a builder-composed blueprint securely obtains a credential for an
external authed service under this build model.** The blocker generalizes to *any* `auth: secret`
source.

The tension, concretely:
- The repo's secret pattern (updated `CLAUDE.md`) is: a secret's *resource* is declared in
  CloudFormation, its *value* injected once by CLI, never in git (see `AzureCredentialsSecret`).
  That works for a **platform-team, once-per-account** credential.
- A **builder-composed dashboard** is different: the builder has PR-only access, no AWS console, no
  account. How does *their* deployment get a LiteLLM key without the builder handling a secret and
  without per-deployment human console work? **That path is not defined.**

So every `auth: secret` source is blocked on this, and the catalog marks them `status: BLOCKED`
rather than pretending. This is the right next platform decision (open #2) — solving it unblocks
LiteLLM and every future external authed source at once, which is more valuable than a one-off
LiteLLM integration.

---

## 7. How the design agent uses this (composition flow)

1. Builder query → the Cornell Builder / design agent ranks the dashboard blueprint's `sources[]`
   by `matches` (reusing the MCP's existing ranking).
2. Agent selects the source subset the query implies (e.g. "is my service up and what's it costing"
   → `http-health` now; `litellm` flagged blocked).
3. For each selected source, the agent follows the `SKILL.md` recipe to wire it: adds the IAM the
   `connection` declares, the collector fan-out, the manifest inputs (e.g. health URLs), and the UI
   section.
4. Sources with `status: BLOCKED` are surfaced to the builder as "not available yet, because <§6>",
   not silently dropped.
5. The composed dashboard still satisfies the whole repo contract: `cornell:*` tags, stack naming,
   `stacks.yml` + `pipeline.yml` wiring, `tools/check`.

---

## 8. Open decisions (for review)

1. **Probe freshness (§5).** Snapshot-consistent (a, recommended, no req change) vs. live-on-read
   for probes only (b, needs an FR-2.1 amendment).
2. **The secret-sharing model (§6) — the important one.** How does a builder-composed blueprint get
   an external credential safely under PR-only/no-console access? Blocks LiteLLM and all `auth:
   secret` sources. This is a platform decision, not a dashboard one.
3. **SSRF surface for `http-probe` (§4.2).** Confirm the URL-validation rule (allowlist/shape, no
   arbitrary-host redirects) before any probe ships.
4. **CloudWatch least-privilege scope (§4.1).** How narrowly can `GetMetricData` be scoped for a
   composed dashboard, and what breadth is documented as accepted.
5. **Catalog vs. per-instance manifest.** The `sources[]` catalog lives on the dashboard *blueprint*
   (the menu). A *composed instance* records which sources it actually selected — decide whether
   that selection is written back into its own manifest for inventory/observability.
