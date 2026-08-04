# Integration Note — Salvaging the fork's Bedrock/CloudWatch telemetry

**Status**: Reference spec. Captures work that exists only in a separate, unmerged fork so it is
not lost when that copy is. **No code is being merged by this note** — it records *what to build*
and *what to change* when the integrated branch reaches the point of building a CloudWatch source.
**Date**: 2026-08-04
**Companions**: `dashboard-sources.md` (the source catalog — this is the concrete `cloudwatch`
entry), `observability-contract.md` (Layer-1 pull path), `composable-dashboards.md`.

---

## 1. Why this note exists

Two lines of dashboard work descended from the same ancestor commit (`9723168`) and diverged:

- **Integrated branch** (`origin/dashboard`, current): drove the AI-DLC workflow forward — U-01
  Domain Core complete and tested (60 tests pass, 9/9 mutants killed), U-02 through NFR Design. Its
  `core/` is a hardened rewrite: `model.py` (497 lines), `aggregation.py` (262), `errors.py` (typed
  hierarchy). **It has no telemetry / CloudWatch module.**
- **A separate fork** (was at `/Users/cjc73/Downloads/ai-dlc-workshop`, HEAD `52b660c`): stayed on
  the pre-reorg baseline and its `core/` is the older, simpler form (`model.py` 173 lines,
  `aggregation.py` 113, no `errors.py`) — **but it alone contains `core/telemetry.py`**, a worked
  implementation of reading Bedrock agent-health metrics from CloudWatch.

A file-level diff (2026-08-04) confirmed the fork's `telemetry.py` was **not** carried into the
integrated branch and **cannot be dropped in as-is** (see §4). Its real value is as a *spec for what
to collect and how to shape it* — captured here before the Downloads copy disappears.

## 2. What the fork's `telemetry.py` actually is

A **pure-Python** model (no `boto3`) for the CloudWatch source that `dashboard-sources.md` describes
abstractly. It maps to the observability contract's Layer-1 pull path: inventory snapshot → identify
Bedrock-calling resources by `cornell:*` tags → `GetMetricData` on the `AWS/Bedrock` namespace →
per-agent health records.

**The metric set (the genuinely reusable domain knowledge)** — from
`https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring-runtime-metrics.html`, namespace
`AWS/Bedrock`:

| Group | Metrics (Stat) |
|---|---|
| Volume & latency | `Invocations` (Sum), `InvocationLatency` (Avg), `TimeToFirstToken` (Avg) |
| Errors | `InvocationClientErrors` (Sum), `InvocationServerErrors` (Sum), `InvocationThrottles` (Sum) |
| Tokens (usage) | `InputTokenCount`, `OutputTokenCount`, `CacheReadInputTokens`, `CacheWriteInputTokens` (all Sum) |

**The record shape** — `BedrockAgentHealth`: identity (`function_name`, `arn`, `model_id`) + the
three `cornell:*` join fields (`blueprint`, `deployment_id`, `owner`) + `collected_at` + the metric
values, with derived properties: `total_errors`, `error_rate`, `total_tokens`, `uptime_pct`, and a
`status` enum (`ok` / `warn` / `err` / `idle` / `stale`) computed from error-rate and volume
thresholds.

**Aggregations**: `aggregate_by_blueprint` and `aggregate_by_model` (both pure), plus
`evaluate_telemetry_freshness` (2h default staleness threshold — Bedrock metrics can lag minutes).

**Keep these three things** when porting — they are the domain knowledge that took real effort:
1. the `AWS/Bedrock` metric list and stats,
2. the `status` derivation thresholds (err_rate > 0.5 / server_errors > 10 / throttles > 10 → `err`;
   > 0.05 / >0 / >2 → `warn`), and
3. keying every record on `cornell:deployment-id` — the contract's join key.

## 3. Why it fits the roadmap (and where)

