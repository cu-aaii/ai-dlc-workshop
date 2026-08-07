"""Telemetry collector configuration (TEL-10, NFR-T8)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from botocore.config import Config


@dataclass(frozen=True)
class TelemetryConfig:
    """Everything the telemetry collector needs, resolved up front."""

    snapshot_bucket: str
    telemetry_key: str
    lookback_hours: int
    period_seconds: int
    max_metrics: int
    connect_timeout: float
    read_timeout: float
    max_attempts: int

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "TelemetryConfig":
        e = os.environ if env is None else env
        bucket = e.get("SNAPSHOT_BUCKET", "")
        if not bucket:
            raise ValueError("SNAPSHOT_BUCKET is required")
        return cls(
            snapshot_bucket=bucket,
            telemetry_key=e.get("TELEMETRY_KEY", "telemetry/current.json"),
            lookback_hours=int(e.get("LOOKBACK_HOURS", "24")),
            period_seconds=int(e.get("PERIOD_SECONDS", "86400")),
            # The allowlist is a constant, but the model list is DISCOVERED, so the number of metrics
            # requested is a product rather than a constant (TEL-10). Bounded here.
            max_metrics=int(e.get("MAX_METRICS", "400")),
            connect_timeout=float(e.get("CONNECT_TIMEOUT", "5")),
            read_timeout=float(e.get("READ_TIMEOUT", "15")),
            max_attempts=int(e.get("MAX_ATTEMPTS", "5")),
        )

    def botocore_config(self) -> Config:
        return Config(
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries={"mode": "standard", "max_attempts": self.max_attempts},
        )
