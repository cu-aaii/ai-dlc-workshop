"""Read the current snapshot from S3, classifying into three states (AR-02). **Total.**

A raising loader forces the caller into `except`, which is exactly where `ABSENT` ("no run yet")
and `UNREADABLE` ("a run wrote something we can't read") collapse into one indistinguishable "it
broke" -- and telling those two apart is the whole point of US-06. So this classifies instead:

- `NoSuchKey`                                  -> ABSENT      (no successful run yet -> 200 no_data)
- any other `ClientError`                      -> UNREADABLE  (-> 503)
- `IncompatibleSchema` / `InvalidSnapshot`     -> UNREADABLE  (-> 503)

The two U-01 errors are caught **by type** (U-01 PAT-7); a bare `except CoreError` would work today
and silently stop distinguishing the moment a fifth error type appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from botocore.exceptions import ClientError

from dashboard.core import IncompatibleSchema, InvalidSnapshot, Snapshot, deserialize_snapshot

_ABSENT_CODES = frozenset({"NoSuchKey", "404", "NoSuchBucket"})


class LoadState(Enum):
    PRESENT = auto()
    ABSENT = auto()
    UNREADABLE = auto()


@dataclass(frozen=True)
class LoadOutcome:
    state: LoadState
    snapshot: Snapshot | None


def load_current_snapshot(s3_client: object, bucket: str, key: str) -> LoadOutcome:
    """Fetch and parse the current snapshot; never raises."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)  # type: ignore[attr-defined]
        body = response["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        state = LoadState.ABSENT if code in _ABSENT_CODES else LoadState.UNREADABLE
        return LoadOutcome(state, None)

    try:
        snapshot = deserialize_snapshot(body)
    except (IncompatibleSchema, InvalidSnapshot):
        return LoadOutcome(LoadState.UNREADABLE, None)
    return LoadOutcome(LoadState.PRESENT, snapshot)
