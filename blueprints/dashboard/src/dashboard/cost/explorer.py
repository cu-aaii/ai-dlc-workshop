"""Cost Explorer reads, and the classification that makes them safe (COST-02..08).

The single most important function here is `to_groups`, and the reason is a measured one. Cost
Explorer answers a tag-grouped query with **HTTP 200** even when the tag was never activated for cost
allocation -- returning one group whose key is `"cornell:blueprint$"`, the key with an *empty value
component*, holding 100% of spend. There is no error to catch. A reader that trusts the response shape
renders a blueprint literally named `cornell:blueprint` costing the account total.

So every grouped amount goes through `dashboard.core.split_attribution`, which partitions on that
predicate. The classification is not a presentation concern; it happens before the data is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from dashboard.core import CostGroup, parse_amount
from dashboard.cost.errors import CostFailure, CostReason

_METRIC = "UnblendedCost"

_ACCESS_DENIED_CODES = frozenset(
    {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}
)
_THROTTLE_CODES = frozenset(
    {"ThrottlingException", "Throttling", "RequestLimitExceeded", "LimitExceededException"}
)


@dataclass(frozen=True)
class CallBudget:
    """Counts Cost Explorer calls and refuses to exceed the budget (COST-05).

    **Exceeding the budget is a failure, not a cap.** Truncating would return a *smaller* cost figure
    that looks entirely valid -- the money-domain version of silently stopping at page 1, which CR-01
    already refuses for inventory. Under-reported spend is worse, because someone may act on it.
    """

    limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "_used", 0)

    @property
    def used(self) -> int:
        return int(getattr(self, "_used"))

    def spend(self) -> None:
        used = self.used + 1
        if used > self.limit:
            raise CostFailure(CostReason.CALL_BUDGET_EXCEEDED)
        object.__setattr__(self, "_used", used)


def classify_client_error(exc: Exception) -> CostReason:
    """Map an SDK exception to a reason, keeping `ACCESS_DENIED` distinct (see `errors.py`)."""
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in _ACCESS_DENIED_CODES:
            return CostReason.ACCESS_DENIED
        if code in _THROTTLE_CODES:
            return CostReason.UPSTREAM_THROTTLED
    return CostReason.UPSTREAM_UNAVAILABLE


def to_groups(raw_groups: list[dict[str, Any]]) -> tuple[CostGroup, ...]:
    """Convert Cost Explorer groups to `CostGroup`, parsing amounts as `Decimal` (COST-01).

    A group with several keys (a two-dimension grouping) is joined with `|` rather than dropped --
    losing a group would break the accounting identity the split then asserts.
    """
    groups: list[CostGroup] = []
    for group in raw_groups:
        keys = group.get("Keys") or []
        amount_raw = (
            group.get("Metrics", {}).get(_METRIC, {}).get("Amount", "0")
        )
        groups.append(
            CostGroup(key="|".join(str(k) for k in keys), amount=parse_amount(str(amount_raw)))
        )
    return tuple(groups)


def month_to_date(today: date) -> tuple[date, date]:
    return today.replace(day=1), today + timedelta(days=1)


def year_to_date(today: date) -> tuple[date, date]:
    return today.replace(month=1, day=1), today + timedelta(days=1)


def last_finalized_day(today: date, lag_days: int = 2) -> tuple[date, date]:
    """The window for the "today" figure (COST-04).

    Cost Explorer lags 24-48h, so the most recent *finalized* day is not today. This returns the day
    actually being reported, and the caller stores it as `covered_through` -- a separate field from
    `collected_at`. One says when we asked; the other says what the answer covers. Collapsing them is
    the mistake US-16 exists to prevent.
    """
    end = today - timedelta(days=lag_days - 1)
    return end - timedelta(days=1), end


def fetch_grouped(
    ce_client: Any,
    start: date,
    end: date,
    *,
    budget: CallBudget,
    group_by: list[dict[str, str]],
) -> tuple[CostGroup, ...]:
    """One `GetCostAndUsage` call, grouped. Raises `CostFailure` on any SDK error (COST-07)."""
    budget.spend()
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=[_METRIC],
            GroupBy=group_by,
        )
    except (ClientError, BotoCoreError) as exc:
        raise CostFailure(classify_client_error(exc)) from exc
    results = response.get("ResultsByTime") or []
    collected: list[dict[str, Any]] = []
    for period in results:
        collected.extend(period.get("Groups") or [])
    return to_groups(collected)


def fetch_total(ce_client: Any, start: date, end: date, *, budget: CallBudget) -> str:
    """One ungrouped `GetCostAndUsage` call, returning the amount as an unparsed string."""
    budget.spend()
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=[_METRIC],
        )
    except (ClientError, BotoCoreError) as exc:
        raise CostFailure(classify_client_error(exc)) from exc
    for period in response.get("ResultsByTime") or []:
        amount = period.get("Total", {}).get(_METRIC, {}).get("Amount")
        if amount is not None:
            return str(amount)
    return "0"
