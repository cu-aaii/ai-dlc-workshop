# Amendment A3 — FR-9/FR-10 corrected against the real account

**Date**: 2026-08-07 (hours after A2, same day)
**Trigger**: credentials for the deploy account became available mid-session, so the three
"verify-before-build" items A2 quarantined in FR-10.8 could actually be checked — along with the
premise underneath FR-9.6.
**Status**: A2 is **approved**; this amends it. Three of its statements were wrong or too absolute and
are corrected below. FR-9 and FR-10 otherwise stand.
**Method**: read-only calls against account `890349359349` (`cu-cit-aisei-prod-apps`) via SSO
`sso-admin`. Five `ce:GetCostAndUsage` requests at $0.01 each (**~$0.05 total, real money, spent with
explicit user consent**); everything else free (`sts`, `cloudformation list-stacks`,
`cloudwatch list-metrics`, `cloudwatch get-metric-statistics`, `ce list-cost-allocation-tags`).

## Why this exists one day after A2

A2 was written without account access and said so. It quarantined its unknowns rather than guessing,
which was right — and then the unknowns became checkable. Three of them resolved **against** what A2
assumed. Recording that plainly is the point of an amendment trail: A2's text stands as what was
approved, this is what measurement changed.

**A detour worth recording, because it nearly produced confidently wrong answers.** The local AWS
profile named `ai-dlc-workshop` does **not** point at the workshop account — it resolves to
a different account (`cu-ornith-test`), an unrelated Cornell account holding production RDS databases. Only
after listing the SSO session's accounts did the real one appear: `890349359349`
(`cu-cit-aisei-prod-apps`), where all eight `aidlc-*` stacks live. Had the profile name been trusted,
every figure below would have described another team's spend. **The profile name is a trap; verify the
account id, not the profile label.**

---

## A3.1 — FR-9.6 was wrong: the Adoption metrics are NOT all push-only

**A2 said** (FR-9.6): *"All are **push-only** — no AWS-emitted metric can supply them, because
generation happens off-account behind the LiteLLM gateway."*

**Measured**: `AWS/Bedrock` in this account is **not empty**. It carries **38 metric streams across 6
models**, dimensioned by `ModelId`:

