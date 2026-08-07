"""EMF envelope shape on success and failure (NFR Design §5; R-8, CR-06).

A non-deployed test cannot prove metrics *arrive* (R-8 is deployed-only), but it can prove the
`_aws` envelope is well-formed -- the failure mode being a silently dropped metric.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from dashboard.collector import handler as H
from dashboard.collector.config import CollectorConfig
from dashboard.collector.errors import CollectorFailure


class OnePage:
    def get_resources(self, **kwargs: object) -> dict[str, object]:
        return {"ResourceTagMappingList": [{"ResourceARN": "arn:aws:s3:::b", "Tags": []}]}


class TokenPager:
    def get_resources(self, **kwargs: object) -> dict[str, object]:
        return {"ResourceTagMappingList": [], "PaginationToken": "more"}


class FakeS3:
    def put_object(self, **kwargs: object) -> None:
        return None


def _emf_lines(captured: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in captured.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "_aws" in obj:
            out.append(obj)
    return out


def test_success_emf_shape(capsys: pytest.CaptureFixture[str]) -> None:
    H.run(
        config=CollectorConfig.from_env({"SNAPSHOT_BUCKET": "b"}),
        tagging_client=OnePage(),
        s3_client=FakeS3(),
        remaining_ms=lambda: 10**9,
        clock=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    envelopes = _emf_lines(capsys.readouterr().out)
    assert len(envelopes) == 1
    env = envelopes[0]
    meta = env["_aws"]["CloudWatchMetrics"][0]
    assert meta["Namespace"] == "Dashboard"
    names = {m["Name"] for m in meta["Metrics"]}
    assert {"ResourcesCollected", "RawReturned", "SkippedCount", "CollectionDuration"} <= names
    assert env["outcome"] == "success"
    assert env["ResourcesCollected"] == 1


def test_failure_emf_shape(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(CollectorFailure):
        H.run(
            config=CollectorConfig.from_env({"SNAPSHOT_BUCKET": "b", "PAGE_LIMIT": "2"}),
            tagging_client=TokenPager(),
            s3_client=FakeS3(),
            remaining_ms=lambda: 10**9,
            clock=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
        )
    envelopes = _emf_lines(capsys.readouterr().out)
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env["outcome"] == "failure"
    assert env["reason"] == "PAGE_LIMIT_EXCEEDED"
    assert env["CollectorFailure"] == 1
