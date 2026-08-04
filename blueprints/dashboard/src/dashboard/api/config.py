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
        )
