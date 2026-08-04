"""The closed route table (AR-01, SEC-5). A view is chosen *before* any S3 access.

Five routes, all `GET`, all under `/api` (the API owns the prefix so CloudFront forwards `/api/*`
verbatim -- Infra Design Part A2 finding 4). Anything else -- wrong method, unknown path, or a
`{tag_key}` outside `REQUIRED_TAGS` -- returns `None`, which the handler maps to a 404 with no S3
read. The `{tag_key}` allowlist is the only user-supplied value that reaches the system, and it is
validated here against U-01's `REQUIRED_TAGS`, so the input-validation surface is structural.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dashboard.core import REQUIRED_TAGS, Snapshot
from dashboard.api import views

# A view maps a Snapshot to the response's `data`. The health sentinel is handled specially by the
# handler (it does no S3 read), so it needs no snapshot.
View = Callable[[Snapshot], Any]

HEALTH = "health"
"""Sentinel returned for /api/health so the handler can skip the S3 read (AR-08)."""

_GROUPS_PREFIX = "/api/groups/"

_STATIC: dict[str, View] = {
    "/api/inventory": views.inventory,
    "/api/tag-gaps": views.tag_gaps,
    "/api/status": views.status,
}


def route(method: str | None, path: str | None) -> View | str | None:
    """Resolve `(method, path)` to a view, the `HEALTH` sentinel, or `None` (→ 404).

    Returns before any S3 access, so an unknown route never touches storage (AR-01).
    """
    if method != "GET" or not path:
        return None
    if path == "/api/health":
        return HEALTH
    static = _STATIC.get(path)
    if static is not None:
        return static
    if path.startswith(_GROUPS_PREFIX):
        tag_key = path[len(_GROUPS_PREFIX):]
        if tag_key in REQUIRED_TAGS:
            return lambda snapshot: views.groups(snapshot, tag_key)
        return None  # a tag_key outside the allowlist is a 404, not a 400 -- closed table
    return None
