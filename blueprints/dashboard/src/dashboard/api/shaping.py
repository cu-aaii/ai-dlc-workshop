"""Map a load outcome to the response envelope -- the six states, in order (AR-03, AR-05, AR-06).

The order is load-bearing (`business-logic-model.md`): `INVALID` is checked **before** the
stale/ok split, because a future `collected_at` gives a negative age that is trivially under any
threshold and would otherwise read as `ok`. `counts_of` is **unconditional** on every data response
(AR-05, obligation 2) -- slimming it away would end the skip-and-count guarantee at the one boundary
a user sees.

Error bodies carry `{"status": "error"}` and nothing else (AR-06): no stack trace, ARN, bucket
name, key, or account id. Because the generic-503 mapping lives in exactly one place, a new route
cannot undo it by forgetting to sanitize its own errors.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from dashboard.core import Freshness, Snapshot, evaluate_freshness
from dashboard.api.loading import LoadOutcome, LoadState

_JSON_HEADERS = {"content-type": "application/json"}

View = Callable[[Snapshot], Any]


def _response(status_code: int, envelope: dict[str, Any]) -> dict[str, Any]:
    """An API Gateway HTTP API (proxy) response with a JSON body."""
    return {
        "statusCode": status_code,
        "headers": dict(_JSON_HEADERS),
        "body": json.dumps(envelope, separators=(",", ":")),
    }


def counts_of(snapshot: Snapshot) -> dict[str, int]:
    """The four provenance counts, on every data response (AR-05)."""
    return {
        "resources": len(snapshot.resources),
        "skipped": snapshot.skipped_count,
        "duplicates_removed": snapshot.duplicates_removed,
        "raw_returned": snapshot.raw_returned,
    }


_ZERO_COUNTS = {"resources": 0, "skipped": 0, "duplicates_removed": 0, "raw_returned": 0}


def error_response(status_code: int) -> dict[str, Any]:
    """A generic error with no internals (AR-06). Used for 404 and 503 alike."""
    return _response(status_code, {"status": "error"})


def health() -> dict[str, Any]:
    """Static liveness (AR-08). No S3 read, no envelope."""
    return _response(200, {"status": "ok"})


def shape(outcome: LoadOutcome, view: View, now: datetime, stale_after: timedelta) -> dict[str, Any]:
    """The six-state mapping (AR-03). `now`/`stale_after` injected so this stays testable."""
    if outcome.state is LoadState.ABSENT:
        return _response(
            200,
            {"status": "no_data", "collected_at": None, "freshness": None,
             "counts": dict(_ZERO_COUNTS), "data": None},
        )
    if outcome.state is LoadState.UNREADABLE:
        return error_response(503)

    snapshot = outcome.snapshot
    if snapshot is None:  # PRESENT always carries a snapshot; guard (not assert) keeps -O honest
        return error_response(503)
    freshness = evaluate_freshness(snapshot.collected_at, now, stale_after)
    if freshness is Freshness.INVALID:
        return error_response(503)

    body_status = "stale" if freshness is Freshness.STALE else "ok"
    return _response(
        200,
        {
            "status": body_status,
            "collected_at": snapshot.collected_at.isoformat(),
            "freshness": freshness.value,
            "counts": counts_of(snapshot),
            "data": view(snapshot),
        },
    )
