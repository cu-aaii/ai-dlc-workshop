# Requirements Amendment — Custom Telemetry, Round 2 (the queued second pass)

**Request**: a concrete metric list for two dashboards (Financial, Adoption), plus "explore getting
metrics directly from AgentCore".
**Received**: 2026-08-07, at the start of the second Requirements pass that
`requirement-amendment-questions-telemetry.md` (Q3 = B) queued on 2026-08-03.
**Status**: answered. This file is the decision record; `amendments/telemetry-fr9-2026-08-07.md`
is the requirement text those decisions produce.

Round 1 settled *what* custom telemetry means (Q1 = A, business counters emitted by blueprints),
*where* it lives (Q2 = C, inside `blueprints/dashboard/` with `observability/` as the eventual
home), *when* (Q3 = B, this pass), and *why* (Q4, free text: usage to justify cost, feedback for
business processes, metrics to determine value). This round settles the metric list and the
mechanisms.

---

## 0. The finding that reframed the metric list

Asked before answering, because it changes which metrics are reachable at all. Read from the code,
not assumed:

**`blueprints/teams-bot` — the only real LLM application in this repo — sends all generation
through Cornell's LiteLLM gateway, never Bedrock.** `src/handler.py` constructs
`Anthropic(base_url=self.config.gateway_base_url, ...)` and `src/requirements.txt` says so
explicitly: *"Pointed at Cornell's LiteLLM gateway via base_url, NOT at Bedrock, so the [bedrock]
extra is deliberately absent."* `MODEL_ID` comes from SSM, defaulting to `claude-haiku-4-5`.

Three consequences:

1. **Generation happens off this AWS account.** The `AWS/Bedrock` CloudWatch namespace in this
   account will be **empty** for chat traffic, and Cost Explorer will show **no model spend**. A
   pull-based CloudWatch metrics source — which the fork's captured `telemetry.py` spec
   (`docs/aidlc/dashboard/design/integration-note-fork-telemetry.md`) and `dashboard-sources.md`
   §4.1 both propose — would render **zeros** for exactly the metrics this request cares most about.
2. **But the application holds the numbers.** Every `messages.create()` response carries
   `usage.input_tokens` / `usage.output_tokens`, and the app knows its own `model_id`. So tokens and
   requests-by-model are reachable — **only** by the push path, not the pull path. `handler.py` does
   not read `usage` today; nothing records it.
3. **Some real in-account Bedrock spend does exist, and it is not chat.** `knowledgebase` uses a
   `MANAGED` embedding model (`EmbeddingModelType: 'MANAGED'`) and `teams-bot` calls
   `bedrock-agent-runtime` `Retrieve` against it. That is embedding cost — small, and not what
   "cost by model" means in this request.

**The split this forces, and the single most important thing in this document:** platform
(infrastructure) cost and model (LLM) cost are two different domains with two different sources.
Cost Explorer sees the first and not the second. The Financial Dashboard list mixes them.

`course-chatbot/src/handler.py` *does* call Bedrock directly (`AnthropicBedrock`), so the pull path
is not useless in principle — but that blueprint is a deliberately unbuilt scaffold
(`CLAUDE.md`, "Scaffolded but not built"), so the path has no live traffic today.

---

## Decisions (2026-08-07)

