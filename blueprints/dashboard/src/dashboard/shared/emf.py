"""Metrics via the CloudWatch Embedded Metric Format (NFR Design §5; R-8, CR-06, RESILIENCY-05).

An EMF metric *is* a log line: a JSON object carrying an `_aws` envelope that CloudWatch extracts
metrics from with no API call. That property is the whole reason this was chosen over
`put_metric_data` (NFR Design Q4): no API call means no IAM permission and, decisively, nothing
that can throttle on the collector's failure path -- exactly when R-8 must still fire.

**CR-04's privacy rule extends to dimensions** (NFR Design Interaction 2): a dimension value lands
in CloudWatch as a searchable key, so a tag value there would leak a NetID just as a log field
would. The API below takes counts and a low-cardinality `outcome` string; it has no parameter for a
tag value, which is the enforcement.

The honest cost (recorded at NFR Design §5, §9): a malformed envelope emits no metric and fails
*silently*. R-8 is a `deployed`-only requirement for that reason; `test_collector_metrics.py`
asserts the envelope shape, which is the most a non-deployed test can do.
"""

from __future__ import annotations

import json
import sys
from typing import Literal

NAMESPACE = "Dashboard"
"""CloudWatch namespace for every U-02 metric. Kept short and fixed so alarms name it literally."""

Unit = Literal["Count", "Seconds", "Milliseconds", "None"]


def emit_metric(
    metrics: dict[str, tuple[float, Unit]],
    *,
    dimensions: dict[str, str] | None = None,
) -> None:
    """Write one EMF record to stdout covering every metric in `metrics`.

    `metrics` maps a metric name to `(value, unit)`. `dimensions` are low-cardinality labels
    (e.g. `{"function": "collector", "outcome": "success"}`) -- **never a tag value or an ARN**;
    high-cardinality or personal-data dimensions are both a CloudWatch cost blow-up and a CR-04
    violation.

    A single record can carry several metrics sharing one dimension set, which is why the collector
    emits duration and all four counts in one call rather than five.
    """
    dims = dimensions or {}
    payload: dict[str, object] = {
        "_aws": {
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [list(dims.keys())] if dims else [[]],
                    "Metrics": [
                        {"Name": name, "Unit": unit} for name, (_v, unit) in metrics.items()
                    ],
                }
            ],
        },
    }
    for name, (value, _unit) in metrics.items():
        payload[name] = value
    for key, dim_value in dims.items():
        payload[key] = dim_value
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
