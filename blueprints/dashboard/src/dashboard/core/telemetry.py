"""Telemetry: counter records, per-agent keying, and rate derivation (C-13).

Pure, like the rest of `dashboard.core`. The clock is passed in, never read.

Three decisions in here are load-bearing:

- **`agent_id` defaults to `deployment_id`** (TEL-01). Applied once, in `counter_key`, so no reader can
  forget it. A deployment running one agent -- every deployment that exists today -- needs no extra
  configuration, and a deployment running several attributes correctly without a schema migration.
  That is why the dimension exists now rather than being added when multi-agent arrives.
- **Rates keep their numerator and denominator** (TEL-06). A stored ratio cannot be re-aggregated: 50%
  of 2 requests and 50% of 2,000 are not the same fact, and averaging two percentages across agents or
  time windows silently weights them equally. So `RateResult` carries the counts it came from.
- **A rate with no denominator is `None` with a state, not `0.0`** (TEL-04). "No requests, so no error
  rate" and "every request succeeded" are different claims; rendering the first as 0% is a lie the UI
  cannot detect.

Rules TEL-01, TEL-04, TEL-06, TEL-07, TEL-08 live in
`aidlc-docs/construction/fr9-fr10/functional-design/business-rules.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

__all__ = [
    "Counter",
    "CounterKey",
    "CounterSeries",
    "RateResult",
    "TelemetryState",
    "aggregate_by_agent",
    "counter_key",
    "derive_rate",
    "total_tokens_by_model",
]


class TelemetryState(StrEnum):
    """Why a counter has, or does not have, a value (TEL-04, NFR-T7).

    Four states that must never collapse into each other. The distinction is the deliverable: with no
    blueprint instrumented, most counters are `NOT_INSTRUMENTED`, and showing that as `0` would claim
    an application is unused when in fact it is unmeasured.

    - `OK`             -- declared, read, and has datapoints
    - `NO_DATA_YET`    -- declared and read, but no datapoints in the window
    - `NOT_INSTRUMENTED` -- no blueprint declares this counter at all
    - `CANNOT_READ`    -- the metrics read itself failed
    """

    OK = "ok"
    NO_DATA_YET = "no_data_yet"
    NOT_INSTRUMENTED = "not_instrumented"
    CANNOT_READ = "cannot_read"


@dataclass(frozen=True, eq=True, slots=True, order=True)
class CounterKey:
    """Identity of a measurement: which deployment, which agent within it, and which model.

    Ordered so aggregation output is deterministic -- a property test comparing two aggregations must
    not fail on dict ordering.
    """

    deployment_id: str
    agent_id: str
    model: str | None = None


def counter_key(
    deployment_id: str, agent_id: str | None = None, model: str | None = None
) -> CounterKey:
    """Build a counter key, defaulting `agent_id` to `deployment_id` (TEL-01).

    The default lives here and nowhere else. Every collector and every view goes through this
    function, so a deployment that never heard of agents still attributes correctly, and the
    multi-agent case is a change of *values* rather than of schema.
    """
    if not deployment_id:
        raise ValueError("deployment_id must not be empty")
    return CounterKey(
        deployment_id=deployment_id,
        agent_id=agent_id if agent_id else deployment_id,
        model=model,
    )


@dataclass(frozen=True, eq=True, slots=True)
class Counter:
    """One counter's value, and whether it means anything (TEL-04)."""

    name: str
    value: float
    state: TelemetryState = TelemetryState.OK

    @property
    def has_value(self) -> bool:
        return self.state is TelemetryState.OK


@dataclass(frozen=True, eq=True, slots=True)
class CounterSeries:
    """A counter attributed to one key."""

    key: CounterKey
    counter: Counter


@dataclass(frozen=True, eq=True, slots=True)
class RateResult:
    """A derived rate, with the counts behind it (TEL-06).

    `rate is None` means the rate is not defined for this window -- read `state` for why. The caller
    must not substitute zero.
    """

    rate: float | None
    numerator: float
    denominator: float
    state: TelemetryState

    @property
    def percent(self) -> float | None:
        return None if self.rate is None else self.rate * 100.0


def derive_rate(numerator: Counter, denominator: Counter) -> RateResult:
    """Derive a rate from two counters, keeping both (TEL-06).

    A zero or absent denominator yields `rate=None`, never a division and never an implied 0%.
    """
    if not denominator.has_value or not numerator.has_value:
        worst = (
            TelemetryState.CANNOT_READ
            if TelemetryState.CANNOT_READ
            in (numerator.state, denominator.state)
            else TelemetryState.NOT_INSTRUMENTED
            if TelemetryState.NOT_INSTRUMENTED
            in (numerator.state, denominator.state)
            else TelemetryState.NO_DATA_YET
        )
        return RateResult(rate=None, numerator=0.0, denominator=0.0, state=worst)
    if denominator.value == 0:
        return RateResult(
            rate=None,
            numerator=numerator.value,
            denominator=0.0,
            state=TelemetryState.NO_DATA_YET,
        )
    return RateResult(
        rate=numerator.value / denominator.value,
        numerator=numerator.value,
        denominator=denominator.value,
        state=TelemetryState.OK,
    )


def aggregate_by_agent(series: Iterable[CounterSeries]) -> Mapping[CounterKey, float]:
    """Sum counter values per (deployment, agent), dropping the model dimension (TEL-07).

    Per-agent totals within a deployment sum to that deployment's total -- the invariant US-23 asks
    for, and a property test here rather than an assertion in a view.

    Counters without a value are skipped rather than counted as zero: including them would make
    "unmeasured" and "measured as nothing" add up the same way.
    """
    totals: dict[CounterKey, float] = {}
    for item in series:
        if not item.counter.has_value:
            continue
        collapsed = CounterKey(
            deployment_id=item.key.deployment_id, agent_id=item.key.agent_id, model=None
        )
        totals[collapsed] = totals.get(collapsed, 0.0) + item.counter.value
    return totals


def total_tokens_by_model(
    input_series: Iterable[CounterSeries], output_series: Iterable[CounterSeries]
) -> Mapping[str, tuple[int, int]]:
    """Total input/output tokens per model, in the shape `ModelUsage.of` accepts.

    The bridge from collected telemetry to the cost estimate (COST-09). Series entries with no model
    dimension are ignored -- a token count that cannot be attributed to a model cannot be priced, and
    guessing which model it belonged to would fabricate money.
    """
    totals: dict[str, list[int]] = {}
    for series, index in ((input_series, 0), (output_series, 1)):
        for item in series:
            if item.key.model is None or not item.counter.has_value:
                continue
            slot = totals.setdefault(item.key.model, [0, 0])
            slot[index] += int(item.counter.value)
    return {model: (counts[0], counts[1]) for model, counts in totals.items()}
