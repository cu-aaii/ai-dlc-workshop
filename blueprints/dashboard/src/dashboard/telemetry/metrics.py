"""CloudWatch metric reads: the fixed AWS allowlist, and declared-counter reads (TEL-02, TEL-03).

**The AWS allowlist is a module-level constant, not configuration.** That is what makes NFR-T5's
"closed allowlist" true for the pull path: AWS's own metrics are declared in no blueprint manifest, so
a catalog cannot cover them, and closing the set in code is the only place it *can* be closed. Only
`ModelId` **dimension values** are discovered at runtime -- never which metrics to read.

The metric names below were verified against the real deploy account (amendment A3.1/A3.2), not taken
from documentation: `AWS/Bedrock` carries 38 metric streams across 6 models there, and
`AWS/Bedrock-AgentCore` carries 13 including `Sessions` and `ActiveSessionCount`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from dashboard.core import Counter, CounterSeries, TelemetryState, counter_key

BEDROCK_NAMESPACE = "AWS/Bedrock"
AGENTCORE_NAMESPACE = "AWS/Bedrock-AgentCore"

BEDROCK_METRICS: tuple[tuple[str, str], ...] = (
    ("Invocations", "Sum"),
    ("InputTokenCount", "Sum"),
    ("OutputTokenCount", "Sum"),
    ("InvocationClientErrors", "Sum"),
    ("InvocationLatency", "Average"),
)
"""Per-model volume, tokens, errors and latency. Dimensioned by `ModelId`."""

AGENTCORE_METRICS: tuple[tuple[str, str], ...] = (
    ("Sessions", "Sum"),
    ("Invocations", "Sum"),
    ("Errors", "Sum"),
    ("Throttles", "Sum"),
    ("Latency", "Average"),
)
"""AgentCore runtime usage. `Sessions` is an adoption signal available with no instrumentation."""


class MetricsUnavailable(Exception):
    """A CloudWatch read failed. Carries no identifiers."""


@dataclass(frozen=True)
class MetricRequest:
    """One metric to fetch, and the key to attribute it to."""

    namespace: str
    metric_name: str
    stat: str
    dimensions: tuple[tuple[str, str], ...]
    deployment_id: str
    agent_id: str | None = None
    model: str | None = None


def discover_models(cw_client: Any, namespace: str = BEDROCK_NAMESPACE) -> tuple[str, ...]:
    """Discover which `ModelId` dimension **values** exist (TEL-02).

    Values only. Which metrics to read is never discovered -- that is the constant above.
    """
    models: set[str] = set()
    try:
        paginator = cw_client.get_paginator("list_metrics")
        for page in paginator.paginate(Namespace=namespace):
            for metric in page.get("Metrics") or []:
                for dimension in metric.get("Dimensions") or []:
                    if dimension.get("Name") == "ModelId":
                        value = str(dimension.get("Value", ""))
                        if value:
                            models.add(value)
    except (ClientError, BotoCoreError) as exc:
        raise MetricsUnavailable("list_metrics failed") from exc
    return tuple(sorted(models))


def build_aws_requests(models: tuple[str, ...], account_deployment_id: str) -> tuple[MetricRequest, ...]:
    """The fixed AWS allowlist crossed with the discovered models.

    Attributed to a synthetic deployment id: these metrics are account-wide and carry no
    `cornell:deployment-id`, so pretending otherwise would fabricate attribution. Naming that
    explicitly is more honest than silently bucketing them under a real deployment.
    """
    requests: list[MetricRequest] = []
    for model in models:
        for name, stat in BEDROCK_METRICS:
            requests.append(
                MetricRequest(
                    namespace=BEDROCK_NAMESPACE,
                    metric_name=name,
                    stat=stat,
                    dimensions=(("ModelId", model),),
                    deployment_id=account_deployment_id,
                    model=model,
                )
            )
    for name, stat in AGENTCORE_METRICS:
        requests.append(
            MetricRequest(
                namespace=AGENTCORE_NAMESPACE,
                metric_name=name,
                stat=stat,
                dimensions=(),
                deployment_id=account_deployment_id,
            )
        )
    return tuple(requests)


def fetch(
    cw_client: Any,
    requests: tuple[MetricRequest, ...],
    start: datetime,
    end: datetime,
    period_seconds: int,
) -> tuple[CounterSeries, ...]:
    """Fetch metric values via `GetMetricData`.

    A metric with no datapoints becomes `NO_DATA_YET`, not zero -- the distinction NFR-T7 requires and
    the one that separates "unused" from "unmeasured".
    """
    if not requests:
        return ()
    queries = [
        {
            "Id": f"m{index}",
            "MetricStat": {
                "Metric": {
                    "Namespace": request.namespace,
                    "MetricName": request.metric_name,
                    "Dimensions": [
                        {"Name": name, "Value": value} for name, value in request.dimensions
                    ],
                },
                "Period": period_seconds,
                "Stat": request.stat,
            },
            "ReturnData": True,
        }
        for index, request in enumerate(requests)
    ]
    try:
        response = cw_client.get_metric_data(
            MetricDataQueries=queries, StartTime=start, EndTime=end
        )
    except (ClientError, BotoCoreError) as exc:
        raise MetricsUnavailable("get_metric_data failed") from exc

    by_id = {
        str(result.get("Id")): result.get("Values") or []
        for result in response.get("MetricDataResults") or []
    }
    series: list[CounterSeries] = []
    for index, request in enumerate(requests):
        values = by_id.get(f"m{index}", [])
        if values:
            counter = Counter(
                name=request.metric_name, value=float(sum(values)), state=TelemetryState.OK
            )
        else:
            counter = Counter(
                name=request.metric_name, value=0.0, state=TelemetryState.NO_DATA_YET
            )
        series.append(
            CounterSeries(
                key=counter_key(request.deployment_id, request.agent_id, request.model),
                counter=counter,
            )
        )
    return tuple(series)
