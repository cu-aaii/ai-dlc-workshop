"""Pagination bounds (CR-01, NFR Design §3). Stubbed pager -- no AWS.

The highest-value collector tests: the page-limit breach must *raise*, never truncate, because
truncation is the silent-under-reporting failure CR-01 exists to forbid.
"""

from __future__ import annotations

import pytest

from dashboard.collector.errors import CollectorFailure, CollectorReason
from dashboard.collector.tagging import collect_all_resources

FAR_FUTURE = lambda: 10**9  # noqa: E731 -- plenty of budget; deadline never trips here


class FakePager:
    """A get_resources stub returning a fixed list of pages, honoring PaginationToken."""

    def __init__(self, pages: list[dict[str, object]]) -> None:
        self._pages = pages
        self.calls = 0

    def get_resources(self, **kwargs: object) -> dict[str, object]:
        page = self._pages[self.calls]
        self.calls += 1
        return page


def _page(arns: list[str], token: str | None) -> dict[str, object]:
    body: dict[str, object] = {
        "ResourceTagMappingList": [{"ResourceARN": a, "Tags": []} for a in arns]
    }
    if token:
        body["PaginationToken"] = token
    return body


def test_single_page_terminates() -> None:
    client = FakePager([_page(["arn:aws:s3:::b"], token=None)])
    outcome = collect_all_resources(client, page_limit=50, remaining_ms=FAR_FUTURE, deadline_safety_ms=20000)
    assert outcome.pages == 1
    assert outcome.result.raw_returned == 1
    assert client.calls == 1


def test_multi_page_follows_token_then_stops() -> None:
    client = FakePager(
        [
            _page(["arn:aws:s3:::a"], token="t1"),
            _page(["arn:aws:s3:::b"], token="t2"),
            _page(["arn:aws:s3:::c"], token=None),
        ]
    )
    outcome = collect_all_resources(client, page_limit=50, remaining_ms=FAR_FUTURE, deadline_safety_ms=20000)
    assert outcome.pages == 3
    assert outcome.result.raw_returned == 3


def test_empty_first_page() -> None:
    client = FakePager([_page([], token=None)])
    outcome = collect_all_resources(client, page_limit=50, remaining_ms=FAR_FUTURE, deadline_safety_ms=20000)
    assert outcome.pages == 1
    assert outcome.result.raw_returned == 0
    assert outcome.result.records == ()


def test_page_limit_breach_raises_not_truncates() -> None:
    # Every page carries a token, so the stream never ends on its own -- the limit must stop it.
    endless = [_page([f"arn:aws:s3:::b{i}"], token=f"t{i}") for i in range(10)]
    client = FakePager(endless)
    with pytest.raises(CollectorFailure) as exc:
        collect_all_resources(client, page_limit=3, remaining_ms=FAR_FUTURE, deadline_safety_ms=20000)
    assert exc.value.reason is CollectorReason.PAGE_LIMIT_EXCEEDED
