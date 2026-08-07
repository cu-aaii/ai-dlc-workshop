"""Per-section loading and shaping for the cost and telemetry views (FR-9.5, FR-10, A4.1).

**Why sections rather than one snapshot.** The store holds three objects with three owners --
`inventory/current.json` (hourly), `telemetry/current.json` (hourly), `cost/current.json` (daily) --
because a single object with three writers on two cadences would force a read-modify-write, which the
collectors forbid (amendment A4.1). The consequence lands here: there is **no single snapshot age**, so
every section carries its own `collected_at` and its own state.

**One section failing degrades only that section.** A viewer must be able to see cost while usage is
uninstrumented, and vice versa (US-16/US-20). So nothing here raises: an unreadable section becomes a
state, exactly as `loading.py` does for the inventory snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SectionRoute(StrEnum):
    """The four new read routes (plan Q6). A closed set, like the inventory route table."""

    COST_SUMMARY = "cost_summary"
    COST_BREAKDOWN = "cost_breakdown"
    USAGE_MODELS = "usage_models"
    USAGE_QUALITY = "usage_quality"


class SectionState(StrEnum):
    """Why a section has, or does not have, data.

    Mirrors `TelemetryState` deliberately: the same four-way distinction NFR-T7 requires, applied at
    section granularity. `ABSENT` is "never collected", which is not the same as "collected and empty".
    """

    OK = "ok"
    ABSENT = "absent"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class SectionOutcome:
    """A loaded section, or the reason there isn't one. Total -- never raises."""

    state: SectionState
    payload: dict[str, Any] | None = None

    @property
    def collected_at(self) -> str | None:
        if self.payload is None:
            return None
        value = self.payload.get("collected_at")
        return str(value) if value is not None else None


def load_section(s3_client: Any, bucket: str, key: str) -> SectionOutcome:
    """Load and parse one section object. Total by construction.

    Catches by exception *type* rather than by string matching, following U-01's PAT-7: a missing key
    is `ABSENT`, anything else that goes wrong is `UNREADABLE`, and neither propagates.
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        raw = response["Body"].read()
    except Exception as exc:  # noqa: BLE001 -- totality is the point; see the docstring
        name = type(exc).__name__
        if "NoSuchKey" in name or "404" in str(getattr(exc, "response", "")):
            return SectionOutcome(state=SectionState.ABSENT)
        return SectionOutcome(state=SectionState.UNREADABLE)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return SectionOutcome(state=SectionState.UNREADABLE)
    if not isinstance(payload, dict):
        return SectionOutcome(state=SectionState.UNREADABLE)
    return SectionOutcome(state=SectionState.OK, payload=payload)
