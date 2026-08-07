"""C-11 Telemetry Collector handler (TEL-02..05, TEL-10).

**This collector degrades per counter** (TEL-05), and that is the deliberate opposite of the cost
collector's fail-whole policy (COST-07). The two halves -- AWS-emitted metrics and blueprint-declared
counters -- are read independently, and each counter carries its own state. Failing the whole run
because one half returned nothing would erase real AWS data merely because no blueprint has been
instrumented yet, which is the normal state today.

The reason the policies differ is that the upstreams differ. Cost Explorer is expensive per call and
its data moves once a day, so a partial write is both avoidable and dangerous. CloudWatch is cheap and
continuous, and the two halves have genuinely different availability.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import boto3

from dashboard.core import Catalog, CounterSeries, TelemetryState, declared_counters
from dashboard.shared.emf import emit_metric
from dashboard.shared.logging_json import get_logger
from dashboard.telemetry.catalog_loader import load_catalog
from dashboard.telemetry.config import TelemetryConfig
from dashboard.telemetry.metrics import (
    MetricRequest,
    MetricsUnavailable,
    build_aws_requests,
    discover_models,
    fetch,
)

LOG = get_logger(__name__)

TELEMETRY_SCHEMA_VERSION = "v1-telemetry"

ACCOUNT_SCOPE = "account"
"""Deployment id for account-wide AWS metrics.

`AWS/Bedrock` and `AWS/Bedrock-AgentCore` metrics carry no `cornell:deployment-id` -- they are
account-scoped. Bucketing them under a real deployment id would fabricate attribution, so they are
labelled explicitly as account-scoped instead.
"""


class TelemetryFailure(Exception):
    """Both halves were unreadable, so there is nothing to write."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _declared_requests(catalog: Catalog) -> tuple[MetricRequest, ...]:
    """Build requests for exactly the counters the catalog declares (TEL-03).

    An undeclared counter present in CloudWatch is not read. That is NFR-T5's closed allowlist: the
    dashboard renders what blueprints promised, not whatever happens to exist.
    """
    requests: list[MetricRequest] = []
    for blueprint in catalog.emitting_blueprints:
        namespace = catalog.namespaces[blueprint]
        for counter in declared_counters(catalog, blueprint):
            requests.append(
                MetricRequest(
                    namespace=namespace,
                    metric_name=counter.name,
                    stat="Sum",
                    dimensions=(),
                    deployment_id=blueprint,
                )
            )
    return tuple(requests)


def _serialize_series(series: tuple[CounterSeries, ...]) -> list[dict[str, Any]]:
    return [
        {
            "deployment_id": item.key.deployment_id,
            "agent_id": item.key.agent_id,
            "model": item.key.model,
            "name": item.counter.name,
            "value": item.counter.value,
            "state": item.counter.state.value,
        }
        for item in series
    ]


def run(
    *,
    config: TelemetryConfig,
    cw_client: Any,
    s3_client: Any,
    catalog: Catalog,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Collect telemetry and write the telemetry section."""
    started = clock()
    window_start = started - timedelta(hours=config.lookback_hours)

    aws_state = TelemetryState.OK
    aws_series: tuple[CounterSeries, ...] = ()
    try:
        models = discover_models(cw_client)
        requests = build_aws_requests(models, ACCOUNT_SCOPE)
        if len(requests) > config.max_metrics:
            # TEL-10: the allowlist is constant but the model list is discovered, so this is a
            # product. Refuse rather than silently truncating to a subset of models.
            raise MetricsUnavailable("metric budget exceeded")
        aws_series = fetch(cw_client, requests, window_start, started, config.period_seconds)
    except MetricsUnavailable:
        aws_state = TelemetryState.CANNOT_READ
        LOG.error("aws metric half unreadable")

    declared_state = TelemetryState.OK
    declared_series: tuple[CounterSeries, ...] = ()
    declared = _declared_requests(catalog)
    if not declared:
        # No blueprint declares any counter -- the expected state until one is instrumented. This is
        # NOT a read failure, and conflating the two would tell an operator to investigate CloudWatch
        # when the real answer is "nobody emits yet" (NFR-T7).
        declared_state = TelemetryState.NOT_INSTRUMENTED
    else:
        try:
            declared_series = fetch(
                cw_client, declared, window_start, started, config.period_seconds
            )
        except MetricsUnavailable:
            declared_state = TelemetryState.CANNOT_READ
            LOG.error("declared counter half unreadable")

    if aws_state is TelemetryState.CANNOT_READ and declared_state is TelemetryState.CANNOT_READ:
        emit_metric(
            {"TelemetryCollectFailure": (1, "Count")}, dimensions={"outcome": "both_unreadable"}
        )
        raise TelemetryFailure("both halves unreadable")

    payload: dict[str, Any] = {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "collected_at": started.isoformat(),
        "window": {"start": window_start.isoformat(), "end": started.isoformat()},
        "aws": {"state": aws_state.value, "counters": _serialize_series(aws_series)},
        "declared": {
            "state": declared_state.value,
            "counters": _serialize_series(declared_series),
            # Named so the UI can say WHICH blueprints are not instrumented rather than showing a
            # blank panel (FR-9.7.3).
            "not_instrumented": list(catalog.not_instrumented),
            "emitting": list(catalog.emitting_blueprints),
        },
    }
    s3_client.put_object(
        Bucket=config.snapshot_bucket,
        Key=config.telemetry_key,
        Body=_serialize(payload),
        ContentType="application/json",
    )
    emit_metric(
        {
            "TelemetryCollectSuccess": (1, "Count"),
            "TelemetryCountersRead": (len(aws_series) + len(declared_series), "Count"),
        },
        dimensions={"outcome": "success"},
    )
    LOG.info(
        "telemetry collected",
        extra={
            "aws_state": aws_state.value,
            "declared_state": declared_state.value,
            "counters": len(aws_series) + len(declared_series),
        },
    )


def handler(event: dict[str, Any], context: Any) -> None:
    """Lambda entrypoint."""
    config = TelemetryConfig.from_env()
    session = boto3.session.Session()
    boto_config = config.botocore_config()
    run(
        config=config,
        cw_client=session.client("cloudwatch", config=boto_config),
        s3_client=session.client("s3", config=boto_config),
        catalog=load_catalog(),
    )
