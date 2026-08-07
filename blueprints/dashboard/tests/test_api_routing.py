"""`route` is a closed allowlist over arbitrary strings (AR-01, SEC-5) -- a genuine property.

No input outside the route table reaches a view; every valid route resolves; a tag_key outside
REQUIRED_TAGS is a 404, not a 400.

**Updated by the FR-9/FR-10 increment**, and worth noting how: adding the four cost/usage routes made
the property below fail, because Hypothesis generated one of the new paths and found it resolving while
`_KNOWN` still listed only the original five. That is the property working as intended -- widening the
allowlist is exactly the kind of change it exists to force someone to declare. `_KNOWN` is now the
single list a reviewer reads to know the whole surface.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from dashboard.core import REQUIRED_TAGS
from dashboard.api import routing

_KNOWN = {
    "/api/inventory",
    "/api/tag-gaps",
    "/api/status",
    "/api/health",
    # FR-9 / FR-10 (A4.1): these read the per-section cost/telemetry objects rather than the
    # inventory snapshot, so `route` returns a SectionRoute for them instead of a Snapshot view.
    "/api/cost/summary",
    "/api/cost/breakdown",
    "/api/usage/models",
    "/api/usage/quality",
} | {f"/api/groups/{t}" for t in REQUIRED_TAGS}


@given(path=st.text())
def test_unknown_get_paths_never_resolve(path: str) -> None:
    if path not in _KNOWN:
        assert routing.route("GET", path) is None


@given(method=st.text().filter(lambda m: m != "GET"), path=st.sampled_from(sorted(_KNOWN)))
def test_non_get_methods_never_resolve(method: str, path: str) -> None:
    assert routing.route(method, path) is None


def test_known_routes_resolve() -> None:
    for path in _KNOWN:
        assert routing.route("GET", path) is not None


def test_health_returns_sentinel() -> None:
    assert routing.route("GET", "/api/health") == routing.HEALTH


def test_invalid_tag_key_is_404() -> None:
    assert routing.route("GET", "/api/groups/cornell:nonsense") is None


def test_section_routes_resolve_to_a_section_marker_not_a_snapshot_view() -> None:
    """The dispatch distinction: a section route must not be called with a Snapshot."""
    from dashboard.api.sections import SectionRoute

    for path in ("/api/cost/summary", "/api/cost/breakdown", "/api/usage/models", "/api/usage/quality"):
        assert isinstance(routing.route("GET", path), SectionRoute)


def test_partial_section_paths_are_404() -> None:
    """Prefix matching would be a hole -- these are exact-match entries in a dict, and stay so."""
    for path in ("/api/cost", "/api/cost/", "/api/usage", "/api/usage/", "/api/cost/summary/x"):
        assert routing.route("GET", path) is None
    assert routing.route("GET", "/api/groups/") is None


def test_valid_tag_key_resolves_to_callable() -> None:
    view = routing.route("GET", f"/api/groups/{REQUIRED_TAGS[0]}")
    assert callable(view)
