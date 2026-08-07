"""Properties and examples for C-13 telemetry and C-14 catalog (TEL-01, 04, 06, 07; CAT-01..05).

The property that earns its keep here is **rate re-aggregation**: deriving a rate from summed
numerators and denominators equals the correctly weighted combination of the parts. That is the
formal reason TEL-06 refuses to store a pre-computed ratio -- averaging two percentages weights a
2-request agent the same as a 2,000-request one, and the resulting number looks entirely plausible.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dashboard.core import (
    Catalog,
    Counter,
    CounterKey,
    CounterSeries,
    MalformedCatalog,
    TelemetryState,
    aggregate_by_agent,
    counter_key,
    declared_counters,
    derive_rate,
    emits,
    parse_catalog,
    total_tokens_by_model,
)
from dashboard.core.catalog import CATALOG_SCHEMA_VERSION

DEPLOYMENTS = ["aidlc-main-teams-bot", "aidlc-main-dashboard", "aidlc-main-hello-world"]
counts = st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------------------------
# TEL-01 -- the agent dimension
# ---------------------------------------------------------------------------------------------


@given(deployment=st.sampled_from(DEPLOYMENTS))
def test_agent_id_defaults_to_deployment_id(deployment: str) -> None:
    """TEL-01. Every deployment today runs one agent, so this default is the common path."""
    assert counter_key(deployment).agent_id == deployment
    assert counter_key(deployment, None).agent_id == deployment
    assert counter_key(deployment, "").agent_id == deployment


@given(deployment=st.sampled_from(DEPLOYMENTS), agent=st.text(min_size=1, max_size=12))
def test_explicit_agent_id_is_kept(deployment: str, agent: str) -> None:
    """The multi-agent case is a change of values, not of schema."""
    assert counter_key(deployment, agent).agent_id == agent


def test_empty_deployment_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        counter_key("")


# ---------------------------------------------------------------------------------------------
# TEL-06 -- rate derivation
# ---------------------------------------------------------------------------------------------


@given(numerator=counts, denominator=st.floats(min_value=1, max_value=1_000_000))
def test_rate_keeps_its_numerator_and_denominator(numerator: float, denominator: float) -> None:
    """TEL-06: both counts survive, so the rate can be re-aggregated later."""
    result = derive_rate(Counter("errors", numerator), Counter("requests", denominator))
    assert result.numerator == numerator
    assert result.denominator == denominator
    assert result.rate == pytest.approx(numerator / denominator)


def test_zero_denominator_is_not_zero_percent() -> None:
    """TEL-04 applied to arithmetic: "no requests" is not "everything succeeded"."""
    result = derive_rate(Counter("errors", 0.0), Counter("requests", 0.0))
    assert result.rate is None
    assert result.state is TelemetryState.NO_DATA_YET
    assert result.percent is None


@pytest.mark.parametrize(
    "state",
    [TelemetryState.NOT_INSTRUMENTED, TelemetryState.CANNOT_READ, TelemetryState.NO_DATA_YET],
)
def test_absent_counter_yields_no_rate_and_keeps_the_reason(state: TelemetryState) -> None:
    """A rate over an unmeasured counter reports *why*, rather than inventing a value."""
    result = derive_rate(Counter("errors", 0.0, state), Counter("requests", 100.0))
    assert result.rate is None
    assert result.state is state


@given(data=st.data())
def test_rate_re_aggregation_is_weighted_correctly(data: st.DataObject) -> None:
    """The property that justifies TEL-06's refusal to store ratios.

    Deriving from summed counts equals the weighted combination of the parts -- and, notably, is NOT
    generally the arithmetic mean of the two rates, which is what storing ratios would produce.
    """
    n1 = data.draw(counts)
    d1 = data.draw(st.floats(min_value=1, max_value=1_000_000))
    n2 = data.draw(counts)
    d2 = data.draw(st.floats(min_value=1, max_value=1_000_000))
    combined = derive_rate(Counter("errors", n1 + n2), Counter("requests", d1 + d2))
    expected = (n1 + n2) / (d1 + d2)
    assert combined.rate == pytest.approx(expected)


# ---------------------------------------------------------------------------------------------
# TEL-07 -- per-agent aggregation
# ---------------------------------------------------------------------------------------------


def test_agents_within_a_deployment_sum_to_the_deployment_total() -> None:
    """US-23.3. Two agents in one deployment, three models between them."""
    series = [
        CounterSeries(counter_key("dep-1", "agent-a", "nova-lite"), Counter("requests", 10.0)),
        CounterSeries(counter_key("dep-1", "agent-a", "nova-pro"), Counter("requests", 5.0)),
        CounterSeries(counter_key("dep-1", "agent-b", "nova-lite"), Counter("requests", 7.0)),
    ]
    totals = aggregate_by_agent(series)
    assert totals[CounterKey("dep-1", "agent-a")] == 15.0
    assert totals[CounterKey("dep-1", "agent-b")] == 7.0
    assert sum(totals.values()) == 22.0


def test_unmeasured_counters_are_not_summed_as_zero() -> None:
    """Including them would make "unmeasured" and "measured as nothing" add up identically."""
    series = [
        CounterSeries(counter_key("dep-1", "a"), Counter("requests", 10.0)),
        CounterSeries(
            counter_key("dep-1", "b"), Counter("requests", 0.0, TelemetryState.NOT_INSTRUMENTED)
        ),
    ]
    totals = aggregate_by_agent(series)
    assert CounterKey("dep-1", "b") not in totals
    assert totals[CounterKey("dep-1", "a")] == 10.0


def test_token_totals_ignore_series_with_no_model() -> None:
    """A token count with no model cannot be priced, and guessing a model would fabricate money."""
    totals = total_tokens_by_model(
        [
            CounterSeries(counter_key("d", "a", "nova-lite"), Counter("in", 100.0)),
            CounterSeries(counter_key("d", "a", None), Counter("in", 999.0)),
        ],
        [CounterSeries(counter_key("d", "a", "nova-lite"), Counter("out", 40.0))],
    )
    assert totals == {"nova-lite": (100, 40)}


# ---------------------------------------------------------------------------------------------
# CAT -- the catalog
# ---------------------------------------------------------------------------------------------


def _catalog_json(blueprints: dict[str, object]) -> str:
    return json.dumps({"schema_version": CATALOG_SCHEMA_VERSION, "blueprints": blueprints})


def test_blueprint_with_no_telemetry_block_does_not_emit() -> None:
    """CAT-01: absence is a declaration, not an error and not unknown."""
    catalog = parse_catalog(_catalog_json({"hello-world": {"emits": False}}))
    assert emits(catalog, "hello-world") is False
    assert declared_counters(catalog, "hello-world") == ()


def test_absent_blueprint_declares_nothing() -> None:
    """CAT-05: not in the catalog at all is distinct from declared-with-no-data."""
    catalog = parse_catalog(_catalog_json({}))
    assert emits(catalog, "teams-bot") is False
    assert declared_counters(catalog, "teams-bot") == ()


def test_declared_counters_carry_unit_and_description() -> None:
    """CAT-03: the UI renders generically from these, so a new emitter needs no dashboard change."""
    catalog = parse_catalog(
        _catalog_json(
            {
                "teams-bot": {
                    "emits": True,
                    "namespace": "Cornell/Blueprints/teams-bot",
                    "counters": [
                        {"name": "queries_answered", "unit": "Count", "description": "queries served"}
                    ],
                }
            }
        )
    )
    assert emits(catalog, "teams-bot") is True
    (counter,) = declared_counters(catalog, "teams-bot")
    assert (counter.name, counter.unit, counter.description) == (
        "queries_answered",
        "Count",
        "queries served",
    )
    assert catalog.emitting_blueprints == ("teams-bot",)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"blueprints": {}}',  # no schema_version
        '{"schema_version": "wrong", "blueprints": {}}',
        _catalog_json({"b": {"emits": True}}),  # emitting with no namespace
        _catalog_json({"b": {"emits": True, "namespace": "N"}}),  # no counters
        _catalog_json({"b": {"emits": True, "namespace": "N", "counters": []}}),  # empty counters
        _catalog_json({"b": {"emits": True, "namespace": "N", "counters": [{"name": "x"}]}}),
        _catalog_json(
            {"b": {"emits": True, "namespace": "N", "counters": [{"name": "", "unit": "Count", "description": "d"}]}}
        ),
    ],
)
def test_malformed_catalog_raises(raw: str) -> None:
    """CAT-02's runtime half: a broken catalog must not degrade to "nobody emits"."""
    with pytest.raises(MalformedCatalog):
        parse_catalog(raw)


