# Amendment A2 — Usage telemetry (FR-9) and cost data (FR-10)

**Date**: 2026-08-07
**Stage**: INCEPTION → Requirements Analysis, **second pass** (the one
`requirements/requirement-amendment-questions-telemetry.md` Q3 = B queued on 2026-08-03)
**Decisions this implements**: T1–T8 in
`requirements/requirement-amendment-questions-telemetry-round-2.md`
**Depth**: Standard, consistent with the first pass

## Why this document rather than edits to `requirements.md`

`requirements.md` is **approved** (2026-08-03). Rewriting an approved conclusion in place destroys
the record of what was approved and when, so — exactly as `repo-baseline-2026-08-03.md` did — the
affected passages keep their original text and gain a pointer here. This document adds **FR-9** and
**FR-10**; FR-10 supersedes FR-8's deferral.

**Requirement type**: New Feature (extension of an existing blueprint).
**Scope**: Multiple Components — the collector gains two new read paths, the snapshot gains two
sibling sections, the read API gains routes, the UI gains two dashboards. Also a **cross-blueprint
contract** other blueprints later implement.
**Complexity**: Moderate-to-Complex — not for any single AWS primitive, but because the data this
request asks for is split across three sources with different freshness, different reachability, and
one that is off-account entirely (§0 of the Round-2 questions).

---

## The frame this is written inside

Per `docs/aidlc/dashboard/design/composable-dashboards.md` §4.1 — *"when FR-9 is written, it should
cite this document's contract (§2.2) as its cross-blueprint frame … If FR-9 diverges from §2.2, FR-9
wins and this document is updated"* — the frame is that document's **Layer 2**, and
`observability-contract.md`'s **three parts** (tag contract / manifest declaration / runtime
emission). FR-9 below is that contract made specific.

Four of those documents' open decisions are **now answered** and should be read as closed:

| Open decision | Answered by | Answer |
|---|---|---|
| `observability-contract.md` #2 — emission mechanism | T7 + FR-9.2 | CloudWatch EMF to the blueprint's own log group. Ratified. |
| `composable-dashboards.md` #3 — deployment-id under composition | T8 + FR-9.3 | Neither flat-forever nor deferred: an `agent_id` dimension that defaults to `deployment_id`. |
| `dashboard-sources.md` #4 — CloudWatch least-privilege scope | FR-9.5 | Read only manifest-declared counters + a fixed AWS namespace list. |
| `dashboard-sources.md` §6 — LiteLLM `auth: secret` blocker | T5 + FR-10.6 | Stays blocked. Model cost is *estimated* from counters meanwhile, and labelled as an estimate. |

One is **not** answered and is explicitly left open: `dashboard-sources.md` #1 (probe freshness) and
#3 (SSRF surface) concern `http-probe` sources, which this pass does not add.

---

# FR-9 — Custom usage telemetry (Layer 2 of the observability contract)

Implements Round-1 Q1 = A (blueprints emit their own business-level counters, the dashboard displays
them joined on the deployment key) and Round-1 Q4 (usage, value, and cost-justification questions).

## FR-9.1 — The contract is a convention plus a reader, not a dashboard feature

1. The deliverable MUST be a **contract other blueprints implement**, in the same sense the four
   `cornell:*` tags are a contract — plus a reader in this blueprint. A blueprint that does not
   implement it MUST remain fully inventoried and cost-attributed, and MUST be shown as *not
   instrumented* rather than as reporting zero.
2. The contract MUST have a **declarative half checkable at PR time without deploying** and a
   **runtime half verifiable only live**, so conformance is mostly enforced statically.
3. The reader MUST live inside `blueprints/dashboard/` for now (Round-1 Q2 = C). The move to
   `observability/` is triggered **when a second blueprint actually emits usage** — not on a date,
   and not merely when a second blueprint has compute.

## FR-9.2 — Emission mechanism: CloudWatch EMF (T7)

1. A blueprint MUST emit declared counters as **CloudWatch Embedded Metric Format log lines to its
   own log group** — no API call, no additional IAM, nothing that can throttle on a failure path.
   This is the mechanism `blueprints/dashboard/src/dashboard/shared/emf.py` already uses for the
   dashboard's own operational metrics, so the pattern is established rather than introduced.
