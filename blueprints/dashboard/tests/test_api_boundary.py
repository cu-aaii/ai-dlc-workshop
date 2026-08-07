"""The outer error boundary and the total handler (NFR Design §6; R-2, AR-06, AR-08).

Anything escaping the route table + loader becomes a generic 503 with no internals -- so a bug in a
view cannot turn into an unstructured 500 that loses the body `status`.
"""

from __future__ import annotations

import json
from typing import Any

from dashboard.api import handler as H
from dashboard.api.config import ApiConfig

CONFIG = ApiConfig.from_env({"SNAPSHOT_BUCKET": "b"})


def _event(method: str, path: str) -> dict[str, Any]:
    return {"requestContext": {"http": {"method": method, "path": path}}}


class ExplodingS3:
    """A non-ClientError from S3 is *not* caught by the loader; it must hit the outer boundary."""

    def get_object(self, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("boom -- unexpected internal error")


def test_unexpected_error_becomes_generic_503() -> None:
    r = H.run(_event("GET", "/api/inventory"), config=CONFIG, s3_client=ExplodingS3())
    assert r["statusCode"] == 503
    assert json.loads(r["body"]) == {"status": "error"}  # no internals leaked


def test_unknown_route_is_404_without_touching_s3() -> None:
    r = H.run(_event("GET", "/api/nope"), config=CONFIG, s3_client=ExplodingS3())
    assert r["statusCode"] == 404  # ExplodingS3 never consulted -> route rejected first


def test_health_needs_no_s3() -> None:
    r = H.run(_event("GET", "/api/health"), config=CONFIG, s3_client=ExplodingS3())
    assert r["statusCode"] == 200 and json.loads(r["body"]) == {"status": "ok"}


def test_malformed_event_is_handled_not_raised() -> None:
    # No requestContext at all: method/path resolve to None -> 404, never an escape.
    r = H.run({}, config=CONFIG, s3_client=ExplodingS3())
    assert r["statusCode"] == 404
