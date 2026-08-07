"""The four cost/usage views (US-16..US-23).

Every response carries **its own section state and its own `collected_at`** -- there is no combined
snapshot age (A4.1). Where a figure is derived rather than billed, `is_estimate` travels with it in the
body (COST-10), so a JSON consumer cannot lose the distinction the UI draws.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from dashboard.api.sections import SectionOutcome, SectionState
from dashboard.core import (
    Counter,
    CounterSeries,
    MalformedRateTable,
    ModelUsage,
    RateTable,
    TelemetryState,
    counter_key,
    cost_per_task,
    derive_rate,
    estimate_model_cost,
    parse_rate_table,
    total_tokens_by_model,
)


def _envelope(outcome: SectionOutcome, data: Any) -> dict[str, Any]:
    return {
        "state": outcome.state.value,
        "collected_at": outcome.collected_at,
        "data": data,
    }


def cost_summary(cost: SectionOutcome) -> dict[str, Any]:
    """US-16: day / month-to-date / year-to-date totals, with what the day figure covers.

    `covered_through` is surfaced beside the totals because it is not the same as `collected_at`:
    Cost Explorer lags 24-48h, so "today" means the last finalized day (COST-04).
    """
    if cost.state is not SectionState.OK or cost.payload is None:
        return _envelope(cost, None)
    payload = cost.payload
    return _envelope(
        cost,
        {
            "currency": payload.get("currency", "USD"),
            "totals": payload.get("totals", {}),
            "covered_through": payload.get("covered_through"),
            "is_estimate": False,
            "ce_calls": payload.get("ce_calls"),
        },
    )


def cost_breakdown(cost: SectionOutcome) -> dict[str, Any]:
    """US-17: attributed groups, the unattributed bucket, and by-service.

    `unattributed` is a named sibling of `attributed`, never an entry in the list -- the shape that
    stops a consumer rendering the empty-value tag group as a blueprint name (FR-10.3.6).
    """
    if cost.state is not SectionState.OK or cost.payload is None:
        return _envelope(cost, None)
    payload = cost.payload
    return _envelope(
        cost,
        {
            "by_blueprint": payload.get("by_blueprint", {}),
            "by_deployment": payload.get("by_deployment", {}),
            "by_service": payload.get("by_service", []),
            "is_estimate": False,
        },
    )


def _counters_from(payload: dict[str, Any], half: str) -> tuple[list[CounterSeries], str]:
    section = payload.get(half, {}) or {}
    state = str(section.get("state", TelemetryState.CANNOT_READ.value))
    series: list[CounterSeries] = []
    for row in section.get("counters", []) or []:
        try:
            series.append(
                CounterSeries(
                    key=counter_key(
                        str(row.get("deployment_id", "")) or "unknown",
                        row.get("agent_id"),
                        row.get("model"),
                    ),
                    counter=Counter(
                        name=str(row.get("name", "")),
                        value=float(row.get("value", 0.0)),
                        state=TelemetryState(str(row.get("state", "ok"))),
                    ),
                )
            )
        except (ValueError, TypeError):
            continue
    return series, state


def _by_name(series: list[CounterSeries], name: str) -> list[CounterSeries]:
    return [s for s in series if s.counter.name == name]


def usage_models(
    telemetry: SectionOutcome, rates_raw: str | None
) -> dict[str, Any]:
    """US-20 + US-18: per-model requests and tokens, plus the labelled cost estimate.

    The estimate is computed **here, at read time**, not stored. Storing it would freeze it against
    whatever rate table was in force at collection, so correcting a wrong rate would not correct
    history. Rates change; token counts do not.
    """
    if telemetry.state is not SectionState.OK or telemetry.payload is None:
        return _envelope(telemetry, None)
    series, aws_state = _counters_from(telemetry.payload, "aws")
    declared, declared_state = _counters_from(telemetry.payload, "declared")

    usage = total_tokens_by_model(
        _by_name(series, "InputTokenCount"), _by_name(series, "OutputTokenCount")
    )
    try:
        rates: RateTable = parse_rate_table(rates_raw) if rates_raw else RateTable()
        rates_state = "ok" if rates.rates else "not_configured"
    except MalformedRateTable:
        # COST-14: a broken table is reported, never silently treated as "no rates".
        rates, rates_state = RateTable(), "malformed"
    estimate = estimate_model_cost(ModelUsage.of(usage), rates)

    models: list[dict[str, Any]] = []
    for model, (tokens_in, tokens_out) in sorted(usage.items()):
        requests = sum(
            s.counter.value
            for s in _by_name(series, "Invocations")
            if s.key.model == model and s.counter.has_value
        )
        models.append(
            {
                "model": model,
                "requests": requests,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "estimated_cost": (
                    str(estimate.per_model[model]) if model in estimate.per_model else None
                ),
                "rate_missing": model in estimate.missing_rates,
            }
        )
    return _envelope(
        telemetry,
        {
            "aws_state": aws_state,
            "declared_state": declared_state,
            "not_instrumented": (telemetry.payload.get("declared", {}) or {}).get(
                "not_instrumented", []
            ),
            "models": models,
            "estimated_total": str(estimate.total),
            # COST-10/NFR-T1: the flag travels in the body, so a JSON consumer cannot lose it.
            "is_estimate": True,
            "rates_state": rates_state,
            "missing_rates": sorted(estimate.missing_rates),
            "declared_counters": [
                {
                    "deployment_id": s.key.deployment_id,
                    "agent_id": s.key.agent_id,
                    "name": s.counter.name,
                    "value": s.counter.value,
                    "state": s.counter.state.value,
                }
                for s in declared
            ],
        },
    )


def usage_quality(telemetry: SectionOutcome) -> dict[str, Any]:
    """US-21 + US-22: error rate, and the application-defined quality rates.

    Rates carry their numerator and denominator (TEL-06). Approval and success rates are
    application-semantic, so with no blueprint instrumented they report `not_instrumented` rather than
    a reassuring 0%.
    """
    if telemetry.state is not SectionState.OK or telemetry.payload is None:
        return _envelope(telemetry, None)
    series, aws_state = _counters_from(telemetry.payload, "aws")
    declared, declared_state = _counters_from(telemetry.payload, "declared")

    def _total(name: str, source: list[CounterSeries]) -> Counter:
        matching = [s for s in source if s.counter.name == name]
        if not matching:
            return Counter(name, 0.0, TelemetryState.NOT_INSTRUMENTED)
        if not any(s.counter.has_value for s in matching):
            return Counter(name, 0.0, matching[0].counter.state)
        return Counter(
            name, sum(s.counter.value for s in matching if s.counter.has_value), TelemetryState.OK
        )

    def _rate(numerator: str, denominator: str, source: list[CounterSeries]) -> dict[str, Any]:
        result = derive_rate(_total(numerator, source), _total(denominator, source))
        return {
            "rate": result.rate,
            "percent": result.percent,
            "numerator": result.numerator,
            "denominator": result.denominator,
            "state": result.state.value,
        }

    return _envelope(
        telemetry,
        {
            "aws_state": aws_state,
            "declared_state": declared_state,
            "not_instrumented": (telemetry.payload.get("declared", {}) or {}).get(
                "not_instrumented", []
            ),
            # From AWS-emitted metrics -- available with no instrumentation.
            "error_rate": _rate("InvocationClientErrors", "Invocations", series),
            # Application-semantic: no AWS metric has these concepts (FR-9.6).
            "timeout_rate": _rate("timeouts", "requests", declared),
            "approval_rate": _rate("approvals", "approval_requests", declared),
            "success_rate": _rate("prompt_successes", "prompt_attempts", declared),
        },
    )


def cost_per_completed_task(
    cost: SectionOutcome, telemetry: SectionOutcome
) -> dict[str, Any]:
    """US-19, folded into the summary response rather than given its own route.

    Needs both sections, so it reports the *worse* of the two states -- a per-task figure derived from
    half the data would be wrong in a way the number itself cannot show.
    """
    if cost.state is not SectionState.OK or telemetry.state is not SectionState.OK:
        worst = cost if cost.state is not SectionState.OK else telemetry
        return {"state": worst.state.value, "outcome": None, "amount": None}
    series, _ = _counters_from(telemetry.payload or {}, "declared")
    completed = int(
        sum(s.counter.value for s in _by_name(series, "completed_tasks") if s.counter.has_value)
    )
    totals = (cost.payload or {}).get("totals", {})
    try:
        month = Decimal(str(totals.get("month_to_date", "0")))
    except Exception:  # noqa: BLE001
        return {"state": SectionState.UNREADABLE.value, "outcome": None, "amount": None}
    result = cost_per_task(month, completed)
    return {
        "state": SectionState.OK.value,
        "outcome": result.outcome.value,
        "amount": None if result.amount is None else str(result.amount),
        "completed_tasks": completed,
        "cost_basis": "month_to_date_platform_cost",
    }