2. The mechanism MUST satisfy **write-own / no-read-peer**: a deployment writes only to its own log
   group and its own dimension values, and has no read path to another deployment's telemetry. This
   is the property Track D's isolation model requires, and it is why a shared bus was rejected.
3. Namespace MUST be `Cornell/Blueprints/<blueprint-name>`.
   **Recorded inconsistency, deliberately not resolved here:** U-02's own operational metrics use the
   namespace `Dashboard`, not `Cornell/Blueprints/dashboard`. Those are *operational* metrics
   (US-14), not *usage* counters, so the two namespaces are not in conflict — but the naming will
   read as an inconsistency to the next person, and renaming U-02's namespace would break alarms
   that name it literally. Flagged for Application Design, not decided in Requirements.

## FR-9.3 — Dimensions, including the per-agent dimension (T8)

1. Every emitted counter MUST carry these dimensions:

   | Dimension | Required | Meaning |
   |---|---|---|
   | `deployment_id` | yes | the existing join key, the value of `cornell:deployment-id` |
   | `agent_id` | yes, **defaulting to `deployment_id`** | which agent within the deployment produced the measurement |
   | `model` | where the counter concerns a model call | the model identifier the call used |

2. `agent_id` MUST default to `deployment_id` so a single-agent deployment — every deployment that
   exists today — needs no additional configuration, while a deployment running several agents
   attributes correctly. Because the dimension is present from the first emission, multi-agent
   support is a **change of values, not a schema migration**.
3. The **format** of `agent_id` MUST NOT be fixed by this pass. If Track D later defines
   parent/sub-id composition semantics, `agent_id` is where a sub-id lands.
4. A dimension value MUST NOT be a tag value, an ARN, a NetID, an end-user identifier, or any other
   personal data, and MUST be low-cardinality. This extends CR-04's existing rule, which
   `emf.py` already documents: *"a dimension value lands in CloudWatch as a searchable key, so a tag
   value there would leak a NetID just as a log field would."* The reason is both privacy and cost —
   a dimension is part of a metric's identity, so a high-cardinality dimension multiplies billed
   custom metrics (see FR-10.9).

## FR-9.4 — Declaration: a blueprint says what it emits

1. A blueprint MUST declare its telemetry **in its `blueprint.yaml`**, extending the manifest the
   Cornell Builder already parses rather than introducing a parallel mechanism. Shape:

   ```yaml
   telemetry:
     emits: true|false
     namespace: "Cornell/Blueprints/<name>"
     counters:
       - name: requests
         unit: Count
         description: model calls issued
   ```

2. `emits: false` MUST be a **first-class, honest state**, and a manifest with no `telemetry:` block
   MUST be treated as `emits: false`.
3. A declared counter MUST name its unit and a human-readable description, because the UI renders
   counters **generically** — it MUST NOT special-case any blueprint, and a new emitting blueprint
   MUST light up with **no edit to the dashboard**. That property is the test of whether this
   contract is correct.
4. Manifest ↔ declaration agreement SHOULD be checkable by the repo's existing PR checks, in the
   same spirit as `pipeline/stacks.yml` registration. (Whether that check lands in
   `validate_stacks.py` or beside it is an Infrastructure Design decision.)

## FR-9.5 — The reader

1. The dashboard MUST read declared counters back via **`cloudwatch:GetMetricData`**. Combined with
   T7, this gives exactly **one metrics read mechanism** serving two kinds of namespace:
   app-emitted (`Cornell/Blueprints/*`) and AWS-emitted (`AWS/*`).
2. The reader MUST read **only counters a manifest declares**, plus a fixed list of AWS namespaces —
   a closed allowlist, mirroring FR-3.3's rule for API parameters. It MUST NOT discover and render
   arbitrary metrics.
3. Telemetry MUST land in the snapshot as an **additive sibling section**, under the existing
   `schema_version` scheme, not as a parallel versioning string and not as a migration. This is the
   headroom `application-design.md` §8 reserved for exactly this amendment.
