"""Config parse + the declarative botocore.Config (NFR Design §1). Review-visible assertions.

The client's retry/timeout config is the load-bearing part of CR-02, so it is asserted directly
rather than left to a reviewer to eyeball.
"""

from __future__ import annotations

import pytest

from dashboard.collector.config import CollectorConfig


def test_from_env_requires_bucket() -> None:
    with pytest.raises(ValueError):
        CollectorConfig.from_env({})


def test_from_env_defaults() -> None:
    c = CollectorConfig.from_env({"SNAPSHOT_BUCKET": "b"})
    assert c.snapshot_bucket == "b"
    assert c.snapshot_key == "snapshots/current.json"
    assert c.page_limit == 50
    assert c.deadline_safety_ms == 20000
    assert c.max_attempts == 5


def test_from_env_overrides() -> None:
    c = CollectorConfig.from_env(
        {
            "SNAPSHOT_BUCKET": "b",
            "SNAPSHOT_KEY": "k",
            "PAGE_LIMIT": "10",
            "DEADLINE_SAFETY_MS": "5000",
            "CONNECT_TIMEOUT": "2",
            "READ_TIMEOUT": "9",
            "MAX_ATTEMPTS": "3",
        }
    )
    assert (c.snapshot_key, c.page_limit, c.deadline_safety_ms) == ("k", 10, 5000)
    assert (c.connect_timeout, c.read_timeout, c.max_attempts) == (2.0, 9.0, 3)


def test_botocore_config_has_timeouts_and_standard_retries() -> None:
    c = CollectorConfig.from_env({"SNAPSHOT_BUCKET": "b", "CONNECT_TIMEOUT": "2", "READ_TIMEOUT": "9"})
    cfg = c.botocore_config()
    assert cfg.connect_timeout == 2.0
    assert cfg.read_timeout == 9.0
    assert cfg.retries["mode"] == "standard"
    assert cfg.retries["max_attempts"] == 5
