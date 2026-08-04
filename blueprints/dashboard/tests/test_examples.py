"""Example-based tests for U-01 Domain Core (PBT-10: complement the properties, do not duplicate).

Three jobs the property suite cannot do:

1. **Pin the specific cases the design argues about.** A property says grouping is consistent; only
   an example says `arn:aws:s3:::my-bucket` yields region `"global"` and type `"s3"`. When someone
   later "simplifies" `_resource_type`, this is the test that names what broke.
2. **Assert the `__eq__`/`__hash__` contract** that P1, P2 and P6 silently depend on.
3. **Hold NFR-P2's 10,000-record complexity check** -- deliberately *not* a Hypothesis property. At
   `max_examples=100` a generated 10k-record snapshot would dominate the pre-push gate for a check
   that needs no randomness.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import serialized_with_unknown_key

from dashboard.core import (
    REQUIRED_TAGS,
    SCHEMA_VERSION,
    Freshness,
    IncompatibleSchema,
    InvalidSnapshot,
    MalformedResource,
    NormalizationResult,
    ResourceRecord,
    SkipReason,
    Snapshot,
    build_snapshot,
    classify_tag_gaps,
    deserialize_snapshot,
    evaluate_freshness,
    group_by_tag,
    has_required_tag,
    normalize_all,
    normalize_resource,
    serialize_snapshot,
)

NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
FULL_TAGS = {key: "value" for key in REQUIRED_TAGS}


def record(arn: str = "arn:aws:s3:::bucket", **tags: str) -> ResourceRecord:
    return ResourceRecord(
        arn=arn, service="s3", resource_type="s3", region="global", tags=tags
    )


def snapshot_of(*records: ResourceRecord, collected_at: datetime = NOW) -> Snapshot:
    return build_snapshot(
        NormalizationResult(
            records=records,
            raw_returned=len(records),
            skipped_count=0,
            skipped_reasons={},
            duplicates_removed=0,
        ),
        collected_at=collected_at,
    )


# --------------------------------------------------------------------------------------------
# BR-03 -- region and resource type derivation
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arn", "region", "resource_type"),
    [
        # An S3 bucket ARN has an empty region AND no type prefix -- both edge cases at once.
        ("arn:aws:s3:::my-bucket", "global", "s3"),
        ("arn:aws:iam::123456789012:role/my-role", "global", "role"),
        ("arn:aws:cloudfront::123456789012:distribution/E123", "global", "distribution"),
        ("arn:aws:lambda:us-east-1:123456789012:function:my-fn", "us-east-1", "function"),
        # The regression case: the type separator here is ":" and the *id* then contains "/", so a
        # fixed "/"-first preference yields "log-group:" with the colon attached. Caught by running
        # the code against real ARN shapes, not by reasoning about them.
        ("arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/x", "us-east-1", "log-group"),
    ],
)
def test_br03_region_and_type_derivation(arn, region, resource_type):
    """BR-03: an empty region segment becomes `"global"`; type comes from the resource prefix.

    The S3 row is the important one. Its ARN has *both* an empty region and no type separator, so it
    exercises the `"global"` mapping and the fall-back-to-service branch of `_resource_type`
    together -- the combination a reader of the dashboard would most notice if it broke, since it
    would render as a blank region and a bucket name in the type column.
    """
    parsed = normalize_resource({"ResourceARN": arn, "Tags": []})
    assert parsed.region == region
    assert parsed.resource_type == resource_type


# --------------------------------------------------------------------------------------------
# BR-01 -- tag presence
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tags", "present"),
    [
        ({"cornell:owner": "abc123"}, True),
        ({"cornell:owner": ""}, False),
        ({"cornell:owner": "   "}, False),
        ({"cornell:owner": "\t\n"}, False),
        ({"Cornell:Owner": "abc123"}, False),
        ({"CORNELL:OWNER": "abc123"}, False),
        ({}, False),
    ],
)
def test_br01_presence_rules(tags, present):
    """BR-01: exact key match, and a value with at least one non-whitespace character.

    The empty-string and mis-cased rows are the whole point. A resource tagged `cornell:owner=""` is
    exactly as unattributable as one with no owner tag, and a resource tagged `Cornell:Owner` is
    genuinely invisible to the case-sensitive tooling this convention feeds -- so reporting either as
    compliant would be reporting something false.
    """
    assert has_required_tag(record(**tags), "cornell:owner") is present


def test_br01_is_shared_by_grouping_and_classification():
    """BR-01 + P9: a mis-cased key is missing in *both* views, not one.

    P9 asserts this over generated inputs; this pins the concrete case a reader would report as a
    bug ("it's tagged, why does it say missing?").
    """
    miscased = record(arn="arn:aws:s3:::a", **{"Cornell:Owner": "abc123"})
    snapshot = snapshot_of(miscased)

    grouped = group_by_tag(snapshot, "cornell:owner")
    assert [g.value for g in grouped.groups] == [None]

    report = classify_tag_gaps(snapshot)
    assert "cornell:owner" in report.incomplete[0].missing_tags


# --------------------------------------------------------------------------------------------
# BR-05 -- grouping and ordering
# --------------------------------------------------------------------------------------------


def test_br05_ordering_and_pinned_missing_group():
    """BR-05 / Q8: count descending, value ascending, missing group pinned last.

    The missing group here is the *largest*, so a naive count-descending sort would put it first.
    Pinning it last is what stops the group from moving as counts change.
    """
    snapshot = snapshot_of(
        record(arn="arn:aws:s3:::a", **{"cornell:owner": "bbb"}),
        record(arn="arn:aws:s3:::b", **{"cornell:owner": "aaa"}),
        record(arn="arn:aws:s3:::c", **{"cornell:owner": "aaa"}),
        record(arn="arn:aws:s3:::d"),
        record(arn="arn:aws:s3:::e"),
        record(arn="arn:aws:s3:::f"),
    )
    groups = group_by_tag(snapshot, "cornell:owner").groups
    assert [(g.value, len(g.resources)) for g in groups] == [
        ("aaa", 2),
        ("bbb", 1),
        (None, 3),
    ]


def test_br05_empty_snapshot_groups_to_nothing():
    """BR-05, shape 7: zero resources yields zero groups, not one empty group.

    Distinct from "no snapshot at all", which U-01 cannot represent -- that state belongs to U-02's
    `LoadOutcome`. US-06 turns on the difference, since the two render identically under a naive
    implementation and mean opposite things.
    """
    result = group_by_tag(snapshot_of(), "cornell:owner")
    assert result.groups == ()
    assert result.total == 0


# --------------------------------------------------------------------------------------------
# BR-02, BR-04 -- skipping and deduplication
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({}, SkipReason.ARN),
        ({"ResourceARN": "not-an-arn"}, SkipReason.ARN),
        ({"ResourceARN": "arn:aws:s3"}, SkipReason.ARN),
        ({"ResourceARN": "arn:aws::us-east-1:123:x"}, SkipReason.ARN),
        ({"ResourceARN": "arn:aws:s3:::b", "Tags": "nope"}, SkipReason.TAGS),
        ({"ResourceARN": "arn:aws:s3:::b", "Tags": [{"Key": 1}]}, SkipReason.TAGS),
    ],
)
def test_br02_malformed_items_raise_with_a_category_only(raw, reason):
    """BR-02 + NFR-S1: the reason is a closed-enum category, and carries no input data.

    The second assertion is the privacy one. `cornell:owner` holds a NetID, and an exception message
    can reach a log group or an error body -- so no ARN, tag key, or tag value may appear in it.
    """
    with pytest.raises(MalformedResource) as caught:
        normalize_resource(raw)
    assert caught.value.reason is reason

    rendered = f"{caught.value}{caught.value.args}"
    assert "arn:aws" not in rendered
    for fragment in ("Key", "Value", "nope", "us-east-1"):
        assert fragment not in rendered


def test_br04_last_duplicate_wins_and_is_counted():
    """BR-04: two items with one ARN are one resource; the later tags win; the collision is counted."""
    result = normalize_all(
        [
            {"ResourceARN": "arn:aws:s3:::b", "Tags": [{"Key": "cornell:owner", "Value": "first"}]},
            {"ResourceARN": "arn:aws:s3:::b", "Tags": [{"Key": "cornell:owner", "Value": "second"}]},
        ]
    )
    assert len(result.records) == 1
    assert result.records[0].tags["cornell:owner"] == "second"
    assert result.duplicates_removed == 1
    assert result.raw_returned == 2


def test_br02_one_bad_item_does_not_lose_the_good_ones():
    """BR-02 / PAT-3: the decision that stops one team's odd resource blanking everyone's view.

    Nine usable resources plus one unparseable ARN yields a snapshot of nine and a visible count of
    one -- not an exception, and not a silent nine.
    """
    items = [
        {"ResourceARN": f"arn:aws:s3:::bucket-{i}", "Tags": []} for i in range(9)
    ] + [{"ResourceARN": "broken"}]

    result = normalize_all(items)
    assert len(result.records) == 9
    assert result.skipped_count == 1
    assert result.skipped_reasons == {"arn": 1}


# --------------------------------------------------------------------------------------------
# BR-07 -- freshness
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offset_seconds", "expected"),
    [
        (-3600, Freshness.FRESH),
        (-1, Freshness.FRESH),
        (0, Freshness.FRESH),
        (+1, Freshness.INVALID),
        (+3600, Freshness.INVALID),
    ],
)
def test_br07_boundaries_including_the_future(offset_seconds, expected):
    """BR-07 / Q6: the FRESH boundary, and a future timestamp as INVALID rather than FRESH.

    The `+1` row is the one that matters. A future `collected_at` gives a negative age, which is
    trivially under any threshold -- so an implementation checking FRESH before INVALID would report
    broken-provenance data as fresh, which is the most dangerous thing this unit could say.
    """
    collected_at = NOW + timedelta(seconds=offset_seconds)
    assert evaluate_freshness(collected_at, NOW, timedelta(hours=3)) is expected


def test_br07_stale_past_the_threshold():
    """BR-07: past the threshold is STALE, and the threshold is exclusive at the boundary."""
    assert evaluate_freshness(NOW - timedelta(hours=3), NOW, timedelta(hours=3)) is Freshness.FRESH
    assert (
        evaluate_freshness(NOW - timedelta(hours=3, seconds=1), NOW, timedelta(hours=3))
        is Freshness.STALE
    )


# --------------------------------------------------------------------------------------------
# BR-08 -- serialization and schema compatibility
# --------------------------------------------------------------------------------------------


def test_br08_rejects_naive_timestamps_rather_than_assuming_utc():
    """BR-08: a naive `collected_at` is rejected, never coerced.

    Assuming a timezone invents information, and BR-07 compares this against a supplied `now` whose
    meaning depends on it.
    """
    with pytest.raises(InvalidSnapshot):
        build_snapshot(
            NormalizationResult((), 0, 0, {}, 0), collected_at=datetime(2026, 8, 3, 12, 0, 0)
        )


def test_br08_major_version_mismatch_is_a_distinct_error():
    """BR-08 / PAT-7: a wrong major version raises `IncompatibleSchema`, not `InvalidSnapshot`.

    They are separate types because U-02 maps them differently in principle even though both become
    503 today -- and distinguishing by `except` is checkable by a type checker, whereas inspecting a
    string attribute is not.
    """
    payload = serialize_snapshot(snapshot_of()).replace(
        f'"schema_version":"{SCHEMA_VERSION}"'.encode(), b'"schema_version":"99.0"'
    )
    with pytest.raises(IncompatibleSchema):
        deserialize_snapshot(payload)


def test_br08_minor_version_difference_is_readable():
    """BR-08: compatibility is major-version equality, so a minor bump still reads.

    This is what makes the queued telemetry amendment additive: bump the minor, add a sibling key,
    and existing readers keep working.
    """
    payload = serialize_snapshot(snapshot_of()).replace(
        f'"schema_version":"{SCHEMA_VERSION}"'.encode(), b'"schema_version":"1.99"'
    )
    assert deserialize_snapshot(payload).schema_version == "1.99"


def test_br08_unknown_top_level_key_is_ignored():
    """BR-08, shape 8: an unrecognized sibling key does not fail the read."""
    assert deserialize_snapshot(serialized_with_unknown_key(snapshot_of())) == snapshot_of()


@pytest.mark.parametrize(
    "payload",
    [b"", b"not json", b"[]", b'{"schema_version":1}', b'{"schema_version":"1.0"}'],
)
def test_br08_malformed_payloads_raise_invalid_snapshot(payload):
    """BR-08: malformed input is rejected rather than best-effort parsed.

    The "corrupt object read as valid data" path is exactly what US-06 exists to distinguish from
    "no data collected yet" -- they mean opposite things to a user.
    """
    with pytest.raises(InvalidSnapshot):
        deserialize_snapshot(payload)


def test_p8_violation_raises_rather_than_asserting():
    """PAT-4 / NFR-R3: a broken accounting identity raises, so `python -O` cannot remove the check.

    Written as an explicit test because the whole point of PAT-4 is that `assert` would silently
    vanish under an optimization flag on a production read path.
    """
    with pytest.raises(InvalidSnapshot):
        build_snapshot(
            NormalizationResult(records=(), raw_returned=5, skipped_count=0,
                                skipped_reasons={}, duplicates_removed=0),
            collected_at=NOW,
        )


# --------------------------------------------------------------------------------------------
# PAT-1, PAT-2 -- immutability and the hash/eq contract
# --------------------------------------------------------------------------------------------


def test_pat1_tags_cannot_be_mutated_after_construction():
    """PAT-1: mutation raises at the offending line rather than corrupting equality silently.

    Without the wrap, a caller mutating `record.tags` would invalidate P1, P2 and P6 -- and it would
    surface as a *flaky property failure* rather than an error here, which is the worst available
    failure signature.
    """
    with pytest.raises(TypeError):
        record(**FULL_TAGS).tags["cornell:owner"] = "changed"  # type: ignore[index]


def test_pat1_construction_copies_the_callers_mapping():
    """PAT-1: the `dict()` copy means the caller cannot reach inside afterwards.

    Wrapping without copying would leave the caller holding a mutable reference into a supposedly
    immutable object -- defeating the pattern while appearing to implement it.
    """
    caller_tags = {"cornell:owner": "original"}
    held = ResourceRecord("arn:aws:s3:::b", "s3", "s3", "global", caller_tags)
    caller_tags["cornell:owner"] = "mutated"
    assert held.tags["cornell:owner"] == "original"


def test_pat2_hash_agrees_with_eq():
    """PAT-2: the contract P1, P2 and P6 rest on.

    Also proves the explicit `__hash__` is present at all: the dataclass-generated one would hash a
    `MappingProxyType` and raise `TypeError` on the first call below.
    """
    a = ResourceRecord("arn:aws:s3:::b", "s3", "s3", "global", {"cornell:owner": "x"})
    b = ResourceRecord("arn:aws:s3:::b", "s3", "s3", "global", {"cornell:owner": "x"})
    c = ResourceRecord("arn:aws:s3:::b", "s3", "s3", "global", {"cornell:owner": "y"})

    assert a == b and hash(a) == hash(b)
    assert a != c
    assert len({a, b, c}) == 2
    assert len({snapshot_of(a), snapshot_of(b)}) == 1


# --------------------------------------------------------------------------------------------
# NFR-P2 -- complexity ceiling
# --------------------------------------------------------------------------------------------


def test_nfr_p2_linear_at_ten_thousand_records():
    """NFR-P2: grouping and classification complete over 10,000 records within a generous bound.

    **Deliberately example-based, not a Hypothesis property.** At `max_examples=100` a generated
    10k-record snapshot would dominate the pre-push gate for a check that needs no randomness.

    The bound is generous on purpose: a wall-clock assertion tight enough to be interesting would be
    flaky on shared CI, and flaky gates teach people to retry rather than to look. Only a complexity
    regression -- an accidental O(n^2) that every other property would happily pass -- trips this.

    `_reference_group_by_tag` is excluded: it is quadratic by design, so running it here would
    measure the test double rather than the implementation.
    """
    records = tuple(
        ResourceRecord(
            arn=f"arn:aws:s3:::bucket-{i}",
            service="s3",
            resource_type="s3",
            region="global",
            tags={"cornell:owner": f"owner-{i % 50}"} if i % 3 else {},
        )
        for i in range(10_000)
    )
    snapshot = snapshot_of(*records)

    started = time.perf_counter()
    grouped = group_by_tag(snapshot, "cornell:owner")
    report = classify_tag_gaps(snapshot)
    elapsed = time.perf_counter() - started

    assert grouped.total == 10_000
    assert sum(len(g.resources) for g in grouped.groups) == 10_000
    assert len(report.complete) + len(report.incomplete) == 10_000
    assert elapsed < 10.0, f"grouping 10k records took {elapsed:.2f}s -- suspect a complexity regression"