4. Telemetry collection MAY share the existing inventory schedule; `GetMetricData` is inexpensive and
   its data advances continuously. Cost collection MUST NOT (FR-10.4).
5. Read failure MUST degrade the same way inventory does (FR-4.4, SECURITY-15): the last good
   telemetry with its true timestamp, or an explicit error state — never a fabricated or
   zero-looking figure.

## FR-9.6 — The Adoption Dashboard: required counters

The counters the dashboard MUST render, from the requested metric list. All are **push-only** — no
AWS-emitted metric can supply them, because generation happens off-account behind the LiteLLM
gateway (Round-2 questions §0):

| Counter | Notes |
|---|---|
| Requests by model | dimensioned by `model` |
| Input tokens | from the model response's usage object |
| Output tokens | as above |
| Error rate | model-call errors ÷ requests. Distinct from Lambda's own `Errors` metric, which measures the function, not the model call |
| Timeout rate | the emitting app knows its own model timeout; AWS cannot infer it |
| Human approval rate | purely application-semantic — no AWS metric has this concept |
| Prompt success rate | as above; the emitting app defines "success" and MUST document its definition in its manifest counter description |
| Completed tasks | required by FR-10.7 (cost per completed task) |

Rates MUST be derived from **two counters** (numerator and denominator) rather than emitted as a
pre-computed ratio, so the dashboard can aggregate correctly across agents and time windows. A
pre-computed rate cannot be re-aggregated without its denominator.

## FR-9.7 — No blueprint is instrumented in this pass (T6)

1. This pass MUST deliver the contract, the manifest declaration, the reader, and the UI. It MUST
   NOT modify another track's blueprint — specifically **not `blueprints/teams-bot`**, which belongs
   to Track C.
2. Consequently every Adoption panel, plus FR-10.6's model cost and FR-10.7's cost per task,
   **renders an empty state on delivery**. This is a known and accepted consequence, recorded rather
   than discovered.
3. Because the empty state *is* the visible deliverable, it MUST be **informative**: it MUST name
   which blueprints were found and not instrumented, and MUST distinguish these three states from
   one another:
   - *not instrumented* — the blueprint declares `emits: false` or has no `telemetry:` block
   - *instrumented, no data yet* — declared, but no datapoints in the window
   - *cannot read* — the metrics read itself failed
   Collapsing any two of these into one message is a defect, for the same reason US-06 requires "no
   data collected yet" to be distinguishable from "no resources found".

---

# FR-10 — Cost data (supersedes FR-8's deferral)

> **⚠️ This supersedes FR-8.** FR-8 recorded cost as a stretch goal with the data source
> deliberately undecided (R1-Q2 = C), and FR-8.3 required that *"when cost is taken up, the decision
> MUST be revisited as its own clarification, capturing the known tradeoff."* T1 is that
> clarification. FR-8's text stands as the record of what was approved on 2026-08-03; FR-10 is what
> now governs.

## FR-10.1 — Source: Cost Explorer, not CUR (T1)

1. Platform cost MUST be read from the **Cost Explorer API** (`GetCostAndUsage`).
2. **CUR is rejected**, with the reason recorded: a CUR export is configured at an Organization's
   management account, and this is a shared workshop account whose payer-level standing is not
   controlled by this project. FR-8.3 named this exact tradeoff; the resolution is to take the
   self-service option. Cost Explorer additionally needs no S3 export, no Athena/Glue, and no
   query infrastructure — consistent with serverless-first and with not building what isn't needed.

## FR-10.2 — Platform cost figures

The Financial Dashboard MUST show, for platform (infrastructure) spend:

1. **Cost today** — which MUST be presented as *cost as of the last finalized day*, not as a
   real-time figure, because Cost Explorer lags 24–48h (FR-10.5).
2. **Cost this month** — month-to-date.
3. **Cost year-to-date.**
4. **Budget remaining is explicitly NOT in scope** (T4). No AWS Budgets dependency is introduced,
   and no manually-configured ceiling is added.

## FR-10.3 — Cost breakdowns

1. MUST break platform cost down by **`cornell:blueprint`** (the "by application" axis) and by
   **`cornell:deployment-id`**.
