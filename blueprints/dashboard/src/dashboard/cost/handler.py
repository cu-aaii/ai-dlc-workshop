"""C-10 Cost Collector handler (COST-04..08, FR-10.2, FR-10.4).

Orchestration only; every rule lives in `explorer.py` or `dashboard.core.money`. Follows C-01's shape
deliberately -- clock read exactly twice, one `PutObject`, EMF on success *and* failure -- so the two
collectors read the same way despite having opposite failure policies.

**This collector fails whole** (COST-07). Any Cost Explorer call failing writes nothing: the previous
`cost/current.json` survives, and the next daily tick retries. That is the opposite of the telemetry
collector, and deliberately so. A partially-populated cost object would render its missing groups as
*zero spend*, which is worse than a figure that is a day old and honest about it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable

import boto3

from dashboard.core import split_attribution
from dashboard.cost.config import CostConfig
from dashboard.cost.errors import CostFailure, CostReason
from dashboard.cost.explorer import (
    CallBudget,
    fetch_grouped,
    fetch_total,
    last_finalized_day,
    month_to_date,
    year_to_date,
)
from dashboard.shared.emf import emit_metric
from dashboard.shared.logging_json import get_logger

LOG = get_logger(__name__)

COST_SCHEMA_VERSION = "v1-cost"

_GROUP_SERVICE = [{"Type": "DIMENSION", "Key": "SERVICE"}]
_GROUP_USAGE_TYPE = [{"Type": "DIMENSION", "Key": "USAGE_TYPE"}]
_GROUP_TAG_BLUEPRINT = [{"Type": "TAG", "Key": "cornell:blueprint"}]
_GROUP_TAG_DEPLOYMENT = [{"Type": "TAG", "Key": "cornell:deployment-id"}]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run(
    *,
    config: CostConfig,
    ce_client: Any,
    s3_client: Any,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Collect cost and write the cost section. Raises `CostFailure` on any upstream failure."""
    started = clock()
    budget = CallBudget(config.max_ce_calls)
    try:
        day_start, day_end = last_finalized_day(started.date())
        mtd_start, mtd_end = month_to_date(started.date())
        ytd_start, ytd_end = year_to_date(started.date())

        day_total = fetch_total(ce_client, day_start, day_end, budget=budget)
        mtd_total = fetch_total(ce_client, mtd_start, mtd_end, budget=budget)
        ytd_total = fetch_total(ce_client, ytd_start, ytd_end, budget=budget)

        by_service = fetch_grouped(
            ce_client, mtd_start, mtd_end, budget=budget, group_by=_GROUP_SERVICE
        )
        by_usage_type = fetch_grouped(
            ce_client, mtd_start, mtd_end, budget=budget, group_by=_GROUP_USAGE_TYPE
        )
        by_blueprint = fetch_grouped(
            ce_client, mtd_start, mtd_end, budget=budget, group_by=_GROUP_TAG_BLUEPRINT
        )
        by_deployment = fetch_grouped(
            ce_client, mtd_start, mtd_end, budget=budget, group_by=_GROUP_TAG_DEPLOYMENT
        )
    except CostFailure as failure:
        # Emit before raising: the call count is the only evidence of what this run cost, and a
        # failed run still spent money (COST-06).
        LOG.error("cost collection failed", extra={"reason": failure.reason.value})
        emit_metric(
            {"CostCollectFailure": (1, "Count"), "CostExplorerCalls": (budget.used, "Count")},
            dimensions={"outcome": failure.reason.value},
        )
        raise

    blueprint_split = split_attribution(by_blueprint)
    deployment_split = split_attribution(by_deployment)

    payload: dict[str, Any] = {
        "schema_version": COST_SCHEMA_VERSION,
        "collected_at": started.isoformat(),
        # Separate from collected_at on purpose (COST-04): one says when we asked, the other says
        # what the answer covers. Cost Explorer lags 24-48h.
        "covered_through": day_end.isoformat(),
        "currency": "USD",
        "totals": {"day": day_total, "month_to_date": mtd_total, "year_to_date": ytd_total},
        "by_service": [{"key": g.key, "amount": str(g.amount)} for g in by_service],
        "by_usage_type": [{"key": g.key, "amount": str(g.amount)} for g in by_usage_type],
        "by_blueprint": _split_payload(blueprint_split),
        "by_deployment": _split_payload(deployment_split),
        "ce_calls": budget.used,
    }
    s3_client.put_object(
        Bucket=config.snapshot_bucket,
        Key=config.cost_key,
        Body=_serialize(payload),
        ContentType="application/json",
    )
    emit_metric(
        {
            "CostCollectSuccess": (1, "Count"),
            "CostExplorerCalls": (budget.used, "Count"),
            "UnattributedBlueprintCost": (float(blueprint_split.unattributed), "None"),
        },
        dimensions={"outcome": "success"},
    )
    LOG.info(
        "cost collected",
        extra={
            "ce_calls": budget.used,
            "fully_unattributed": blueprint_split.fully_unattributed,
        },
    )


def _split_payload(split: Any) -> dict[str, Any]:
    """Serialize an attribution split.

    `unattributed` is a **named sibling** of `attributed`, never one entry in the list. That shape is
    what stops a consumer treating the empty-value tag group as a blueprint name.
    """
    return {
        "attributed": [{"key": g.key, "amount": str(g.amount)} for g in split.attributed],
        "unattributed": str(split.unattributed),
        "fully_unattributed": split.fully_unattributed,
    }


def handler(event: dict[str, Any], context: Any) -> None:
    """Lambda entrypoint. Bootstraps clients; `run` holds the logic."""
    config = CostConfig.from_env()
    session = boto3.session.Session()
    boto_config = config.botocore_config()
    run(
        config=config,
        ce_client=session.client("ce", config=boto_config),
        s3_client=session.client("s3", config=boto_config),
    )