| Present | Metrics |
|---|---|
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` (teams-bot's default `MODEL_ID`) | `Invocations`, `InvocationLatency`, `InputTokenCount`, `OutputTokenCount`, `InvocationClientErrors`, `EstimatedTPMQuotaUsage` |
| `us.anthropic.claude-sonnet-4-5-…`, `us.anthropic.claude-sonnet-4-6` | same shape |
| `us.amazon.nova-lite-v1:0`, `us.amazon.nova-pro-v1:0` | same shape |
| `arn:…foundation-model/amazon.titan-embed-text-v2:0` | embedding (the knowledgebase) |

So **requests-by-model, input/output tokens, and error counts are obtainable with no instrumentation
at all** for any call that reaches this account's Bedrock.

**Correction to FR-9.6**: the required counters split into two supply routes, and the reader MUST
consume **both**:

| Counter | Route |
|---|---|
| Requests by model, input tokens, output tokens, error count | **Pull** — `AWS/Bedrock` via `GetMetricData`, dimensioned by `ModelId`. **No emitter needed.** |
| Timeout rate, human approval rate, prompt success rate, completed tasks | **Push** — application-semantic; no AWS metric has these concepts. Unchanged from A2. |

**But the volume qualification is essential, and cuts the other way.** For claude-haiku-4-5 over 14
days: **2 invocations, 14 input tokens, 4 output tokens.** That is a smoke test, not an application
serving users. Billing agrees — see A3.4. So:

> The pull path is **mechanically live and structurally correct, but captures almost none of the real
> traffic**, because the application's generation goes through the LiteLLM gateway off-account. A2's
> underlying finding holds; its absolute phrasing ("will be empty", "push-only") did not.

**Why building the pull path is still worth it** despite near-zero volume today: it costs no
instrumentation, it is the *only* route that works without another track's cooperation (which T6
declined to require), and it **lights up automatically** as direct-Bedrock usage grows —
`course-chatbot` is designed to call Bedrock directly, and `teams-bot`'s own module docstring says
AgentCore *"replaces `_ask()`… the model call moves out of this Lambda into an AgentCore Runtime
container."* At that point this path becomes the primary feed with no dashboard change.

**Consequence for FR-9.7**: the "everything renders an empty state" prediction is **softened but not
withdrawn**. Requests/tokens/errors will show real — if tiny — numbers on day one. Approval rate,
success rate, and completed tasks still render *not instrumented*. The three-state distinction
(NFR-T7) matters more now, not less, because one panel will have data while its neighbour does not.

## A3.2 — T7 (CloudWatch-only for AgentCore) is validated with evidence

`AWS/Bedrock-AgentCore` exists in this account and is substantial — 13 metric names, including
**usage-shaped** and **cost-shaped** ones:

`Sessions`, `ActiveSessionCount`, `Invocations`, `Latency`, `Duration`, `Errors`, `SystemErrors`,
`UserErrors`, `Throttles`, `InboundAuthorizationSuccess`, `WorkloadAccessTokenFetchSuccess`,
`CPUUsed-vCPUHours`, `MemoryUsed-GBHours`.

`builder-mcp` runs there, and AgentCore is a real billed line (A3.4). `Sessions` /
`ActiveSessionCount` are genuine adoption signals available with no instrumentation — worth reading
alongside `AWS/Bedrock`. This closes T7 as correct **for a stronger reason than the one given**: not
merely "AgentCore publishes into CloudWatch so a second integration is redundant," but "the CloudWatch
data is already rich enough to answer adoption questions."

## A3.3 — FR-10.5.1 understated the tag blocker, and FR-10.3 has a trap

**A2 said**: cost allocation tag activation is *"manual, one-time, per-account, out-of-band"* — i.e. a
console step someone could take.

**Measured**: `ce list-cost-allocation-tags` →

```
AccessDeniedException: Failed to list Cost Allocation Tags:
Linked account doesn't have access to cost allocation tags.
```

This is a **linked (member) account in an AWS Organization**, and cost allocation tags are a
**payer/management-account capability**. So it is not a step anyone here can take, with any role —
this account holds `sso-admin` and still cannot. It requires the Organization's management account,
i.e. **a different team**.

**Correction to FR-10.5.1**: the prerequisite is not "someone must click a button in this account's
Billing console." It is *"the Organization's payer account must activate `cornell:*` as cost
allocation tags; this account cannot, at any privilege level."* That converts FR-10.3's tag-based
breakdown from *pending a chore* to *blocked on an external dependency*, and makes US-17's
"attribution unavailable" state the **expected default**, not an edge case.

### The trap — and it is the most important finding here

A2 (FR-10.5.4) anticipated CE access being *denied*, expecting a failure the code could detect.
**That is not what happens.** Grouping by tag **succeeds**:

```
$ aws ce get-cost-and-usage --group-by Type=TAG,Key=cornell:blueprint  (MTD)
cornell:blueprint$      9.0231738003
```

The call returns HTTP 200 and **one group** — key `cornell:blueprint$`, with the **entire $9.02** in
it. The `$` with nothing after it is CE's encoding for *no value for this tag*: every dollar is
unattributed. But a naive implementation sees a successful response containing exactly one group with
the full account total, and would happily render **"cornell:blueprint: $9.02"** — a single confident,
wrong attribution rather than an error.

**New requirement — FR-10.3.6**: the reader MUST treat a CE tag group key whose value component is
empty (`<key>$`) as the **unattributed** bucket, MUST NOT render it as a tag value, and MUST NOT
present it as a named group. Where the unattributed bucket is 100% of spend, the UI MUST show the
"attribution unavailable" state of US-17 rather than a breakdown. This is exactly the failure mode
SECURITY-15 exists to prevent — plausible-looking data that is silently wrong — and it is not
detectable by checking for an error.

## A3.4 — FR-10.8 answered: usage types DO encode the model

All three verify-before-build items resolve:

**1 & 2 — do Bedrock usage types encode the model, and does `GROUP BY USAGE_TYPE` split per model?**
**Yes.** Grouping YTD by `USAGE_TYPE`, filtered to the two Bedrock services, returns:

```
USE1-NovaLite-input-tokens          USE1-NovaPro-input-tokens
USE1-NovaLite-output-tokens         USE1-NovaPro-output-tokens
USE1-TitanEmbeddingV2-Text-input-tokens
USE1-Knowledge-Base:Consumption-based:{Retrieval,AgenticRetrieval,Storage}
USE1-Runtime:Consumption-based:{vCPU,Memory}          (AgentCore)
DataTransfer-{In,Out,Regional}-Bytes
```

Format: **`<REGION>-<ModelShortName>-{input,output}-tokens`**. So per-model cost attribution from CE
is possible **for in-account Bedrock calls**, keyed on usage type rather than on a tag — and
therefore **not blocked by the cost-allocation-tag problem of A3.3**. That is a genuinely useful
escape hatch: model cost by usage type works even though blueprint cost by tag does not.

**Note what is absent**: no Claude usage types appear at all, despite Claude metric streams existing
in CloudWatch. The 2 claude-haiku invocations produced no measurable billed line. Nova and Titan do
have billed token usage, so something in the account genuinely uses them.

**3 — current per-model rates for the estimator table**: still **not** answered. Rates are pricing-page
data, not account data, and web access was unavailable. FR-10.6.4 (rate table as configuration)
remains the mitigation, and FR-10.8 keeps this one item open.

## A3.5 — FR-10.6's estimate is confirmed necessary, by billing rather than by code

**Amazon Bedrock model spend, month-to-date: `$0.0000371`.** Effectively zero, against a $9.02
account total. Bedrock does not appear at all in the YTD list above $0.01.

A2 inferred from reading `teams-bot`'s source that model spend happens off-account. **The billing data
independently confirms it**: there is no meaningful in-account model spend to break down, so
"cost by model" from Cost Explorer would report ~nothing while the real spend sits behind the LiteLLM
gateway. FR-10.6's `tokens × rate table` estimate is therefore **not** a workaround for a missing API
— it is the only route to a number that reflects reality. Unchanged, and now evidenced.

## A3.6 — Measured cost baseline, and what it does to NFR-T4

Month-to-date (2026-08-01 → 08-08), `UnblendedCost`, **total $9.0232**:

| Service | MTD | YTD |
|---|---|---|
| Amazon OpenSearch Service | 6.4437 | 6.44 |
| AWS Config | 1.1420 | 2.46 |
| AWS CodePipeline | 0.4140 | 0.41 |
| **AmazonCloudWatch** | **0.3493** | **2.27** |
| AWS Secrets Manager | 0.2668 | 0.27 |
| Amazon Bedrock AgentCore | 0.2406 | 0.24 |
| CodeBuild | 0.1020 | 0.10 |
| Amazon Cognito | 0.0293 | 0.03 |
| Amazon S3 | 0.0156 | 0.11 |
| AWS Lambda | 0.0099 | — |
| ECR | 0.0063 | — |
| KMS | 0.0036 | 0.02 |
| Amazon Bedrock | **0.0000371** | — |

Two observations that change a requirement:

1. **OpenSearch at $6.44 is 71% of the account** — the knowledgebase's vector store, and it appeared
   only this month. Not a dashboard concern, but it is the single fact anyone opening a cost dashboard
   here will ask about first, so the UI should not bury it.
2. **NFR-T4 is now a live constraint with real numbers, not a caution.** CloudWatch is *already*
   $2.27 YTD — **18% of the account's entire spend** — and the dashboard's whole design adds to
   exactly that line plus Cost Explorer requests:

   | Dashboard cost driver | Rate | Against a ~$9/month account |
   |---|---|---|
   | `GetCostAndUsage`, daily (FR-10.4) | $0.01/request | ~$0.30/mo ≈ **3%** |
   | Custom metrics, if push counters land | ~$0.30/metric/mo | 10 metrics ≈ $3/mo ≈ **33%** |
   | `GetMetricData` on the pull path | ~$0.01/1,000 metrics | negligible |

   **A cost dashboard that becomes a top-three line item in the account it observes has failed at its
   own purpose.** This retroactively vindicates T1's separate daily schedule (hourly CE polling would
   be ~$7.20/mo — comparable to the entire rest of the account) and A2's refusal of a per-user metric
   dimension (which at 1,000 users would exceed total account spend by two orders of magnitude).

**New requirement — NFR-T8**: the dashboard's own operating cost MUST be estimated and documented
against the observed account total before FR-9/FR-10 are built, and custom-metric cardinality MUST be
budgeted explicitly rather than allowed to grow per counter added.

## A3.7 — Deployment state confirmed

Eight `aidlc-*` stacks are live: `account-bootstrap`, `pipeline`, `hello-world`, `notify-topic`,
`knowledgebase`, `aisei-site`, `builder-mcp`, `teams-bot`. **No `aidlc-main-dashboard*` stacks** —
consistent with the `dashboard` branch never having been merged. The four `deployed`-only v1
requirements (SEC-7, A-4, P-6, R-8) therefore remain unverified, as recorded.

---

## Net effect on A2

| A2 statement | Verdict |
|---|---|
| FR-9.6 — every Adoption counter is push-only | **Wrong.** Requests/tokens/errors are pull-able from `AWS/Bedrock` per model (A3.1) |
| FR-9.7 — every new panel renders empty on delivery | **Softened.** Some panels will have real, small numbers; the rest still empty (A3.1) |
| FR-10.5.1 — tag activation is a manual console step here | **Understated.** Impossible from this account at any privilege; payer-only (A3.3) |
| FR-10.5.4 — CE denial will present as an error | **Wrong in the tag case.** Tag grouping succeeds and returns 100% unattributed under a real-looking key (A3.3) → new FR-10.3.6 |
| FR-10.8 — usage-type/model encoding unverified | **Answered.** `USE1-<Model>-{input,output}-tokens`; grouping works (A3.4). Rates still open |
| FR-10.6 — model cost must be estimated | **Confirmed by billing**, not just by code reading (A3.5) |
| T7 — CloudWatch-only covers AgentCore | **Validated, with a stronger rationale** (A3.2) |
| NFR-T4 — don't let the dashboard become a material cost | **Now quantified**; promoted to NFR-T8 (A3.6) |

**Unchanged and still governing**: T1 (Cost Explorer, daily), T2 (department punted), T4 (budget
removed), T5 (estimate now / reconcile later), T6 (no emitter this pass), T8 (`agent_id` defaulting to
`deployment_id`), FR-10.9 (no per-user attribution), and every NFR-T1…T7.

**Stories affected**: US-20 and US-21 gain real data sooner than A2 predicted (their data-present
criteria become testable against the account, not only fixtures); US-17 needs a criterion for the
empty-value tag group. US-18, US-19, US-22, US-23 are unchanged.
