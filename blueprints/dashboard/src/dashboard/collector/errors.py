"""The collector's named failure modes (NFR Design §3; CR-01, CR-02, P-3).

Three named stop conditions, one enum, no two sharing a code -- so a log line unambiguously says
which bound fired, which is what CR-04's logging and the R-10 runbook depend on. The platform's
120 s Lambda timeout is a fourth, *unnamed* bound the design keeps from ever winning by ordering
these three ahead of it (NFR Design §2, §3).

Like U-01's errors, the reason is a closed `StrEnum` and the exception carries **no ARN and no tag
value** -- only the code. `CollectorFailure` is deliberately *not* a `CoreError`: U-01's hierarchy
is about unreadable data, this is about an upstream/budget failure, and conflating them would let an
`except CoreError` in the API accidentally catch a collector concern.
"""

from __future__ import annotations

from enum import StrEnum


class CollectorReason(StrEnum):
    """Why a collection run failed. The value is the reason code logged and counted."""

    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    """More pages than `PAGE_LIMIT` -- we never truncate (CR-01), we fail loudly instead."""

    UPSTREAM_TOO_SLOW = "UPSTREAM_TOO_SLOW"
    """The internal deadline (derived from the remaining Lambda budget) was hit before the next
    page (P-3). Raised so the failure has a name before the platform timeout can produce an
    unattributable one."""

    UPSTREAM_THROTTLED = "UPSTREAM_THROTTLED"
    """The SDK exhausted its standard-mode retries, or the connection failed (CR-02)."""


class CollectorFailure(Exception):
    """A collection run that could not complete. Carries a `CollectorReason` and nothing else."""

    def __init__(self, reason: CollectorReason) -> None:
        self.reason = reason
        super().__init__(reason.value)
