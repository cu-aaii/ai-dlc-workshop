"""Money: cost records, the token x rate estimate, and the attribution predicate (C-12).

Pure by contract, like the rest of `dashboard.core`: no AWS SDK, no environment read, no clock, no
logging. `tools/check`'s boundary grep enforces it.

**Every monetary value in here is `Decimal`, never `float`** (COST-01). Cost Explorer returns amounts
as decimal *strings* (`"9.0231738003"`); `float("0.1") + float("0.2") != float("0.3")`, and these are
figures a person reads and then spends against. `decimal` is stdlib, so this costs U-01 no dependency.

Two things in this module carry more weight than their size suggests:

- **`is_unattributed`** is the entire defence against a measured trap (amendment A3.3). Cost Explorer
  answers a tag-grouped query with HTTP 200 and a group keyed ``"cornell:blueprint$"`` -- the key with
  an *empty value component* -- holding 100% of spend when the tag was never activated for cost
  allocation. A reader that trusts the response shape renders that as a blueprint literally named
  ``cornell:blueprint`` costing the account total: one confident, wrong attribution, and no error to
  catch. The predicate is a one-liner on purpose, so it is trivially reviewable and property-testable.
- **`missing_rates`** exists so a model with usage but no configured price is *reported*, never priced
  at zero (COST-09). A silent zero is the same class of lie as the trap above.

Rules COST-01, COST-02, COST-03, COST-08, COST-09, COST-10, COST-11, COST-12, COST-14 live in
`aidlc-docs/construction/fr9-fr10/functional-design/business-rules.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from dashboard.core.errors import CoreError

__all__ = [
    "AttributionSplit",
    "CostGroup",
    "CostEstimate",
    "MalformedRateTable",
    "ModelRate",
    "ModelUsage",
    "PerTaskOutcome",
    "PerTaskResult",
    "RateTable",
    "cost_per_task",
    "estimate_model_cost",
    "is_unattributed",
    "parse_amount",
    "parse_rate_table",
    "split_attribution",
]

# Cost Explorer encodes a tag group as "<key>$<value>". An empty value component means the resource
# carried no value for that tag as far as cost allocation is concerned -- i.e. unattributed.
_TAG_GROUP_SEPARATOR = "$"


class MalformedRateTable(CoreError):
    """The rate table could not be parsed.

    Carries no fragment of the input: a rate table is configuration, but this exception can reach a
    log group or an HTTP body, and NFR-S1's rule is structural -- no message here carries data.
    """


class PerTaskOutcome(StrEnum):
    """Why a per-task figure is or is not available (COST-12).

    Closed enum rather than free text, matching `SkipReason`'s reasoning: these values become response
    fields, and a typo in a string literal is a silent behaviour change.
    """

    OK = "ok"
    NO_TASKS = "no_tasks"
    NO_COST = "no_cost"


def parse_amount(raw: str) -> Decimal:
    """Parse an upstream decimal *string* into `Decimal` (COST-01).

    Rejects anything that is not a finite decimal. `float` never appears -- passing through `float`
    would round before the value is ever used.
    """
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MalformedRateTable("amount is not a decimal") from exc
    if not amount.is_finite():
        raise MalformedRateTable("amount is not finite")
    return amount


@dataclass(frozen=True, eq=True, slots=True)
class ModelRate:
    """Price for one model, per `per_unit` tokens.

    `per_unit` is explicit and required. Vendors quote per 1,000 or per 1,000,000 tokens depending on
    the model, so assuming either is how a 1000x error enters a figure that still looks plausible.
    """

    input_price: Decimal
    output_price: Decimal
    per_unit: int

    def __post_init__(self) -> None:
        if self.per_unit <= 0:
            raise MalformedRateTable("per_unit must be positive")
        if self.input_price < 0 or self.output_price < 0:
            raise MalformedRateTable("prices must not be negative")


@dataclass(frozen=True, eq=True)
class RateTable:
    """Per-model prices. An empty table is valid and means every model reports a missing rate.

    Deliberately empty on delivery: the per-model rates were the one FR-10.8 item that could not be
    verified (pricing-page data, not account data), and shipping a guessed rate would produce
    confident wrong money. Empty is honest; a default is not.
    """

    rates: Mapping[str, ModelRate] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rates", MappingProxyType(dict(self.rates)))

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.rates.items(), key=lambda kv: kv[0])))

    def get(self, model: str) -> ModelRate | None:
        return self.rates.get(model)


def parse_rate_table(raw: str | bytes) -> RateTable:
    """Parse the configured rate table (COST-14).

    A malformed table raises rather than degrading to empty: silently treating "the operator wrote
    broken JSON" as "no rates are configured" hides a fixable mistake behind a plausible state.
    """
    try:
        payload: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedRateTable("rate table is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise MalformedRateTable("rate table must be a JSON object")

    rates: dict[str, ModelRate] = {}
    for model, entry in payload.items():
        if not isinstance(model, str) or not model:
            raise MalformedRateTable("model id must be a non-empty string")
        if not isinstance(entry, dict):
            raise MalformedRateTable("rate entry must be an object")
        missing = {"input", "output", "per_unit"} - set(entry)
        if missing:
            raise MalformedRateTable("rate entry is missing required fields")
        per_unit = entry["per_unit"]
        if not isinstance(per_unit, int) or isinstance(per_unit, bool):
            raise MalformedRateTable("per_unit must be an integer")
        rates[model] = ModelRate(
            input_price=parse_amount(str(entry["input"])),
            output_price=parse_amount(str(entry["output"])),
            per_unit=per_unit,
        )
    return RateTable(rates=rates)


@dataclass(frozen=True, eq=True, slots=True)
class _Tokens:
    """Input and output token counts for one model."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, eq=True)