- It is the concrete implementation of the **`cloudwatch` source** in `dashboard-sources.md` §4.1 —
  `kind: aws-api`, `auth: iam`, no secret. It is in the *unblocked* half of the source catalog (it
  never needs the deferred builder-credential model that blocks LiteLLM).
- It is a **U-02 concern** (it reads a live AWS API), so the natural moment to port it is **U-02 Code
  Generation**, when the collector is built. The pure model itself could live in U-01's `core/`
  (laptop-testable), with the `boto3` `GetMetricData` call in U-02's collector — matching the branch's
  existing split (pure `core/` + AWS-facing collector).

## 4. Why it can't be copied — the required changes

The fork's file was written against the fork's *older* domain core and predates the integrated
branch's hardening rules. Porting = rewriting it to the current contracts, not moving the file:

1. **Purity: remove all inline clocks.** The fork uses `datetime.now(UTC)` in
   `field(default_factory=...)`, `__post_init__`, `build_telemetry_snapshot`, and
   `evaluate_telemetry_freshness`. The integrated `model.py` forbids this — *"no clock… the
   `tools/check` boundary grep enforces that mechanically."* `evaluate_freshness` in the integrated
   aggregation already takes an **injected `now`**; the telemetry freshness/`status` logic must do the
   same (pass `now` in) to be pure and testable.
2. **Immutability: match PAT-1/PAT-2.** The integrated `model.py` wraps every `Mapping` in
   `MappingProxyType` and defines `__hash__` explicitly. A ported `BedrockAgentHealth` (currently
   `frozen=True, slots=True` with plain fields) must follow the same rules if it carries any mapping,
   and its equality/hash must agree so property tests don't flake.
3. **Errors: use the typed hierarchy, carry no PII.** The fork raises bare `ValueError`. The
   integrated branch has `errors.py` with `CoreError` subtypes and a **structural NFR-S1 rule: no
   exception carries an ARN, tag key, tag value, or NetID** — because a message can reach a log group
   or an HTTP body. A Bedrock ARN/`ModelId` in a raised message would violate that. Raise a
   `CoreError` subtype with fixed detail; keep identifiers out of the message.
4. **Status/skip vocabularies should be closed enums**, consistent with `SkipReason` (`StrEnum`),
   rather than the fork's free-text status strings — if any of them become mapping keys or snapshot
   fields (the `SkipReason` rationale in `errors.py`).
5. **Schema versioning: align with the real snapshot.** The fork's `schema_version =
   "v1-bedrock-telemetry"` is standalone. The integrated `model.py` already carries a `SCHEMA_VERSION`
   and sibling-key headroom *specifically for the queued telemetry amendment*. Telemetry should land as
   an **additive sibling section** under that scheme, not a parallel versioning string — this is what
   `application-design.md` §8 and `observability-contract.md` were designed to allow.

## 5. Recommendation

- **Do not regress** the integrated `core/` toward the fork. The integrated version is the mature one.
- **Treat the fork's `telemetry.py` as a captured spec** (§2) — the metric set, thresholds, and record
  shape are the reusable parts.
- **Port at U-02 Code Generation**, rewriting to the five contracts in §4, landing the pure model in
  `core/` and the `GetMetricData` call in the U-02 collector.
- **Scope check**: the fork specialized on *Bedrock agent health*. The source catalog's `cloudwatch`
  entry is more general (any namespace/dimension). Decide at port time whether to generalize the
  metric list or keep a Bedrock-specific health module as the first concrete CloudWatch consumer —
  Bedrock-first is the honest MVP, since the workshop's compute-bearing blueprints are agents.

## 6. Provenance

The source file was `blueprints/dashboard/core/telemetry.py` at fork HEAD `52b660c` (commit
"Update state + commit NFR artifacts — U-01 Functional Design + NFR Requirements complete",
2026-08-04). That fork is not a git remote of this repo; if the metric definitions or thresholds in
§2 need to be re-verified later, they must be read from that working copy before it is deleted, or
re-derived from the AWS Bedrock runtime-metrics documentation cited in §2.