2. **"By department" is NOT in scope** (T2). No `cornell:department` tag exists, and adding a fifth
   required tag is a platform-wide change affecting every blueprint and every existing resource —
   out of proportion to this pass. `cornell:owner` remains available as the closest existing axis.
3. **"By agent"**: model cost MUST split by `agent_id`; infrastructure cost MUST NOT claim to.
   Several agents share one Lambda or AgentCore runtime and AWS bills the resource, so an
   agent-level split of infrastructure cost would be fabricated. The UI MUST NOT present one.
4. **"By user" is NOT built** (see FR-10.9).
5. **"By model"**: see FR-10.6 — not available from Cost Explorer at all.

## FR-10.4 — Cost collection runs on its own, slower schedule

1. Cost collection MUST run on a **separate schedule from inventory collection**, at a **daily**
   cadence, and MUST NOT be attached to the hourly inventory tick.
2. The reason is explicit: **`GetCostAndUsage` is billed at $0.01 per paginated request**, and its
   data advances only once a day. Hourly polling would spend real money re-reading unchanged data —
   a dashboard whose purpose is cost control must not itself be a silent cost.
3. The cadence MUST be a stack parameter, consistent with FR-2.3.
4. Whether this is a second Lambda or the existing collector on a second event is an **Application
   Design** decision, not fixed here.

## FR-10.5 — Prerequisites and honest degradation

Each of these MUST be surfaced in the UI rather than rendering as zero spend:

1. **`cornell:*` must be activated as user-defined cost allocation tags** in the Billing console —
   manual, one-time, per-account, and impossible from this repo or from a PR-only builder's access.
   Until it is done, tag-grouped queries return **unattributed** totals, and the UI MUST say so.
2. **Activation is not retroactive.** Tag-attributed cost begins at activation, so year-to-date
   breakdowns will be incomplete for the earlier period. The UI MUST distinguish *"no spend"* from
   *"spend not attributable because tags were not yet active."*
3. **The 24–48h lag MUST be displayed**, reusing the staleness-honesty pattern FR-4.4 already
   requires of the inventory snapshot.
4. **Cost Explorer access may be denied by the payer** in an Organization member account. That MUST
   render as an explicit "cost data unavailable" state, distinguishable from zero spend
   (SECURITY-15 fail-closed).
5. The blueprint README MUST document the activation step, the lag, and the per-request cost, in the
   same way it documents the WAF access model's limits (§4.5 of `requirements.md`).

## FR-10.6 — Model cost: estimated now, reconciled later (T5)

1. Model cost **cannot be read from Cost Explorer**, because chat generation happens through
   Cornell's LiteLLM gateway and is therefore not spend in this AWS account (Round-2 §0). This is a
   finding about the deployed system, not a limitation of the API.
2. The dashboard MUST therefore show model cost as an **estimate**, computed as
   `tokens × a configured per-model rate table`, using the token counters of FR-9.6.
3. The estimate MUST be **labelled as an estimate wherever it appears**, and MUST NOT be totalled
   into the same figure as Cost Explorer's actual platform spend without the distinction remaining
   visible. Presenting a derived estimate as billed cost would be fabricated data — precisely what
   SECURITY-15 forbids.
4. The **rate table MUST be configuration, not hardcoded** — model prices change, and a stale
   hardcoded rate silently produces wrong money. It MUST be updatable without a code change.
5. **LiteLLM's own usage API is recorded as the authoritative source** to replace the estimate when
   it becomes reachable. It remains **`status: BLOCKED`** per `dashboard-sources.md` §6: there is no
   established pattern by which a builder-composed blueprint obtains a credential for an external
   authed service under PR-only, no-console access. That blocker is a **platform decision, not a
   dashboard one**, and solving it unblocks every `auth: secret` source at once.
6. Until an emitter exists (FR-9.7), the estimator reads zero. It MUST still be built and tested
   against fixtures, and MUST render FR-9.7's *not instrumented* state rather than "$0.00".

## FR-10.7 — Cost per completed task

