"""The four data views: Snapshot -> JSON-serializable data (AR-04, delegating to U-01).

Each builder returns only the `data` field of the response envelope; `counts`, `collected_at` and
`freshness` are added by `shaping.py` uniformly. None of these iterates records to make a decision --
grouping and gap classification are U-01 calls; inventory and status are shaping of already-derived
fields.
"""

from __future__ import annotations

from typing import Any

from dashboard.core import (
    ResourceRecord,
    Snapshot,
    classify_tag_gaps,
    group_by_tag,
)


def resource_dict(record: ResourceRecord) -> dict[str, Any]:
    """One resource as JSON. The `data-testid` / UI `ResourceRow` shape."""
    return {
        "arn": record.arn,
        "service": record.service,
        "resource_type": record.resource_type,
        "region": record.region,
        "tags": dict(record.tags),
    }


def inventory(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Every resource (AR-04; renders US-01/US-02 inventory)."""
    return [resource_dict(r) for r in snapshot.resources]


def groups(snapshot: Snapshot, tag_key: str) -> dict[str, Any]:
    """Grouped counts by `tag_key` (US-03). Ordering is U-01's -- the UI must not re-sort.

    Compact by design: the grouping view shows a table of value + count + a proportional bar, not
    the members, so this returns counts. The missing group is `value: null` pinned last.
    """
    result = group_by_tag(snapshot, tag_key)
    return {
        "tag_key": result.tag_key,
        "total": result.total,
        "groups": [{"value": g.value, "count": len(g.resources)} for g in result.groups],
    }


def tag_gaps(snapshot: Snapshot) -> dict[str, Any]:
    """Which resources lack which required tags (US-04), with the specifics per record."""
    report = classify_tag_gaps(snapshot)
    return {
        "complete_count": len(report.complete),
        "incomplete": [
            {
                "arn": ir.record.arn,
                "service": ir.record.service,
                "region": ir.record.region,
                "missing_tags": list(ir.missing_tags),
            }
            for ir in report.incomplete
        ],
    }


def status(snapshot: Snapshot) -> dict[str, Any]:
    """Provenance detail beyond the envelope counts: the skip breakdown and schema version.

    Freshness and the three counts already ride the envelope (`shaping.py`); this adds only what a
    dedicated status view shows on top -- why things were skipped, and the schema the data was
    written at.
    """
    return {
        "schema_version": snapshot.schema_version,
        "skipped_reasons": dict(snapshot.skipped_reasons),
    }
