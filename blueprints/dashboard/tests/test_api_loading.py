"""`load_current_snapshot` classification: three states from three stubbed S3 outcomes (AR-02).

Total by construction -- none of these raises out of the loader.
"""

from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from dashboard.core import build_snapshot, normalize_all, serialize_snapshot
from dashboard.api.loading import LoadState, load_current_snapshot

VALID = serialize_snapshot(
    build_snapshot(normalize_all([{"ResourceARN": "arn:aws:s3:::a", "Tags": []}]),
                   collected_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
)


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class OkS3:
    def get_object(self, **kwargs: object) -> dict[str, object]:
        return {"Body": _Body(VALID)}


class CorruptS3:
    def get_object(self, **kwargs: object) -> dict[str, object]:
        return {"Body": _Body(b"not json at all")}


class MissingS3:
    def get_object(self, **kwargs: object) -> dict[str, object]:
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "nope"}}, "GetObject")


class DeniedS3:
    def get_object(self, **kwargs: object) -> dict[str, object]:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetObject")


def test_present() -> None:
    out = load_current_snapshot(OkS3(), "b", "k")
    assert out.state is LoadState.PRESENT and out.snapshot is not None


def test_absent_on_no_such_key() -> None:
    out = load_current_snapshot(MissingS3(), "b", "k")
    assert out.state is LoadState.ABSENT and out.snapshot is None


def test_unreadable_on_other_client_error() -> None:
    out = load_current_snapshot(DeniedS3(), "b", "k")
    assert out.state is LoadState.UNREADABLE


def test_unreadable_on_corrupt_body() -> None:
    out = load_current_snapshot(CorruptS3(), "b", "k")
    assert out.state is LoadState.UNREADABLE
