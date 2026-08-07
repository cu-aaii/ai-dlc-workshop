"""C-03 entrypoint: total by structure (NFR Design §6; R-2, AR-01..AR-06, AR-08).

`handler` cannot let anything escape as an unstructured 500 -- API Gateway would then drop AR-03's
body `status`, which the UI and C-09's alarms both read. Totality is a property of the enclosing
shape, not of per-branch discipline:

1. unknown routes 404 **before any S3 access** (the closed table in `routing.py`);
2. a known route classifies the S3 read into the six states (`loading.py` + `shaping.py`);
3. **any** exception escaping the above is caught by one top-level handler and mapped to a generic
   503 with no internals (AR-06).

The seam named at NFR Design §6: event parsing happens **inside** the guard, so a malformed event
becomes a clean 503 rather than escaping before the `try`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import boto3

from dashboard.api import routing, section_views, shaping
from dashboard.api.config import ApiConfig
from dashboard.api.loading import load_current_snapshot
from dashboard.api.sections import SectionRoute, load_section
from dashboard.shared.logging_json import get_logger

LOG = get_logger("dashboard.api")

_UTC_NOW: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def _method_path(event: dict[str, Any]) -> tuple[str | None, str | None]:
    http = event.get("requestContext", {}).get("http", {})
    return http.get("method"), (http.get("path") or event.get("rawPath"))


def run(
    event: dict[str, Any],
    *,
    config: ApiConfig,
    s3_client: object,
    clock: Callable[[], datetime] = _UTC_NOW,
) -> dict[str, Any]:
    """The testable core: dependencies injected, one outer error boundary (AR-06)."""
    try:
        method, path = _method_path(event)  # inside the guard -- the §6 seam
        view = routing.route(method, path)
        if view is None:
            return shaping.error_response(404)
        if isinstance(view, SectionRoute):
            return _serve_section(view, config=config, s3_client=s3_client)
        if isinstance(view, str):  # the HEALTH sentinel; narrows `view` to a View below
            return shaping.health()
        outcome = load_current_snapshot(s3_client, config.snapshot_bucket, config.snapshot_key)
        return shaping.shape(outcome, view, clock(), config.stale_after)
    except Exception:
        # Generic 503, no internals. One place, so a new route cannot undo AR-06 by forgetting it.
        LOG.exception("unhandled error in api handler")
        return shaping.error_response(503)


def _serve_section(
    route: SectionRoute, *, config: ApiConfig, s3_client: object
) -> dict[str, Any]:
    """Serve one FR-9/FR-10 route.

    Loads **only** the sections that route needs, and each load is total -- so an absent cost object
    does not affect a usage response, and vice versa. That per-section independence is a requirement
    (FR-9.5.5, US-16/US-20), not an optimisation: a viewer must be able to see cost while usage is
    uninstrumented.

    Still inside `run`'s outer boundary, so a fault here becomes the same generic 503 (AR-06).
    """
    if route in (SectionRoute.COST_SUMMARY, SectionRoute.COST_BREAKDOWN):
        cost = load_section(s3_client, config.snapshot_bucket, config.cost_key)
        if route is SectionRoute.COST_SUMMARY:
            body = section_views.cost_summary(cost)
            # US-19 rides on the summary: it needs both sections, so it reports the worse state.
            telemetry = load_section(
                s3_client, config.snapshot_bucket, config.telemetry_key
            )
            body["per_task"] = section_views.cost_per_completed_task(cost, telemetry)
            return shaping.section_response(body)
        return shaping.section_response(section_views.cost_breakdown(cost))

    telemetry = load_section(s3_client, config.snapshot_bucket, config.telemetry_key)
    if route is SectionRoute.USAGE_MODELS:
        return shaping.section_response(
            section_views.usage_models(telemetry, config.model_rates)
        )
    return shaping.section_response(section_views.usage_quality(telemetry))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint. Bootstraps config + client, then delegates to `run`."""
    config = ApiConfig.from_env()
    s3_client = boto3.session.Session().client("s3")
    return run(event, config=config, s3_client=s3_client)
