"""Cost collector configuration (COST-05, NFR-T8).

Same shape as `collector/config.py`, with one field that exists for a reason unique to this
collector: **`max_ce_calls`**. `ce:GetCostAndUsage` is billed **$0.01 per request** against an account
whose entire measured monthly spend is ~$9 (amendment A3.6). An unbounded fan-out of cost queries
would make the cost dashboard a material line item in the bill it exists to explain.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from botocore.config import Config


@dataclass(frozen=True)
class CostConfig:
    """Everything the cost collector needs, resolved up front."""

    snapshot_bucket: str
    cost_key: str
    rates_parameter: str
    max_ce_calls: int
    connect_timeout: float
    read_timeout: float
    max_attempts: int

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "CostConfig":
        e = os.environ if env is None else env
        bucket = e.get("SNAPSHOT_BUCKET", "")
        if not bucket:
            raise ValueError("SNAPSHOT_BUCKET is required")
        return cls(
            snapshot_bucket=bucket,
            cost_key=e.get("COST_KEY", "cost/current.json"),
            rates_parameter=e.get("MODEL_RATES_PARAM", ""),
            max_ce_calls=int(e.get("MAX_CE_CALLS", "8")),
            connect_timeout=float(e.get("CONNECT_TIMEOUT", "5")),
            read_timeout=float(e.get("READ_TIMEOUT", "20")),
            max_attempts=int(e.get("MAX_ATTEMPTS", "3")),
        )

    def botocore_config(self) -> Config:
        """Explicit timeouts + standard retries.

        `max_attempts` is deliberately lower than the tag collector's 5: every retry of a Cost
        Explorer call is another $0.01, and the data being fetched only changes once a day, so
        retrying hard buys nothing but spend.
        """
        return Config(
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries={"mode": "standard", "max_attempts": self.max_attempts},
        )
