"""Read API configuration from the environment (AR-*; TSD-8/R-4).

`STALE_THRESHOLD_S` is a stack parameter set as a multiple of the collection interval (3x by
default -- R-4), never a bare constant here: the interval is itself a parameter, so a fixed value
would be silently invalidated the moment someone changed the schedule.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class ApiConfig:
    snapshot_bucket: str
    snapshot_key: str
    stale_after: timedelta
    # A4.1: three per-section keys, not one snapshot object. Each has a single writer, so no
    # read-modify-write is ever needed and each section carries its own age.
    cost_key: str = "cost/current.json"
    telemetry_key: str = "telemetry/current.json"
    # The rate table's JSON, resolved from SSM at deploy time into the environment. Empty means no
    # rates are configured, which surfaces as "rate missing" rather than as a zero price (COST-14).
    model_rates: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ApiConfig":
        e = os.environ if env is None else env
        bucket = e.get("SNAPSHOT_BUCKET", "")
        if not bucket:
            raise ValueError("SNAPSHOT_BUCKET is required")
        return cls(
            snapshot_bucket=bucket,
            snapshot_key=e.get("SNAPSHOT_KEY", "snapshots/current.json"),
            stale_after=timedelta(seconds=int(e.get("STALE_THRESHOLD_S", str(3 * 3600)))),
            cost_key=e.get("COST_KEY", "cost/current.json"),
            telemetry_key=e.get("TELEMETRY_KEY", "telemetry/current.json"),
            model_rates=e.get("MODEL_RATES") or None,
        )