def test_catalog_round_trips_through_the_parser() -> None:
    payload = _catalog_json(
        {
            "teams-bot": {
                "emits": True,
                "namespace": "Cornell/Blueprints/teams-bot",
                "counters": [{"name": "q", "unit": "Count", "description": "d"}],
            },
            "hello-world": {"emits": False},
        }
    )
    assert parse_catalog(payload) == parse_catalog(payload)
    assert isinstance(parse_catalog(payload), Catalog)


def test_catalog_names_the_blueprints_that_are_not_instrumented() -> None:
    """FR-9.7.3: the empty state must NAME which blueprints report nothing, not render blank.

    Regression test for a real bug in the first draft of this increment: `parse_catalog` dropped
    non-emitting blueprints entirely, so `not_instrumented` was always empty and the UI would have
    shown an unexplained blank panel instead of "these blueprints report nothing".
    """
    catalog = parse_catalog(
        _catalog_json(
            {
                "hello-world": {"emits": False},
                "notify-topic": {"emits": False},
                "teams-bot": {
                    "emits": True,
                    "namespace": "Cornell/Blueprints/teams-bot",
                    "counters": [{"name": "q", "unit": "Count", "description": "d"}],
                },
            }
        )
    )
    assert catalog.emitting_blueprints == ("teams-bot",)
    assert catalog.not_instrumented == ("hello-world", "notify-topic")
    assert set(catalog.known) == {"hello-world", "notify-topic", "teams-bot"}


def test_all_non_emitting_is_the_expected_state_today() -> None:
    """The state the real generated catalog is in: every blueprint declared, none emitting."""
    catalog = parse_catalog(
        _catalog_json({name: {"emits": False} for name in ("a", "b", "c")})
    )
    assert catalog.emitting_blueprints == ()
    assert catalog.not_instrumented == ("a", "b", "c")
