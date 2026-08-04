"""Pagination over the Resource Groups Tagging API (CR-01, CR-02, CR-03; NFR Design §1, §2, §3).

The three named bounds live here, ordered so the platform timeout never wins:

1. page-count guard, top of loop        -> PAGE_LIMIT_EXCEEDED   (never truncate, CR-01)
2. deadline guard, top of loop          -> UPSTREAM_TOO_SLOW      (P-3)
3. SDK retry exhaustion / connection    -> UPSTREAM_THROTTLED     (CR-02)

Every *decision* about the returned items -- parsing, deduping, counting -- is U-01's
`normalize_all`, which is total, so a malformed item can never reach this file as an exception. The
only things that fail a collection are the two budget bounds and an upstream that will not answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError

from dashboard.core import NormalizationResult, normalize_all
from dashboard.collector.errors import CollectorFailure, CollectorReason


@dataclass(frozen=True)
class CollectionOutcome:
    """What one collection run produced: the normalized result plus how many pages it took."""

    result: NormalizationResult
    pages: int


def collect_all_resources(
    client: object,
    page_limit: int,
    remaining_ms: Callable[[], int],
    deadline_safety_ms: int,
) -> CollectionOutcome:
    """Walk every page of `get_resources`, then hand the raw items to U-01 to normalize.

    `remaining_ms` is `context.get_remaining_time_in_millis` (injected so tests can drive it). The
    deadline is checked *before starting a page*, so we stop with a named reason while there is
    still budget to build the failure result and write the log -- never mid-request where the
    platform timeout would win (NFR Design §2).
    """
    raw: list[dict[str, object]] = []
    pages = 0
    token: str | None = None

    while True:
        pages += 1
        if pages > page_limit:
            raise CollectorFailure(CollectorReason.PAGE_LIMIT_EXCEEDED)
        if remaining_ms() <= deadline_safety_ms:
            raise CollectorFailure(CollectorReason.UPSTREAM_TOO_SLOW)

        try:
            kwargs = {"PaginationToken": token} if token else {}
            page = client.get_resources(**kwargs)  # type: ignore[attr-defined]
        except (ClientError, BotoCoreError) as exc:
            # Retries are exhausted by the time botocore surfaces these (standard mode, §1), so an
            # SDK-level give-up becomes a *named* collector failure rather than a raw exception.
            raise CollectorFailure(CollectorReason.UPSTREAM_THROTTLED) from exc

        raw.extend(page.get("ResourceTagMappingList", []))
        token = page.get("PaginationToken") or None
        if not token:
            break

    return CollectionOutcome(result=normalize_all(raw), pages=pages)
