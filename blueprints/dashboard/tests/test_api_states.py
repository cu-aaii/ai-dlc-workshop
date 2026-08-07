"""The six-state mapping, all six rows (AR-03). The highest-value tests in this unit.

Rows 3 and 4 -- `ok` with zero resources vs `no_data` -- are the pair US-06 exists for; they are
asserted *distinct* in status and data, not just in a count.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from dashboard.core import build_snapshot, normalize_all
from dashboard.api import views
from dashboard.api.loading import LoadOutcome, LoadState
from dashboard.api.shaping import shape

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
STALE_AFTER = timedelta(hours=3)


def _snapshot(arns: list[str], collected_at: datetime):
    raw = [{"ResourceARN": a, "Tags": []} for a in arns]
    return build_snapshot(normalize_all(raw), collected_at=collected_at)


def _present(snapshot) -> LoadOutcome:
    return LoadOutcome(LoadState.PRESENT, snapshot)


def _body(response: dict[str, Any]) -> Any:
    return json.loads(response["body"])


def test_row1_ok_with_resources() -> None:
    out = _present(_snapshot(["arn:aws:s3:::a"], NOW - timedelta(hours=1)))
    r = shape(out, views.inventory, NOW, STALE_AFTER)
    assert r["statusCode"] == 200
    b = _body(r)
    assert b["status"] == "ok" and b["freshness"] == "fresh"
    assert b["counts"]["resources"] == 1 and len(b["data"]) == 1


def test_row2_stale_banner() -> None:
    out = _present(_snapshot(["arn:aws:s3:::a"], NOW - timedelta(hours=10)))
    r = shape(out, views.inventory, NOW, STALE_AFTER)
    assert r["statusCode"] == 200
    b = _body(r)
    assert b["status"] == "stale" and b["freshness"] == "stale"
    assert b["collected_at"] is not None


def test_row3_ok_zero_resources() -> None:
    out = _present(_snapshot([], NOW - timedelta(hours=1)))
    r = shape(out, views.inventory, NOW, STALE_AFTER)
    b = _body(r)
    assert r["statusCode"] == 200 and b["status"] == "ok"
    assert b["counts"]["resources"] == 0 and b["data"] == []


def test_row4_no_data() -> None:
    r = shape(LoadOutcome(LoadState.ABSENT, None), views.inventory, NOW, STALE_AFTER)
    b = _body(r)
    assert r["statusCode"] == 200 and b["status"] == "no_data"
    assert b["data"] is None and b["collected_at"] is None


def test_rows_3_and_4_are_distinguishable() -> None:
    # The US-06 crux: "ran and found nothing" must not look like "never ran".
    empty = _body(shape(_present(_snapshot([], NOW - timedelta(hours=1))), views.inventory, NOW, STALE_AFTER))
    no_data = _body(shape(LoadOutcome(LoadState.ABSENT, None), views.inventory, NOW, STALE_AFTER))
    assert empty["status"] != no_data["status"]
    assert (empty["data"], no_data["data"]) == ([], None)


def test_row5_unreadable_503() -> None:
    r = shape(LoadOutcome(LoadState.UNREADABLE, None), views.inventory, NOW, STALE_AFTER)
    assert r["statusCode"] == 503 and _body(r) == {"status": "error"}


def test_invalid_future_timestamp_is_503_not_ok() -> None:
    # INVALID checked before the stale/ok split: a future collected_at must not read as ok.
    out = _present(_snapshot(["arn:aws:s3:::a"], NOW + timedelta(hours=1)))
    r = shape(out, views.inventory, NOW, STALE_AFTER)
    assert r["statusCode"] == 503 and _body(r) == {"status": "error"}


@pytest.mark.parametrize("view", [views.inventory, views.tag_gaps, views.status])
def test_counts_present_on_every_data_view(view) -> None:
    out = _present(_snapshot(["arn:aws:s3:::a"], NOW - timedelta(hours=1)))
    b = _body(shape(out, view, NOW, STALE_AFTER))
    assert set(b["counts"]) == {"resources", "skipped", "duplicates_removed", "raw_returned"}
