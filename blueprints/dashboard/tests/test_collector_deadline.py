"""The internal deadline and retry-exhaustion bounds (NFR Design §2, §1; P-3, CR-02).

Both are checked with a stubbed pager and a driven remaining-time function -- no clock, no AWS.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError

from dashboard.collector.errors import CollectorFailure, CollectorReason
from dashboard.collector.tagging import collect_all_resources


class TokenPager:
    """Always returns a next token, so only a bound can stop the loop."""

    def get_resources(self, **kwargs: object) -> dict[str, object]:
        return {"ResourceTagMappingList": [], "PaginationToken": "more"}


def test_deadline_stops_before_next_page() -> None:
    # Remaining time drops below the 20 s safety margin on the second check.
    budget = iter([30000, 15000, 15000, 15000])
    client = TokenPager()
    with pytest.raises(CollectorFailure) as exc:
        collect_all_resources(client, page_limit=50, remaining_ms=lambda: next(budget), deadline_safety_ms=20000)
    assert exc.value.reason is CollectorReason.UPSTREAM_TOO_SLOW


def test_client_error_maps_to_throttled() -> None:
    class Throttling:
        def get_resources(self, **kwargs: object) -> dict[str, object]:
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "GetResources")

    with pytest.raises(CollectorFailure) as exc:
        collect_all_resources(Throttling(), page_limit=50, remaining_ms=lambda: 10**9, deadline_safety_ms=20000)
    assert exc.value.reason is CollectorReason.UPSTREAM_THROTTLED


def test_connection_error_maps_to_throttled() -> None:
    class Flaky:
        def get_resources(self, **kwargs: object) -> dict[str, object]:
            raise ConnectTimeoutError(endpoint_url="https://tagging")

    with pytest.raises(CollectorFailure) as exc:
        collect_all_resources(Flaky(), page_limit=50, remaining_ms=lambda: 10**9, deadline_safety_ms=20000)
    assert exc.value.reason is CollectorReason.UPSTREAM_THROTTLED