| # | Decision | Answer | Effect |
|---|---|---|---|
| **T1** | Cost data source — un-defer FR-8? | **Yes; Cost Explorer**, on its own slower schedule | `GetCostAndUsage`, not CUR. Self-service from inside this account; CUR needs a payer/organization-level export this account may not control. Cost collection runs on a **separate, daily** schedule — not the hourly inventory tick — because CE charges **$0.01 per paginated request** and its data only advances once a day. |
| **T2** | "Cost by department" | **Punt** | No `cornell:department` tag exists and adding a fifth required tag is a platform-wide change, not a dashboard one. Out of scope for this pass; `cornell:owner` and `cornell:blueprint` remain the attribution axes. |
| **T3** | "Cost by agent" | Collapses to deployment today; **per-agent dimension designed now** (see T8) | The POC target is one blueprint spinning up many agents, but today it is one agent per deployment, so `cornell:deployment-id` already answers it. The contract carries an agent dimension anyway so the multi-agent case needs no migration. |
| **T4** | "Budget remaining" | **Removed from scope** | Dropped at the user's instruction. No AWS Budgets dependency is introduced. |
| **T5** | "Cost by model", given it is off-account | **Both** — estimate now, reconcile later | Estimated as `tokens × a configured per-model rate table`, labelled an estimate. LiteLLM's own usage API is recorded as the authoritative source to swap in when reachable — it is `status: BLOCKED` in `dashboard-sources.md` §6 on the unsolved builder-credential problem. |
| **T6** | Who emits, given every Adoption metric needs app instrumentation | **Reader + spec only; no emitter this pass** | This pass ships the contract, the manifest declaration, the reader, and the UI. **No blueprint is instrumented** — `teams-bot` belongs to Track C and is not edited here. Consequence accepted below. |
| **T7** | Pull metrics from AgentCore directly, or via CloudWatch? | **CloudWatch only** | AgentCore Observability publishes into CloudWatch metrics plus OTel/X-Ray traces; its console view reads the same data, so there is no separate metrics backend to integrate. One read path (`cloudwatch:GetMetricData`) covers AgentCore-hosted agents, direct-Bedrock callers, and Lambda alike. *Caveat recorded honestly: this session had no web access to re-verify current AgentCore API surface — treat exact namespace/metric names as verify-before-build.* |
| **T8** | `cornell:deployment-id` under composition | **Design the per-agent dimension now** | Rather than flat-id-plus-later-migration. See §2 for the shape. |

---

## 1. What T6 means, stated plainly before it is discovered later

**With no emitter, the entire Adoption Dashboard renders an empty state.** So do "cost by model"
and "cost per completed task", because both are derived from counters an emitter would have to send.

What this pass therefore actually delivers:

| Panel | Real data on day one? |
|---|---|
| Platform cost — today / this month / YTD | **Yes** — Cost Explorer, once tag activation lands (§3) |
| Platform cost — by application, by deployment | **Yes** — same, subject to §3 |
| Cost by model (estimated) | **No** — needs token counters; estimator built and unit-tested against fixtures |
| Cost per completed task | **No** — needs a completed-task counter |
| Requests by model, token usage, error rate, timeout rate | **No** — all push-only |
| Human approval rate, prompt success rate | **No** — purely application-semantic, push-only |

This is not a defect in the decision; it is the honest consequence of building the reading side
before any blueprint implements the convention — which is exactly what Round 1 predicted: *"the
honest v2 deliverable is the contract plus a reader proven against a deliberately trivial emitter —
not a populated usage dashboard."* T6 goes one step further than Round 1 anticipated by declining
even the trivial emitter, so the empty states are the deliverable's visible surface and must be
built to be *informative* — naming the blueprint that has not been instrumented rather than showing
a blank panel (this becomes an acceptance criterion, not a nicety).

**The first real emitter is a Track C decision.** Instrumenting `teams-bot` is ~10 lines against a
`usage` object it already receives, and this pass produces the spec they would implement.

---

## 2. The per-agent dimension (T8)

The problem T8 avoids: if a deployment runs several agents and telemetry carries only
`cornell:deployment-id`, all of their usage collapses into one bucket, unrecoverably.

**Shape decided**: the emission contract carries **both** identifiers, and the agent one
**defaults to the deployment id**:

| Dimension | Required | Meaning |
|---|---|---|
| `deployment_id` | yes | the existing flat join key — `cornell:deployment-id`, unchanged |
| `agent_id` | yes, but **defaults to `deployment_id`** | which agent within the deployment produced this |

A single-agent deployment (every deployment today) sets `agent_id == deployment_id` and needs no
extra thought; a multi-agent deployment sets distinct values and attributes correctly. Because the
dimension exists from the first emission, the multi-agent case is a **change of values, not a schema
migration** — which is what C-02's `schema_version` headroom was reserved for and now does not have
to spend.