1. MUST be derived as cost ÷ the `completed tasks` counter (FR-9.6), and MUST make clear **which**
   cost it divides — estimated model cost, platform cost, or both — rather than presenting an
   unqualified figure.
2. MUST show the *not instrumented* state, not a division by zero or a zero result, when no
   completed-task counter is present.

## FR-10.8 — What "cost by model" needs verified before build

Recorded because it was **not** verifiable in this session (no live documentation access, no account
to query), and building against an assumption here would produce silently wrong money:

1. The exact Bedrock **usage-type strings** that encode a model identifier, if per-model in-account
   attribution is ever needed for the embedding spend that *is* local.
2. Whether `GetCostAndUsage` grouping by `USAGE_TYPE` splits per model as expected in this account.
3. The current per-model rates for the rate table of FR-10.6.

## FR-10.9 — Cost by user: not built, and the two reasons

1. Per-user cost attribution MUST NOT be built in this pass.
2. **Reason one — no identity exists.** v1 has no authentication by design (FR-4.5, and the
   SECURITY-13 accepted exception in §4.6): the dashboard cannot identify a user, and the user's own
   framing was correct that this "depends on application, sometimes it's not applicable."
3. **Reason two — a per-user metric dimension is a cost trap.** CloudWatch bills custom metrics
   per-metric-per-month and a dimension is part of a metric's identity, so a per-user dimension
   creates one metric per user per counter. A workshop chatbot with a thousand users would cost
   hundreds of dollars a month to observe. If per-user attribution is ever built it belongs in
   **structured logs**, queried on demand, not in metric dimensions.
4. Any future per-user identifier MUST be a **stable non-identifying pseudonym**, never a NetID —
   SECURITY-04 forbids PII in logs and NFR-S1 forbids it in error messages.

---

## New non-functional requirements

| ID | Requirement |
|---|---|
| **NFR-T1** | Estimated figures MUST be visually distinguishable from billed figures everywhere they appear (FR-10.6.3). |
| **NFR-T2** | The per-model rate table MUST be configuration, updatable without a code change (FR-10.6.4). |
| **NFR-T3** | Metric dimensions MUST stay low-cardinality and free of personal data (FR-9.3.4), extending CR-04 and matching the rule `emf.py` already documents. |
| **NFR-T4** | Cost Explorer calls MUST be bounded and their per-request cost documented; the dashboard MUST NOT become a material cost itself (FR-10.4.2). |
| **NFR-T5** | The reader MUST read only declared counters and a fixed AWS namespace list — a closed allowlist, mirroring SECURITY-05 / FR-3.3 (FR-9.5.2). |
| **NFR-T6** | New IAM MUST be least-privilege (SECURITY-06): `ce:GetCostAndUsage` and `cloudwatch:GetMetricData`, read-only. Any unavoidable account-wide breadth MUST be documented as an accepted exception the way `tag:GetResources` already is. |
| **NFR-T7** | Every new panel MUST distinguish *not instrumented* / *no data yet* / *cannot read* (FR-9.7.3), consistent with SECURITY-15 and US-06. |

## Documented exceptions added to `requirements.md` §4.6

5. **Model cost is an estimate, not billed cost** — compensating control: labelled as an estimate
   everywhere (NFR-T1), with the authoritative source named and its blocker recorded (FR-10.6.5).
   Accepted because the alternative is showing no model cost at all while the credential problem
   remains a platform-level unknown.
6. **Cost attribution depends on a manual, out-of-band Billing-console step** (FR-10.5.1) that no
   part of this repo can perform or verify. Compensating control: the UI states when attribution is
   unavailable rather than rendering it as zero.

## Requirements that remain out of scope

Unchanged from `requirements.md` §6, plus:

- Budget tracking and budget-remaining figures (T4).
- Department-level cost attribution and any fifth `cornell:*` tag (T2).
- Per-user cost or usage attribution (FR-10.9).
- Instrumenting any blueprint, including `teams-bot` (FR-9.7).
- A direct AgentCore API integration separate from CloudWatch (T7).
- LiteLLM and every other `auth: secret` source (FR-10.6.5).
- `http-probe` sources, and therefore `dashboard-sources.md`'s open decisions #1 and #3.
