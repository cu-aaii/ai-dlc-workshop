"""`route` is a closed allowlist over arbitrary strings (AR-01, SEC-5) -- a genuine property.

No input outside the five-route table reaches a view; every valid route resolves; a tag_key outside
REQUIRED_TAGS is a 404, not a 400.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from dashboard.core import REQUIRED_TAGS
from dashboard.api import routing

_KNOWN = {"/api/inventory", "/api/tag-gaps", "/api/status", "/api/health"} | {
    f"/api/groups/{t}" for t in REQUIRED_TAGS
}


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
    assert routing.route("GET", "/api/groups/") is None


def test_valid_tag_key_resolves_to_callable() -> None:
    view = routing.route("GET", f"/api/groups/{REQUIRED_TAGS[0]}")
    assert callable(view)
