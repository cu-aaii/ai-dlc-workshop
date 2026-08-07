"""Derived views over a snapshot -- component C-05 (BR-01, BR-05, BR-06, BR-07).

Pure. No AWS SDK, no network, no filesystem, no clock, no environment read, no logging. `now` and
`stale_after` arrive as arguments; nothing here reads a clock, which is what makes staleness -- a
*server-side* judgement -- testable without waiting for time to pass, and what makes P10
assertable at all.

`has_required_tag` is the single presence predicate. Both `group_by_tag` and `classify_tag_gaps`
consult it, and nothing else may re-derive it: if each implemented its own version they would
drift, and the dashboard would contradict itself -- a resource sitting in the "missing owner" group
while the tag-gap view calls it compliant. P9 asserts that cannot happen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from dashboard.core.model import REQUIRED_TAGS, ResourceRecord, Snapshot

__all__ = [
    "Freshness",
    "Group",
    "GroupingResult",
    "IncompleteRecord",
    "TagGapReport",
    "classify_tag_gaps",
    "evaluate_freshness",
    "group_by_tag",
    "has_required_tag",
]


class Freshness(StrEnum):
    """How much a snapshot's age can be trusted (BR-07).

    Three-valued rather than a boolean, because reporting `FRESH` about data whose provenance is
    broken is the most dangerous thing this unit could say.
    """

    FRESH = "fresh"
    STALE = "stale"
    INVALID = "invalid"
    """`collected_at` is in the future -- impossible in a correct system, so a fault rather than an
    age. U-02 maps this to a **503**, not a 200: it is not a state of the world."""


@dataclass(frozen=True)
class Group:
    """One group of records sharing a value for some tag key.

    `value is None` is the **missing** group -- records that lack the key per BR-01, which covers
    absent keys, wrong-case keys, and empty values alike.
    """

    value: str | None
    resources: tuple[ResourceRecord, ...]


@dataclass(frozen=True)
class GroupingResult:
    """A snapshot grouped by one tag key (BR-05).

    `groups` is **ordered**, and the order is part of the value: two results with the same groups
    in a different sequence are not equal. That is what makes P6 (idempotence including order) and
    P2 (byte-level serialization determinism) reachable.

    `total` is stored rather than recomputed so P3 has something to assert against.
    """

    tag_key: str
    groups: tuple[Group, ...]
    total: int


@dataclass(frozen=True)
class IncompleteRecord:
    """A record together with which required tags it lacks."""

    record: ResourceRecord
    missing_tags: tuple[str, ...]


@dataclass(frozen=True)
class TagGapReport:
    """Which resources lack which required tags (BR-06).

    `complete` and `incomplete` partition the snapshot's records: every record appears in exactly
    one, and their sizes sum to the total.
    """

    complete: tuple[ResourceRecord, ...]
    incomplete: tuple[IncompleteRecord, ...]


def has_required_tag(record: ResourceRecord, key: str) -> bool:
    """Whether `record` carries usable tag `key` (BR-01). **The single presence predicate.**

    Two halves, both deliberate and both looking harsher than necessary:

    **Exact key match, no case folding.** AWS tag keys really are case-sensitive, so a resource
    tagged `Cornell:Owner` is genuinely invisible to the case-sensitive cost and inventory tooling
    this whole convention exists to feed. Reporting it as tagged would be reporting something false
    in order to be kind.

    **A present-but-empty value counts as missing.** A resource tagged `cornell:owner=""` is exactly
    as unattributable as one with no owner tag, and treating it as compliant would make the
    tag-gap view lie in the one way that matters.
    """
    value = record.tags.get(key)
    return value is not None and value.strip() != ""


def group_by_tag(snapshot: Snapshot, tag_key: str) -> GroupingResult:
    """Group a snapshot's records by their value for `tag_key` (BR-05).

    `tag_key` is validated against `REQUIRED_TAGS`, a closed allowlist (PAT-8). This is the only
    user-supplied value reaching U-01, and it is why U-02's input-validation surface is nearly
    structural rather than a layer to write and maintain.

    **No record is ever dropped.** Records lacking the key land in the `value=None` group, which is
    what makes P3's sum invariant hold and what stops US-03 from silently under-reporting -- the
    failure mode of a naive group-by that skips missing keys.

    Ordering (Q8): member count descending, then value ascending, with the missing group pinned
    **last** regardless of its size. Pinning rather than sorting it stops the group from changing
    position as counts shift. The cost is that the group a viewer most needs to act on sits at the
    bottom; US-04's dedicated tag-gap view is the mitigation, since this is the inventory grouping
    and not the gap report.
    """
    if tag_key not in REQUIRED_TAGS:
        raise ValueError(f"tag_key must be one of REQUIRED_TAGS, got {tag_key!r}")

    present: dict[str, list[ResourceRecord]] = {}
    missing: list[ResourceRecord] = []

    for record in snapshot.resources:
        if has_required_tag(record, tag_key):
            present.setdefault(record.tags[tag_key], []).append(record)
        else:
            missing.append(record)

    groups = [
        Group(value=value, resources=tuple(records))
        for value, records in sorted(
            present.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]
    # Empty groups cannot arise -- a key is only created when a record lands in it -- so the
    # missing group is appended only when it has members, keeping "no empty groups" true (P4).
    if missing:
        groups.append(Group(value=None, resources=tuple(missing)))

    return GroupingResult(
        tag_key=tag_key,
        groups=tuple(groups),
        total=len(snapshot.resources),
    )


def classify_tag_gaps(
    snapshot: Snapshot,
    required: Sequence[str] = REQUIRED_TAGS,
) -> TagGapReport:
    """Split records into fully-tagged and incompletely-tagged (BR-06).

    `missing_tags` reports **which** tags are absent, not merely that some are: US-04 is only
    actionable with the specifics.

    Iterating `required` rather than the record's own keys is what makes `missing_tags`
    deterministically ordered, which P2 needs.

    Shares `has_required_tag` with `group_by_tag` by construction, which is what makes P9 true
    rather than coincidental.
    """
    complete: list[ResourceRecord] = []
    incomplete: list[IncompleteRecord] = []

    for record in snapshot.resources:
        missing = tuple(key for key in required if not has_required_tag(record, key))
        if missing:
            incomplete.append(IncompleteRecord(record=record, missing_tags=missing))
        else:
            complete.append(record)

    return TagGapReport(complete=tuple(complete), incomplete=tuple(incomplete))


def evaluate_freshness(
    collected_at: datetime,
    now: datetime,
    stale_after: timedelta,
) -> Freshness:
    """Judge a snapshot's age (BR-07). **Total** -- no input makes this raise.

    Totality is deliberate: this sits on the read path, and an exception here would turn a
    data-provenance fault into an unexplained 500 rather than the deliberate 503 U-02 maps
    `INVALID` to.

    **The `INVALID` check must come first.** A future `collected_at` gives a negative age, which is
    trivially under any threshold and would therefore satisfy the `FRESH` comparison -- which is
    precisely the bug Q6 exists to prevent and precisely what P10 catches.

    `stale_after` is passed in rather than read from config, so the threshold stays a stack
    parameter and this module stays environment-free. Its default is set at the call site as a
    multiple of the refresh interval (3x), not as a bare duration: the interval is itself a stack
    parameter, and a fixed threshold would be silently invalidated the moment someone changed it.
    """
    if collected_at > now:
        return Freshness.INVALID
    if now - collected_at <= stale_after:
        return Freshness.FRESH
    return Freshness.STALE


def _reference_group_by_tag(snapshot: Snapshot, tag_key: str) -> GroupingResult:
    """Deliberately naive reference implementation of BR-05. **Test-only oracle for P5.**

    Written from BR-05's prose rather than from `group_by_tag`, and it must stay that way. If this
    is ever produced by copying the real implementation, P5 becomes a tautology that passes forever
    while asserting nothing -- and **no tool can detect that** (NFR-T5). It is the one place in this
    unit where a reviewer's attention is the only control.

    Quadratic on purpose: it rescans the whole record list once per distinct value. Excluded from
    NFR-P2's 10,000-record check, where it would measure the test double rather than the
    implementation.

    Not exported from the package (`__all__` in `__init__.py` omits it), so it cannot be reached
    from production code and used as if it were the real thing.
    """
    if tag_key not in REQUIRED_TAGS:
        raise ValueError(f"tag_key must be one of REQUIRED_TAGS, got {tag_key!r}")

    records = list(snapshot.resources)

    # Distinct values, discovered by scanning and appending -- no dict, no setdefault.
    distinct: list[str] = []
    for record in records:
        if has_required_tag(record, tag_key):
            value = record.tags[tag_key]
            if value not in distinct:
                distinct.append(value)

    # One full rescan of every record per distinct value.
    built: list[Group] = []
    for value in distinct:
        members = [
            record
            for record in records
            if has_required_tag(record, tag_key) and record.tags[tag_key] == value
        ]
        built.append(Group(value=value, resources=tuple(members)))

    built = sorted(built, key=lambda group: (-len(group.resources), group.value or ""))

    absent = [record for record in records if not has_required_tag(record, tag_key)]
    if absent:
        built.append(Group(value=None, resources=tuple(absent)))

    return GroupingResult(tag_key=tag_key, groups=tuple(built), total=len(records))
