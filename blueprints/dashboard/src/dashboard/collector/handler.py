"""C-01 entrypoint: collect, build, write one snapshot (CR-01..CR-06; NFR Design §2..§5).

The orchestration only. Every derivation is U-01's; every bound is `tagging.py`'s; logging and
metrics are `shared/`. What is genuinely decided here is the *shape* of a run:

- the clock is read **exactly twice**, both here, so the snapshot's `collected_at` and the duration
  metric cannot disagree (U-01 forbids itself a clock; this is where "now" enters the system);
- the write is a single `PutObject` of a freshly built snapshot -- complete-or-fail, no
  read-modify-write, so on any failure the previous snapshot survives (CR-05, A-4);
- a `CollectorFailure` is logged with its reason, emitted as a failure metric, and **re-raised** --
  the invocation fails, OR-01 alarms, the next tick retries, and staleness stays visible rather
  than being papered over by a silent success (Q6).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import boto3

from dashboard.core import build_snapshot, serialize_snapshot
from dashboard.collector.config import CollectorConfig
from dashboard.collector.errors import CollectorFailure
from dashboard.collector.tagging import CollectionOutcome, collect_all_resources
from dashboard.shared.emf import emit_metric
from dashboard.shared.logging_json import get_logger

LOG = get_logger("dashboard.collector")

_UTC_NOW: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def run(
    *,
    config: CollectorConfig,
    tagging_client: object,
    s3_client: object,
    remaining_ms: Callable[[], int],
    clock: Callable[[], datetime] = _UTC_NOW,
) -> None:
    """The testable core: all dependencies injected, no environment or AWS bootstrapping.

    Returns nothing -- success *is* the written object (CR-05). Raises `CollectorFailure` on any
    named bound, after logging and emitting the failure metric.
    """
    started = clock()
    try:
        outcome = collect_all_resources(
            tagging_client, config.page_limit, remaining_ms, config.deadline_safety_ms
        )
    except CollectorFailure as exc:
        LOG.error("collection failed", extra={"reason": exc.reason.value})
        emit_metric(
            {"CollectorFailure": (1, "Count")},
            dimensions={"function": "collector", "outcome": "failure", "reason": exc.reason.value},
        )
        raise

    collected_at = clock()
    snapshot = build_snapshot(outcome.result, collected_at=collected_at)
    # One PutObject of the fully built snapshot. No GetObject-then-PutObject anywhere on this path.
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=config.snapshot_bucket,
        Key=config.snapshot_key,
        Body=serialize_snapshot(snapshot),
        ContentType="application/json",
    )

    _log_skipped(outcome.result)
    _emit_success(outcome, duration_s=(collected_at - started).total_seconds())


def _log_skipped(result: Any) -> None:
    """Log skipped-item counts by reason code (CR-04).

    Per *reason code and count*, never per ARN: U-01's `normalize_all` deliberately discards the
    ARNs of skipped items rather than carrying them (its no-leak design), so they are not available
    here -- and the reason codes are enum values (`arn` / `tags`), never tag values. This is the
    one place the collector's logging differs from the functional-design pseudocode, and it differs
    in the safe direction.
    """
    for reason, count in result.skipped_reasons.items():
        LOG.warning("skipped resources", extra={"reason": reason, "count": count})


def _emit_success(outcome: CollectionOutcome, *, duration_s: float) -> None:
    r = outcome.result
    emit_metric(
        {
            "CollectionDuration": (duration_s, "Seconds"),
            "PagesFetched": (outcome.pages, "Count"),
            "ResourcesCollected": (len(r.records), "Count"),
            "RawReturned": (r.raw_returned, "Count"),
            "SkippedCount": (r.skipped_count, "Count"),
            "DuplicatesRemoved": (r.duplicates_removed, "Count"),
        },
        dimensions={"function": "collector", "outcome": "success"},
    )


def handler(event: dict[str, Any], context: Any) -> None:
    """AWS Lambda entrypoint. Bootstraps config + clients, then delegates to `run`.

    `remaining_ms` comes from the Lambda context; on a hand invoke without one it falls back to a
    large constant so the deadline guard never trips locally.
    """
    config = CollectorConfig.from_env()
    remaining_ms: Callable[[], int] = (
        context.get_remaining_time_in_millis if context is not None else (lambda: 10**9)
    )
    session = boto3.session.Session()
    tagging_client = session.client("resourcegroupstaggingapi", config=config.botocore_config())
    s3_client = session.client("s3")
    run(
        config=config,
        tagging_client=tagging_client,
        s3_client=s3_client,
        remaining_ms=remaining_ms,
    )
