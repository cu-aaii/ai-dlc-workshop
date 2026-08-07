"""Cost collector failure vocabulary (COST-05, COST-07).

Mirrors `collector/errors.py`: a closed `StrEnum` reason, and a message that carries **no** account
id, ARN, or tag value -- a collector message reaches a log group, and NFR-S1's rule is structural.

`ACCESS_DENIED` is separate from the other reasons on purpose, and the distinction is operational
rather than cosmetic. Every other reason here is **retry-shaped**: the next scheduled run may well
succeed. `ACCESS_DENIED` is not. This deployment sits in a *linked* AWS account, and cost allocation
tag activation is a payer/management-account capability -- measured, not assumed (amendment A3.3:
`ListCostAllocationTags` returns *"Linked account doesn't have access to cost allocation tags"*).
Retrying tomorrow, and every tomorrow after, fails identically. It needs a human in another team.
That is why it gets its own alarm in the template rather than sharing one with transient failures.
"""

from __future__ import annotations

from enum import StrEnum


class CostReason(StrEnum):
    """Why a cost collection run failed."""

    CALL_BUDGET_EXCEEDED = "call_budget_exceeded"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    UPSTREAM_THROTTLED = "upstream_throttled"
    ACCESS_DENIED = "access_denied"


class CostFailure(Exception):
    """A cost collection run failed. Carries only the reason."""

    def __init__(self, reason: CostReason) -> None:
        super().__init__(reason.value)
        self.reason = reason
