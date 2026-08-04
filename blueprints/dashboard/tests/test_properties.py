"""Property-based tests for U-01 Domain Core (PBT-01..PBT-10, full enforcement).

**This file contains ONLY property tests.** Example-based tests live in `test_examples.py`, which
complements rather than duplicates them (PBT-10). The split mirrors
`packages/builder-mcp/tests/test_properties.py`.

Framework: Hypothesis (PBT-09). Shrinking and seed reporting are Hypothesis defaults and are **not**
disabled (PBT-08) -- a shrunk minimal counterexample is most of the value here. Runtime is bounded by
`max_examples = 100` in `pyproject.toml`, inside the rules' cap of 200.

Ten properties, identified at Functional Design and extended during NFR analysis. Each test names
its PBT category and the business rule it verifies:

| # | Property | Category | Rule |
|---|---|---|---|
| P1 | round-trip, same major version | round-trip | BR-08 |
| P2 | serialization determinism | invariant | BR-08 |
| P3 | group sizes sum to total | invariant | BR-05 |
| P4 | every record in exactly one group | invariant | BR-05 |
| P5 | grouping matches the naive oracle | oracle | BR-05 |
| P6 | grouping idempotent, order included | idempotence | BR-05 |
| P7 | gap flagged iff a required tag is absent | easy verification | BR-06 |
| P8 | accounting identity | invariant | BR-02, BR-04 |
| P9 | grouping and classification agree | consistency | BR-01 |
| P10 | freshness monotonic in `now` | metamorphic | BR-07 |
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import (
    clock_pairs,
    raw_item_lists,
    serialized_with_unknown_key,
    snapshots,
    stale_afters,
    timestamps,
)
from hypothesis import assume, given
from hypothesis import strategies as st

from dashboard.core import (
    REQUIRED_TAGS,
    Freshness,
    classify_tag_gaps,
    deserialize_snapshot,
    evaluate_freshness,
    group_by_tag,
    has_required_tag,
    normalize_all,
    serialize_snapshot,
)
from dashboard.core.aggregation import _reference_group_by_tag

tag_keys = st.sampled_from(REQUIRED_TAGS)


# --------------------------------------------------------------------------------------------
# P1, P2 -- serialization (BR-08)
# --------------------------------------------------------------------------------------------


@given(snapshots())
def test_p1_round_trip(snapshot):
    """P1 (round-trip, BR-08): deserialize(serialize(s)) == s.

    Scoped to snapshots produced at the reader's own major version. That scoping is deliberate and
    recorded: unknown top-level keys are ignored rather than preserved, which is safe only because
    no code path in this system reads a snapshot and writes it back.
    """
    assert deserialize_snapshot(serialize_snapshot(snapshot)) == snapshot


@given(snapshots())
def test_p1_round_trip_ignores_unknown_keys(snapshot):
    """P1, forward-compatibility arm (BR-08, generator shape 8).

    A snapshot carrying an unrecognized sibling key still reads back equal to the original. This is
    the case the queued telemetry amendment depends on: adding a `metrics` key must be additive, not
    a migration.
    """
    assert deserialize_snapshot(serialized_with_unknown_key(snapshot)) == snapshot


@given(snapshots())
def test_p2_serialization_is_deterministic(snapshot):
    """P2 (invariant, BR-08): equal snapshots serialize to identical bytes.

    Determinism is a requirement rather than an optimization -- without it P1 would be flaky rather
    than failing, which is worse than not having it.
    """
    assert serialize_snapshot(snapshot) == serialize_snapshot(snapshot)
    assert serialize_snapshot(snapshot) == serialize_snapshot(
        deserialize_snapshot(serialize_snapshot(snapshot))
    )


# --------------------------------------------------------------------------------------------
# P3, P4 -- grouping invariants (BR-05)
# --------------------------------------------------------------------------------------------


@given(snapshots(), tag_keys)
def test_p3_group_sizes_sum_to_total(snapshot, tag_key):
    """P3 (invariant, BR-05): group sizes sum to total, and total is the record count.

    This is the invariant a naive group-by breaks by skipping records that lack the key -- the
    failure that would make US-03 under-report without anything looking wrong.
    """
    result = group_by_tag(snapshot, tag_key)
    assert sum(len(group.resources) for group in result.groups) == result.total
    assert result.total == len(snapshot.resources)


@given(snapshots(), tag_keys)
def test_p4_every_record_in_exactly_one_group(snapshot, tag_key):
    """P4 (invariant, BR-05): records partition across groups, and no group is empty."""
    result = group_by_tag(snapshot, tag_key)
    seen = [record for group in result.groups for record in group.resources]
    assert len(seen) == len(snapshot.resources)
    assert {r.arn for r in seen} == {r.arn for r in snapshot.resources}
    assert all(group.resources for group in result.groups)


# --------------------------------------------------------------------------------------------
# P5 -- oracle (BR-05)
# --------------------------------------------------------------------------------------------


@given(snapshots(), tag_keys)
def test_p5_matches_reference_implementation(snapshot, tag_key):
    """P5 (oracle, BR-05): the real grouping equals the naive reference.

    The oracle is quadratic and written from BR-05's prose rather than from `group_by_tag`. If it
    were ever produced by copying the implementation this test would pass forever while asserting
    nothing, and no tool can detect that (NFR-T5) -- which is why it is called out here as well as
    in the oracle's own docstring.
    """
    assert group_by_tag(snapshot, tag_key) == _reference_group_by_tag(snapshot, tag_key)


# --------------------------------------------------------------------------------------------
# P6 -- idempotence (BR-05)
# --------------------------------------------------------------------------------------------


@given(snapshots(), tag_keys)
def test_p6_grouping_is_idempotent_including_order(snapshot, tag_key):
    """P6 (idempotence, BR-05): regrouping the same snapshot by the same key changes nothing.

    Equality here includes **order**, since `GroupingResult.groups` is a tuple and order is part of
    the value. That stronger form is what makes P2's byte-level determinism reachable: a
    non-deterministic group order would serialize differently on each call.
    """
    first = group_by_tag(snapshot, tag_key)
    second = group_by_tag(snapshot, tag_key)
    assert first == second
    assert [g.value for g in first.groups] == [g.value for g in second.groups]


@given(snapshots(), tag_keys)
def test_p6_ordering_contract(snapshot, tag_key):
    """P6, ordering arm (BR-05 / Q8): count descending, value ascending, missing group last."""
    groups = group_by_tag(snapshot, tag_key).groups
    named = [g for g in groups if g.value is not None]
    missing = [g for g in groups if g.value is None]

    assert len(missing) <= 1
    if missing:
        assert groups[-1].value is None, "the missing group must be pinned last"

    keys = [(-len(g.resources), g.value) for g in named]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------------------------
# P7 -- gap classification (BR-06)
# --------------------------------------------------------------------------------------------


@given(snapshots())
def test_p7_gap_flagged_iff_a_required_tag_is_absent(snapshot):
    """P7 (easy verification, BR-06): incomplete iff some required tag fails the predicate.

    Trivially checkable per record, and hard to get wrong across a generated corpus -- which is
    exactly the shape an easy-verification property should have.
    """
    report = classify_tag_gaps(snapshot)

    for record in report.complete:
        assert all(has_required_tag(record, key) for key in REQUIRED_TAGS)

    for entry in report.incomplete:
        expected = tuple(k for k in REQUIRED_TAGS if not has_required_tag(entry.record, k))
        assert entry.missing_tags == expected
        assert entry.missing_tags, "an incomplete record must be missing at least one tag"

    assert len(report.complete) + len(report.incomplete) == len(snapshot.resources)


# --------------------------------------------------------------------------------------------
# P8 -- accounting identity (BR-02, BR-04)
# --------------------------------------------------------------------------------------------


@given(raw_item_lists())
def test_p8_accounting_identity_holds_after_normalization(items):
    """P8 (invariant, BR-02 + BR-04): raw == kept + skipped + deduped.

    The property that makes skipping malformed items *honest* rather than merely convenient: a
    resource cannot vanish without landing in exactly one of the three buckets. Neither BR-02 nor
    BR-04 implies this alone -- the pair does.
    """
    result = normalize_all(items)
    assert result.raw_returned == len(items)
    assert (
        result.raw_returned
        == len(result.records) + result.skipped_count + result.duplicates_removed
    )
    assert sum(result.skipped_reasons.values()) == result.skipped_count


@given(raw_item_lists())
def test_p8_normalize_all_is_total(items):
    """P8, totality arm (NFR-R2, PAT-3): no input makes `normalize_all` raise.

    This is Q1 of Functional Design as a contract. The only normalization function the collector
    calls cannot fail on a malformed item, which is what stops one bad ARN from taking down a
    snapshot -- and in a shared account, one team's odd resource from blanking everyone's view.
    """
    result = normalize_all(items)
    assert len({r.arn for r in result.records}) == len(result.records)


@given(raw_item_lists())
def test_p8_survives_serialization(items):
    """P8, persistence arm (NFR-R3): the identity is re-checked on deserialization.

    Enforced by an explicit raise rather than `assert`, because `assert` is stripped under
    `python -O` and this is a production read path.
    """
    from datetime import UTC, datetime

    from dashboard.core import build_snapshot

    snapshot = build_snapshot(normalize_all(items), collected_at=datetime.now(UTC))
    restored = deserialize_snapshot(serialize_snapshot(snapshot))
    assert (
        restored.raw_returned
        == len(restored.resources) + restored.skipped_count + restored.duplicates_removed
    )


# --------------------------------------------------------------------------------------------
# P9 -- cross-function consistency (BR-01)
# --------------------------------------------------------------------------------------------


@given(snapshots(), tag_keys)
def test_p9_grouping_and_classification_agree(snapshot, tag_key):
    """P9 (consistency, BR-01): in the missing group for K iff the gap report says K is missing.

    Catches the specific drift that would make the dashboard contradict itself -- a resource sitting
    in "missing owner" while the tag-gap view calls it compliant. It holds by construction because
    both functions consult the one `has_required_tag` predicate; this asserts the construction has
    not been undone.
    """
    grouped = group_by_tag(snapshot, tag_key)
    report = classify_tag_gaps(snapshot)

    in_missing_group = {
        record.arn
        for group in grouped.groups
        if group.value is None
        for record in group.resources
    }
    flagged_for_key = {
        entry.record.arn for entry in report.incomplete if tag_key in entry.missing_tags
    }

    assert in_missing_group == flagged_for_key


# --------------------------------------------------------------------------------------------
# P10 -- freshness (BR-07)
# --------------------------------------------------------------------------------------------


@given(clock_pairs(), stale_afters)
def test_p10_freshness_is_exhaustive_and_correct(pair, stale_after):
    """P10, correctness arm (BR-07): the three states are exactly as BR-07 defines them.

    Includes the `collected_at == now` boundary and the future-timestamp fault, which is the case an
    implementation checking FRESH before INVALID would silently misreport as fresh.
    """
    collected_at, now = pair
    verdict = evaluate_freshness(collected_at, now, stale_after)

    if collected_at > now:
        assert verdict is Freshness.INVALID
    elif now - collected_at <= stale_after:
        assert verdict is Freshness.FRESH
    else:
        assert verdict is Freshness.STALE


@given(timestamps, stale_afters, st.integers(min_value=1, max_value=1_000_000))
def test_p10_freshness_monotonic_in_now(collected_at, stale_after, seconds):
    """P10 (metamorphic, BR-07): increasing `now` never takes STALE back to FRESH.

    A metamorphic property rather than a value assertion, because sign and comparison-direction
    errors are the realistic bug in a threshold function and are invisible to single-value tests.
    """
    later = collected_at + timedelta(seconds=seconds)
    even_later = later + timedelta(seconds=seconds)

    first = evaluate_freshness(collected_at, later, stale_after)
    second = evaluate_freshness(collected_at, even_later, stale_after)

    assume(first is not Freshness.INVALID and second is not Freshness.INVALID)
    if first is Freshness.STALE:
        assert second is Freshness.STALE


# --------------------------------------------------------------------------------------------
# Guard: the closed allowlist (PAT-8)
# --------------------------------------------------------------------------------------------


@given(snapshots(), st.text(max_size=20))
def test_group_by_tag_rejects_keys_outside_the_allowlist(snapshot, tag_key):
    """PAT-8 (BR-05): only `REQUIRED_TAGS` are groupable.

    The only user-supplied value that reaches U-01, validated against a closed set -- which is what
    makes U-02's input-validation surface nearly structural rather than a layer to maintain.
    """
    assume(tag_key not in REQUIRED_TAGS)
    with pytest.raises(ValueError):
        group_by_tag(snapshot, tag_key)
