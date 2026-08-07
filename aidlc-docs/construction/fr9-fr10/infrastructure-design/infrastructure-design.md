# Infrastructure Design — FR-9 / FR-10 increment

**Stage**: CONSTRUCTION → Infrastructure Design (FR-9/FR-10)
**Date**: 2026-08-07
**Scope**: what CloudFormation and pipeline changes the increment needs. NFR Design is folded in here
per the construction plan — U-02's six NFR patterns are inherited unchanged, and only the genuinely
new decisions are recorded.

---

## 1. Template placement — all of it in `dashboard.yml`

| Option | Verdict |
|---|---|
| Extend `dashboard.yml` (the app stack) | **Chosen** |
| A new `dashboard-telemetry.yml` stack | Rejected — it would need the snapshot bucket name and the distribution, and this repo has **no CloudFormation exports anywhere**, so cross-stack references would have to be reconstructed by `!Sub` naming convention. That was already accepted once (the notify-topic ARN) and doubling down on it for resources with no independent lifecycle buys nothing. |
| Extend `dashboard-storage.yml` (stateful) | Rejected for the compute; **the three S3 keys need no template change at all** (keys are not resources). |

Consequence: **`pipeline/stacks.yml` is unchanged** — no new template is registered, so the
three-file mirror (template + registry + action) does not apply. Worth stating because a reviewer who
knows that rule will look for the missing registry entry.

## 2. New resources in `dashboard.yml`

| Logical id | Type | Notes |
|---|---|---|
| `CostFunction` | `AWS::Lambda::Function` | `Condition: HasCollectorImage`; **same** `CollectorImageUri`, entrypoint overridden by `ImageConfig.Command: ['dashboard.cost.handler.handler']`; arm64; 512 MB; Timeout 60; `ReservedConcurrentExecutions: 1` |
| `TelemetryFunction` | `AWS::Lambda::Function` | as above with `dashboard.telemetry.handler.handler`; Timeout 120 (it fans out over models) |
| `CostRole` / `TelemetryRole` | `AWS::IAM::Role` | §3 |
| `CostLogGroup` / `TelemetryLogGroup` | `AWS::Logs::LogGroup` | **14-day** retention, not 30 — §5 |
| `CostSchedule` | `AWS::Scheduler::Schedule` (or Events rule, matching `CollectorSchedule`'s existing type) | `!Ref CostScheduleExpression`, default `rate(1 day)`; `MaximumRetryAttempts: 0` (inherits DR-02's no-DLQ decision — a failed run is retried by the next tick, and a retry inside the hour would spend another $0.01 for data that has not changed) |
| `TelemetrySchedule` | same | reuses the existing hourly `ScheduleExpression` parameter |
| `ModelRatesParameter` | `AWS::SSM::Parameter` | `Name: !Sub '/${Application}/${Environment}/dashboard/model-rates'`, `Type: String`, `Value: '{}'` — an **empty table**, deliberately: FR-10.8 item 3 is unresolved, and shipping a guessed rate would produce confident wrong money. Empty ⇒ COST-14 ⇒ *rate missing*. **`Tags` is a map on this type**, not a list (a `CLAUDE.md` gotcha) |
| `CostFailureAlarm`, `CostStaleAlarm`, `TelemetryFailureAlarm` | `AWS::CloudWatch::Alarm` | mirror `CollectorNotRunningAlarm`'s `TreatMissingData: breaching` shape |
| `CostAccessDeniedAlarm` | `AWS::CloudWatch::Alarm` | **separate alarm, deliberately** — see §6 |

**Parameters added**: `CostScheduleExpression` only. The SSM path is derived by `!Sub`, so it needs no
parameter; per `CLAUDE.md` the one new parameter is passed **explicitly** from the pipeline.

## 3. IAM — one role per function, each scoped to one action set and one key

| Role | Allowed | Scope |
|---|---|---|
| `CostRole` | `ce:GetCostAndUsage` | `Resource: '*'` — **documented exception**: Cost Explorer has no resource-level ARN scoping, exactly as `tag:GetResources` does not. Recorded in the same place and shape as `requirements.md` §4.6(2), not silently. |
| | `s3:PutObject` | the **cost key only** (`arn:.../cost/current.json`) |
| `TelemetryRole` | `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics` | `Resource: '*'` — same documented exception; neither action supports resource scoping |
| | `s3:PutObject` | the **telemetry key only** |
| `ApiRole` *(existing, widened)* | `s3:GetObject` | from one key to **three**, still enumerated — never `bucket/*` |
| | `ssm:GetParameter` | the one rates parameter, by ARN |