This does **not** pre-empt Track D. `origin/team-d` is still at Reverse Engineering with no
composition-id decision recorded (checked: latest commit `e7edca0`, reverse-engineering artifacts
only), so there was no joint decision available to wait for. If Track D later defines parent/sub-id
semantics, `agent_id` is the natural place for a sub-id to land, and the contract states that
`agent_id`'s *format* is not fixed by this pass.

**Cost by agent is asymmetric, and the UI must not imply otherwise:** model cost (estimated from
counters) splits by `agent_id`; infrastructure cost from Cost Explorer **cannot** — several agents
share one Lambda or AgentCore runtime, and AWS bills the resource, not the agent.

---

## 3. Cost Explorer caveats to go in with eyes open

Each of these is a real prerequisite or limit, not a risk to note and forget:

1. **`cornell:*` must be activated as user-defined cost allocation tags** in the Billing console.
   Manual, one-time, per-account, out-of-band — nothing in this repo can do it, and it needs billing
   console access that PR-only builders do not have. **Until it is done, every tag-grouped cost
   query returns unattributed totals.**
2. **Activation is not retroactive.** Cost allocation tag data begins at activation, so "cost YTD by
   application" will be blank for the period before it — a caveat the UI must state rather than
   present as zero spend.
3. **Cost Explorer lags 24–48h.** "Cost today" is really "cost as of the last finalized day". The
   UI must say so, reusing the staleness-display honesty FR-4.4 already requires of the inventory
   snapshot.
4. **`GetCostAndUsage` costs $0.01 per paginated request.** Hence T1's separate daily schedule.
   Polling it hourly would spend real money re-reading data that had not changed.
5. **CE access can be restricted by the payer** in an Organization member account. If this account
   is a member and CE is denied, the Financial Dashboard degrades to its empty state — which must be
   distinguishable from "no spend".
6. **"Cost by model" is not reachable through CE at all** (§0). Per-model usage types exist for
   *in-account* on-demand Bedrock, but this account's chat spend is not in-account. Even for the
   embedding spend that *is* here, the exact usage-type strings were **not verified** — no live doc
   access this session, and no account to query.

---

## 4. Cardinality and PII — two traps in the metric list

**"Cost by user" must not become a metric dimension.** CloudWatch custom metrics are billed
per-metric-per-month (~$0.30), and a dimension is part of a metric's identity — so a per-user
dimension creates one metric per user, per counter. A thousand users across a handful of counters is
hundreds of dollars a month to *observe* a workshop chatbot. Per-user attribution belongs in
**structured logs** (queryable on demand via Logs Insights), not in metric dimensions.

**And it must not carry PII.** The user asked for cost by user "depends on application, sometimes
it's not applicable" — correct, and there is a second reason to be careful: NetIDs are personal
data, `SECURITY-04` forbids PII in logs, and the domain core's structural rule (NFR-S1) forbids an
exception message carrying a NetID. If per-user attribution is ever built, the identifier must be a
**stable non-identifying pseudonym**, and the decision to build it is its own pass.

Neither is built in this pass. Both are recorded so a later pass starts from them.

---

## 5. What this round changes

- `requirements.md` — **not rewritten.** FR-8 and §6 gain pointers to the amendment (approved
  artifact; amendment discipline per `amendments/repo-baseline-2026-08-03.md`).
- `amendments/telemetry-fr9-2026-08-07.md` — **new**, carrying FR-9 (usage telemetry) and FR-10
  (cost data, superseding FR-8's deferral).
- `user-stories/stories.md` — **extended** with a Round-2 section; US-D1/US-D2 gain superseded
  pointers now that the decision blocking them is made.
- `docs/aidlc/dashboard/design/*` — the four open decisions these drafts left (emission mechanism,
  id-under-composition, CloudWatch scope, LiteLLM blocker) are answered by T5–T8; those files are a
  separate track's reference drafts and are annotated, not rewritten.
