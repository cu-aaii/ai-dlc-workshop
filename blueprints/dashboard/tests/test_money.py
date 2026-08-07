"""Properties and examples for C-12 money (COST-01..03, 08..12, 14).

**Why these are property tests and the collectors' are not.** This module is the one place in the
FR-9/FR-10 increment where a silent error produces a *wrong number a person spends money against*.
That is the whole argument for putting C-12 in U-01: it is pure, so these run with no AWS, no mocks,
and no stubs -- and a property test over a stubbed AWS client would only be testing the stub.

The two highest-value properties here:

- **Additivity.** `estimate(a) + estimate(b) == estimate(a merged with b)`. This is what makes
  per-agent and per-window totals trustworthy; without it, a breakdown could disagree with its own
  total and nothing would notice.
- **Attribution partition.** attributed + unattributed == input total, always. Money that vanishes
  from a split, or is counted twice, is exactly the failure mode amendment A3.3 measured in the wild.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dashboard.core import (
    CostGroup,
    MalformedRateTable,
    ModelRate,
    ModelUsage,
    PerTaskOutcome,
    RateTable,
    cost_per_task,
    estimate_model_cost,
    is_unattributed,
    parse_amount,
    parse_rate_table,
    split_attribution,
)

MODELS = ["nova-lite", "nova-pro", "claude-haiku-4-5", "titan-embed-v2"]

token_counts = st.integers(min_value=0, max_value=10_000_000)
prices = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("100"), places=6, allow_nan=False, allow_infinity=False
)


@st.composite
def rate_tables(draw: st.DrawFn, models: list[str] | None = None) -> RateTable:
    pool = models if models is not None else draw(st.lists(st.sampled_from(MODELS), unique=True))
    return RateTable(
        rates={
            m: ModelRate(
                input_price=draw(prices),
                output_price=draw(prices),
                per_unit=draw(st.sampled_from([1_000, 1_000_000])),
            )
            for m in pool
        }
    )


@st.composite
def usages(draw: st.DrawFn, models: list[str] | None = None) -> ModelUsage:
    pool = models if models is not None else draw(st.lists(st.sampled_from(MODELS), unique=True))
    return ModelUsage.of({m: (draw(token_counts), draw(token_counts)) for m in pool})


# ---------------------------------------------------------------------------------------------
# Estimation properties
# ---------------------------------------------------------------------------------------------


@given(rates=rate_tables())
def test_zero_tokens_cost_nothing(rates: RateTable) -> None:
    """Zero usage is free, for every rate table. The base case a rounding bug breaks first."""
    usage = ModelUsage.of({m: (0, 0) for m in rates.rates})
    estimate = estimate_model_cost(usage, rates)
    assert estimate.total == Decimal(0)
    assert not estimate.missing_rates


@given(data=st.data())
def test_estimate_is_monotonic_in_tokens(data: st.DataObject) -> None:
    """More tokens never cost less."""
    models = ["nova-lite"]
    rates = data.draw(rate_tables(models=models))
    low_in, low_out = data.draw(token_counts), data.draw(token_counts)
    extra_in, extra_out = data.draw(token_counts), data.draw(token_counts)
    low = estimate_model_cost(ModelUsage.of({"nova-lite": (low_in, low_out)}), rates)
    high = estimate_model_cost(
        ModelUsage.of({"nova-lite": (low_in + extra_in, low_out + extra_out)}), rates
    )
    assert high.total >= low.total


@given(data=st.data())
def test_estimate_is_additive_across_models(data: st.DataObject) -> None:
    """estimate(a) + estimate(b) == estimate(a+b), per model.

    The property that makes a per-agent or per-window breakdown agree with its own total.
    """
    rates = data.draw(rate_tables(models=MODELS))
    left = data.draw(usages(models=["nova-lite", "nova-pro"]))
    right = data.draw(usages(models=["nova-lite", "claude-haiku-4-5"]))
    merged_counts: dict[str, tuple[int, int]] = {}
    for usage in (left, right):
        for model, tokens in usage.tokens.items():
            prev = merged_counts.get(model, (0, 0))
            merged_counts[model] = (
                prev[0] + tokens.input_tokens,
                prev[1] + tokens.output_tokens,
            )
    merged = estimate_model_cost(ModelUsage.of(merged_counts), rates)
    separate = estimate_model_cost(left, rates).total + estimate_model_cost(right, rates).total
    assert merged.total == separate


@given(data=st.data())
def test_missing_rate_contributes_nothing_and_is_reported(data: st.DataObject) -> None:
    """COST-09: a model with usage but no rate is reported, never priced at zero, never dropped."""
    rates = data.draw(rate_tables(models=["nova-lite"]))
    usage = data.draw(usages(models=["nova-lite", "unpriced-model"]))
    estimate = estimate_model_cost(usage, rates)
    assert "unpriced-model" in estimate.missing_rates
    assert "unpriced-model" not in estimate.per_model
    # And the total is exactly the priced model's contribution -- nothing implicit was added.
    priced_only = estimate_model_cost(
        ModelUsage.of({"nova-lite": (
            usage.tokens["nova-lite"].input_tokens,
            usage.tokens["nova-lite"].output_tokens,
        )}),
        rates,
    )
    assert estimate.total == priced_only.total


@given(usage=usages(), rates=rate_tables())
def test_every_monetary_value_is_decimal(usage: ModelUsage, rates: RateTable) -> None:
    """COST-01: no float reaches a money field. A float here would round silently."""
    estimate = estimate_model_cost(usage, rates)
    assert all(isinstance(v, Decimal) for v in estimate.per_model.values())
    assert isinstance(estimate.total, Decimal)


@given(usage=usages(), rates=rate_tables())
def test_estimate_flag_is_always_set(usage: ModelUsage, rates: RateTable) -> None:
    """COST-10: an estimate is marked as one in the record, not only in the UI."""
    assert estimate_model_cost(usage, rates).is_estimate is True


# ---------------------------------------------------------------------------------------------
# Attribution properties -- the defence against the A3.3 trap
# ---------------------------------------------------------------------------------------------

amounts = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("10000"), places=4, allow_nan=False, allow_infinity=False
)


@st.composite
def cost_groups(draw: st.DrawFn) -> tuple[CostGroup, ...]:
    keys = draw(
        st.lists(
            st.one_of(
                st.just("cornell:blueprint$"),  # the unattributed bucket
                st.sampled_from(
                    ["cornell:blueprint$dashboard", "cornell:blueprint$teams-bot", "cornell:owner$abc123"]
                ),
            ),
            min_size=0,
            max_size=6,
        )
    )
    return tuple(CostGroup(key=k, amount=draw(amounts)) for k in keys)


@given(groups=cost_groups())
def test_attribution_partitions_and_preserves_the_total(groups: tuple[CostGroup, ...]) -> None:
    """The accounting identity: nothing is dropped, nothing is double-counted."""
    split = split_attribution(groups)
    assert split.total == sum((g.amount for g in groups), Decimal(0))
    assert len(split.attributed) == sum(1 for g in groups if not is_unattributed(g.key))


@given(key=st.text(min_size=1, max_size=20).filter(lambda s: "$" not in s), value=st.text(min_size=1, max_size=10))
def test_empty_value_component_is_unattributed(key: str, value: str) -> None:
    """`k$` is unattributed; `k$v` is attributed. The one-line rule, checked for all inputs."""
    assert is_unattributed(f"{key}$") is True
    assert is_unattributed(f"{key}${value}") is False


def test_the_measured_trap_specifically() -> None:
    """Regression test for the exact response amendment A3.3 measured against the real account.

    `get-cost-and-usage --group-by Type=TAG,Key=cornell:blueprint` returned HTTP 200 with a single
    group keyed `cornell:blueprint$` holding the entire $9.02. A reader that trusts the response shape
    renders a blueprint named `cornell:blueprint` costing the account total.
    """
    split = split_attribution((CostGroup(key="cornell:blueprint$", amount=Decimal("9.0231738003")),))
    assert split.attributed == ()
    assert split.unattributed == Decimal("9.0231738003")
    assert split.fully_unattributed is True


def test_no_groups_is_not_fully_unattributed() -> None:
    """No data is not the same claim as no attribution -- COST-03 must not fire on an empty input."""
    assert split_attribution(()).fully_unattributed is False


# ---------------------------------------------------------------------------------------------
# Rate table parsing and per-task
# ---------------------------------------------------------------------------------------------


def test_empty_rate_table_is_valid() -> None:
    """The table ships empty on purpose: a guessed rate is confident wrong money."""
    assert parse_rate_table("{}").rates == {}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"m": "not an object"}',
        '{"m": {"input": "1"}}',  # missing output/per_unit
        '{"m": {"input": "1", "output": "1", "per_unit": "1000"}}',  # per_unit not an int
        '{"m": {"input": "1", "output": "1", "per_unit": 0}}',  # non-positive
        '{"m": {"input": "-1", "output": "1", "per_unit": 1000}}',  # negative price
        '{"": {"input": "1", "output": "1", "per_unit": 1000}}',  # empty model id
    ],
)
def test_malformed_rate_table_raises(raw: str) -> None:
    """COST-14: malformed config raises rather than degrading to "no rates configured"."""
    with pytest.raises(MalformedRateTable):
        parse_rate_table(raw)


def test_parse_amount_rejects_non_decimal() -> None:
    with pytest.raises(MalformedRateTable):
        parse_amount("nine dollars")


def test_parse_amount_keeps_full_precision() -> None:
    """The upstream string is preserved exactly -- no float narrowing on the way in."""
    assert parse_amount("9.0231738003") == Decimal("9.0231738003")


@given(cost=amounts, tasks=st.integers(min_value=1, max_value=10_000))
def test_cost_per_task_divides(cost: Decimal, tasks: int) -> None:
    result = cost_per_task(cost, tasks)
    if cost == 0:
        assert result.outcome is PerTaskOutcome.NO_COST
    else:
        assert result.outcome is PerTaskOutcome.OK
        assert result.amount == cost / Decimal(tasks)


def test_cost_per_task_with_no_tasks_is_not_zero() -> None:
    """COST-12: "no tasks completed" and "each task was free" are different claims."""
    result = cost_per_task(Decimal("5.00"), 0)
    assert result.outcome is PerTaskOutcome.NO_TASKS
    assert result.amount is None