class ModelUsage:
    """Token counts per model, as collected from CloudWatch."""

    tokens: Mapping[str, _Tokens] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tokens", MappingProxyType(dict(self.tokens)))

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.tokens.items(), key=lambda kv: kv[0])))

    @classmethod
    def of(cls, counts: Mapping[str, tuple[int, int]]) -> ModelUsage:
        """Build from `{model: (input_tokens, output_tokens)}` -- the shape the collector holds."""
        return cls(tokens={m: _Tokens(i, o) for m, (i, o) in counts.items()})


@dataclass(frozen=True, eq=True)
class CostEstimate:
    """An estimated cost, per model, with the models whose rate was missing.

    `is_estimate` is carried **in the record**, not applied by the UI (COST-10). It survives
    serialization, so a JSON consumer cannot lose the distinction between an estimate derived from
    token counts and a figure the provider billed. Presenting the first as the second is exactly the
    fabrication SECURITY-15 forbids.
    """

    per_model: Mapping[str, Decimal] = field(default_factory=dict)
    missing_rates: frozenset[str] = frozenset()
    is_estimate: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_model", MappingProxyType(dict(self.per_model)))

    def __hash__(self) -> int:
        return hash(
            (
                tuple(sorted(self.per_model.items(), key=lambda kv: kv[0])),
                self.missing_rates,
                self.is_estimate,
            )
        )

    @property
    def total(self) -> Decimal:
        """Total across priced models. Models in `missing_rates` contribute nothing (COST-09)."""
        return sum(self.per_model.values(), Decimal(0))


def estimate_model_cost(usage: ModelUsage, rates: RateTable) -> CostEstimate:
    """Estimate model cost as tokens x rate (COST-09, COST-10).

    A model with usage but no configured rate goes to `missing_rates` and is priced nowhere -- not at
    zero, and not omitted from the report. The caller surfaces it; this function never guesses.
    """
    priced: dict[str, Decimal] = {}
    missing: set[str] = set()
    for model, tokens in usage.tokens.items():
        rate = rates.get(model)
        if rate is None:
            missing.add(model)
            continue
        unit = Decimal(rate.per_unit)
        priced[model] = (Decimal(tokens.input_tokens) / unit) * rate.input_price + (
            Decimal(tokens.output_tokens) / unit
        ) * rate.output_price
    return CostEstimate(
        per_model=priced, missing_rates=frozenset(missing), is_estimate=True
    )


def is_unattributed(group_key: str) -> bool:
    """True when a Cost Explorer tag group key has an empty value component (COST-02).

    ``"cornell:blueprint$"`` -> True (no tag value: unattributed spend)
    ``"cornell:blueprint$dashboard"`` -> False (attributed to `dashboard`)

    This is the whole defence against amendment A3.3's measured trap. See the module docstring.
    """
    key, separator, value = group_key.partition(_TAG_GROUP_SEPARATOR)
    if not separator:
        # No separator at all: not a tag grouping key, so not the unattributed bucket.
        return False
    return value == ""


@dataclass(frozen=True, eq=True, slots=True)
class CostGroup:
    """One grouped cost figure as returned upstream."""

    key: str
    amount: Decimal


@dataclass(frozen=True, eq=True)
class AttributionSplit:
    """Attributed groups, and the unattributed remainder (COST-02, COST-03).

    The accounting identity `sum(attributed) + unattributed == total` is a property test, mirroring
    how U-01 already guards resource counts under grouping: a split that loses or double-counts money
    is worse than one that fails.
    """

    attributed: tuple[CostGroup, ...] = ()
    unattributed: Decimal = Decimal(0)

    @property
    def attributed_total(self) -> Decimal:
        return sum((g.amount for g in self.attributed), Decimal(0))

    @property
    def total(self) -> Decimal:
        return self.attributed_total + self.unattributed

    @property
    def fully_unattributed(self) -> bool:
        """True when no spend is attributable (COST-03).

        The caller renders "attribution unavailable" rather than a one-group breakdown. Note this is
        False for an empty input -- no data is not the same claim as no attribution.
        """
        return bool(self.unattributed) and not self.attributed


def split_attribution(groups: tuple[CostGroup, ...]) -> AttributionSplit:
    """Partition tag groups into attributed and unattributed (COST-02).

    Every input group lands in exactly one side; nothing is dropped and nothing is counted twice.
    """
    attributed = tuple(g for g in groups if not is_unattributed(g.key))
    unattributed = sum(
        (g.amount for g in groups if is_unattributed(g.key)), Decimal(0)
    )
    return AttributionSplit(attributed=attributed, unattributed=unattributed)


@dataclass(frozen=True, eq=True, slots=True)
class PerTaskResult:
    """Cost per completed task, or why there isn't one (COST-12)."""

    outcome: PerTaskOutcome
    amount: Decimal | None = None


def cost_per_task(cost: Decimal, completed_tasks: int) -> PerTaskResult:
    """Cost divided by completed tasks (COST-12).

    Zero completed tasks returns `NO_TASKS`, never a division and never zero. "No tasks completed" and
    "each task cost nothing" are different claims, and only one of them is ever true here.
    """
    if completed_tasks < 0:
        raise MalformedRateTable("completed task count must not be negative")
    if completed_tasks == 0:
        return PerTaskResult(outcome=PerTaskOutcome.NO_TASKS)
    if cost == 0:
        return PerTaskResult(outcome=PerTaskOutcome.NO_COST, amount=Decimal(0))
    return PerTaskResult(
        outcome=PerTaskOutcome.OK, amount=cost / Decimal(completed_tasks)
    )