**Per-key write scoping is what enforces A4.1's "no writer reads or writes another's object."** It is
an IAM property, not a code convention — which is why the three-object layout is safe rather than
merely intended.

## 4. Inherited NFR patterns — unchanged, listed so the inheritance is explicit

C-10 and C-11 are the same *shape* of component as C-01, so all six of U-02's NFR-design patterns carry
over with no new decision: declarative `botocore.Config` timeouts + standard retries; internal deadline
from `context.get_remaining_time_in_millis()`; stdlib `logging` + JSON formatter; EMF metrics as a log
line (no API call, nothing to throttle on the failure path); one outer error boundary; and
`MaximumRetryAttempts: 0` with no DLQ.

## 5. NFR-T8 — this increment's own recurring cost, against a measured $9.02/month

The one place where inheriting U-02's defaults would have been wrong.

| Driver | Rate | Estimate | Note |
|---|---|---|---|
| `ce:GetCostAndUsage` | $0.01/request | **~$0.21/mo** | 7 calls/day × 30 (COST-05 budget) |
| `cloudwatch:GetMetricData` | ~$0.01/1,000 metrics | **< $0.05/mo** | ~50 metrics/hour |
| Lambda invocations (2 more functions) | — | **< $0.01/mo** | 24 + 1 runs/day at 512 MB |
| **CloudWatch Logs (2 new groups)** | ingest + storage | **~$0.10–0.30/mo** | the one that needed a decision |
| **Total** | | **~$0.40–0.60/mo ≈ 5% of the account** | |

**Two decisions this analysis drove**, rather than confirmed:

1. **Log retention on the new groups is 14 days, not the 30 the existing groups use.** CloudWatch is
   already ~18% of this account's spend (A3.6) and these two groups add nothing diagnostically after a
   fortnight — a failed cost run is retried the next day. Copying the 30-day default would have been
   the unexamined choice.
2. **`max_ce_calls` is a config value with a small default, and the actual count is emitted** (COST-05,
   COST-06). Without the metric, the estimate above is an assertion; with it, the dashboard can show
   its own cost line (design Q8) from measured data.

For comparison, the rejected alternatives: hourly CE polling would be **~$5.04/mo** (7 calls × 24 × 30),
i.e. **over half the account's total spend** — which is what T1's separate daily schedule avoids. Ten
per-user custom metrics would be ~$3/mo, ~33%; FR-10.9 avoids that.

## 6. `ACCESS_DENIED` gets its own alarm, and that is the operationally important detail

Every other collector failure is **retry-shaped**: throttling, a timeout, a transient upstream error —
the next tick fixes it, and an alarm means "watch it."

`ACCESS_DENIED` from Cost Explorer is **not**. Per A3.3 this account is a linked member account and
cannot activate cost allocation tags at any privilege level; only the Organization payer can. A retry
tomorrow, and every tomorrow after, will fail identically. So a single "cost collector failed" alarm
would train whoever owns it to ignore the one condition that actually needs a human — and a human
*outside this team*.

Hence a distinct alarm whose description names the required action: *the Organization payer must
activate `cornell:*` cost allocation tags; retrying will not help.*

## 7. Pipeline changes

| Change | Size |
|---|---|
| **No new Build action** | 0 bytes — the Q3 refinement reuses the collector image via `ImageConfig.Command` |
| **No new BlueprintDeploy action** | 0 bytes — the resources land in the existing `dashboard.yml` |
| `CostScheduleExpression` in `DashboardCloudFormation`'s `ParameterOverrides` | ~45 bytes |
| **C-14 catalog build step** in `SiteBuildProject`'s buildspec | ~120 bytes: one command collecting `blueprints/*/blueprint.yaml` `telemetry:` blocks into a catalog JSON |
| **Comment condensation** | reclaim ≥ 500 bytes |

`pipeline.yml` is at **50,966 / 51,200 bytes — 234 free** (measured). The additions above fit, but
would leave ~70 bytes, which is too fragile to hand to the next person. So condensation is part of the
work, not a contingency.

**Where C-14's catalog goes**: written by the build step and **baked into the container image** —
which means it must be produced *before* the image build, i.e. in the container build's context rather
than the site build. **Open for Code Generation**: either the catalog is generated into the build
context by the container Build action, or it is committed as a generated file and validated in
`tools/check`. The second is more inspectable and needs no pipeline change at all; the first cannot
drift. Deciding it needs the buildspec in front of me.

## 8. Not changed

`dashboard-storage.yml` (keys are not resources), `stacks.yml` (no new template), `blueprint.yaml`'s
`template:` (unchanged), the WAF/CloudFront/edge configuration (no new origin, no new path pattern —
the new routes are all under the existing `/api/*` behaviour).
