"""Collector configuration, read from the environment exactly once (NFR Design §1, §2).

Two things live here so the handler stays about orchestration: the environment parse, and the
declarative `botocore.Config` that makes the upstream call bounded and retryable. Every value is a
stack parameter with a default good enough for a hand deploy (the pipeline passes them explicitly).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from botocore.config import Config


@dataclass(frozen=True)
class CollectorConfig:
    """Everything the collector needs from its environment, resolved up front."""

    snapshot_bucket: str
    snapshot_key: str
    page_limit: int
    deadline_safety_ms: int
    connect_timeout: float
    read_timeout: float
    max_attempts: int

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "CollectorConfig":
        """Build from `os.environ` (or an injected mapping, for tests).

        `SNAPSHOT_BUCKET` is required and has no default: a collector with nowhere to write is a
        misconfiguration that should fail at construction, not silently write nothing.
        """
        e = os.environ if env is None else env
        bucket = e.get("SNAPSHOT_BUCKET", "")
        if not bucket:
            raise ValueError("SNAPSHOT_BUCKET is required")
        return cls(
            snapshot_bucket=bucket,
            snapshot_key=e.get("SNAPSHOT_KEY", "snapshots/current.json"),
            page_limit=int(e.get("PAGE_LIMIT", "50")),
            deadline_safety_ms=int(e.get("DEADLINE_SAFETY_MS", "20000")),
            connect_timeout=float(e.get("CONNECT_TIMEOUT", "5")),
            read_timeout=float(e.get("READ_TIMEOUT", "15")),
            max_attempts=int(e.get("MAX_ATTEMPTS", "5")),
        )

    def botocore_config(self) -> Config:
        """The tagging client's config: explicit timeouts + standard-mode retries (NFR Design §1).

        `standard` mode supplies exponential backoff with jitter, which the design uses rather than
        re-implements. The explicit `read_timeout` is the load-bearing part of CR-02 -- boto3's
        default socket timeout is long enough to consume most of the Lambda budget before the SDK
        notices a stalled upstream.
        """
        return Config(
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries={"mode": "standard", "max_attempts": self.max_attempts},
        )
