"""CR-04's privacy rule: a tag value must never reach a log line.

The analogue of U-01's no-leak test. Runs the collector end to end (fake AWS) with a resource
carrying a sensitive tag value and a malformed resource that gets skipped, then asserts the value
appears in no emitted log record.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from dashboard.collector import handler as H
from dashboard.collector.config import CollectorConfig
from dashboard.shared.logging_json import JsonFormatter

SECRET = "abc123-netid"  # a cornell:owner value; must never appear in logs


class OnePage:
    def get_resources(self, **kwargs: object) -> dict[str, object]:
        return {
            "ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:s3:::bucket", "Tags": [{"Key": "cornell:owner", "Value": SECRET}]},
                {"ResourceARN": "not-an-arn", "Tags": []},  # skipped -> exercises log_skipped
            ]
        }


class FakeS3:
    def __init__(self) -> None:
        self.body: bytes | None = None

    def put_object(self, **kwargs: object) -> None:
        self.body = kwargs["Body"]  # type: ignore[assignment]


def test_no_tag_value_in_logs() -> None:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    H.LOG.addHandler(handler)
    try:
        s3 = FakeS3()
        H.run(
            config=CollectorConfig.from_env({"SNAPSHOT_BUCKET": "b"}),
            tagging_client=OnePage(),
            s3_client=s3,
            remaining_ms=lambda: 10**9,
            clock=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
        )
    finally:
        H.LOG.removeHandler(handler)

    logged = buf.getvalue()
    assert SECRET not in logged
    # But the skip WAS logged -- by reason code, so the observability is real, just leak-free.
    assert "skipped resources" in logged
    # And the snapshot itself (which legitimately contains the tag value) was written to S3.
    assert s3.body is not None and SECRET.encode() in s3.body
