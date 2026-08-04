"""Hypothesis strategies for U-01 Domain Core (PBT-07 domain generators).

**These generators are what RESILIENCY-14 actually rests on.** NFR Design Q5 recorded that the
property suite *is* this unit's resiliency test, on the grounds that adversarial input is the only
thing a pure library can be made resilient to. That claim is only as strong as the shapes generated
below -- and NFR-T7, the requirement that they cover all eight, is **review-only**. No tool checks
it. So each strategy names the shape it covers, so a reviewer can compare this file against the
list rather than take it on trust.

The eight shapes required by `business-logic-model.md`:

1. ARNs with an empty region segment (BR-03 -> "global")
2. Tag values that are empty, whitespace-only, and normal (BR-01)
3. Tag keys differing from a required one only by case (BR-01)
4. Duplicate ARNs within one input (BR-04)
5. Non-normalizable items mixed with valid ones (BR-02)
6. `collected_at` before, equal to, and after `now` (BR-07)
7. Snapshots with zero resources -- distinct from "no snapshot", which U-01 cannot represent
8. Snapshots carrying an unrecognized top-level key (BR-08 / schema forward-compatibility)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from dashboard.core import (
    REQUIRED_TAGS,
    SCHEMA_VERSION,
    NormalizationResult,
    ResourceRecord,
    Snapshot,
    build_snapshot,
)

# Hypothesis settings live HERE, in code, and not in pyproject.toml. Hypothesis has no
# pyproject config source, so a `[tool.hypothesis]` table is read by nobody -- the first draft of
# this suite had one, and the 100-example cap it claimed to set was only being honoured because it
# happens to equal Hypothesis's own default. Caught by asking the library what profile it was
# actually using rather than trusting the file.
#
# max_examples 100 matches packages/builder-mcp and sits inside the PBT rules' cap of 200.
# deadline=None because a per-example wall-clock deadline flakes on shared CI, and a flaky gate
# teaches people to retry rather than to look.
# Shrinking and seed reporting are Hypothesis defaults and are deliberately NOT disabled (PBT-08):
# a shrunk minimal counterexample is most of the value of property-based testing.
hyp_settings.register_profile("dashboard-pbt", max_examples=100, deadline=None)
hyp_settings.load_profile("dashboard-pbt")

# --------------------------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------------------------

# Deliberately narrow so collisions are common: with a small pool, generated inputs actually
# exercise grouping with several members per group instead of producing all-singleton groups.
TAG_VALUE_POOL = ["abc123", "xyz789", "dashboard", "hello-world", "0.1.0"]

services = st.sampled_from(["s3", "lambda", "iam", "cloudfront", "apigateway", "logs"])
"""A mix of regional and global services, so shape 1 arises naturally."""

# Shape 2: empty and whitespace-only values alongside normal ones. BR-01 treats the first two as
# MISSING, so these are the inputs that distinguish a correct presence predicate from a naive one.
tag_values = st.one_of(
    st.sampled_from(TAG_VALUE_POOL),
    st.just(""),
    st.sampled_from([" ", "  ", "\t", "\n"]),
)

# Shape 3: keys differing from a required key only by case. BR-01 is case-sensitive, so these must
# be reported as gaps -- the case a case-folding implementation would silently pass.
miscased_required_keys = st.sampled_from(
    ["Cornell:owner", "CORNELL:OWNER", "Cornell:Blueprint", "cornell:Deployment-Id"]
)


@st.composite
def arns(draw: st.DrawFn, service: str | None = None, global_service: bool | None = None) -> str:
    """A syntactically valid ARN.

    **Shape 1**: when the region segment is empty the ARN is a global-service ARN, which BR-03 maps
    to the literal region ``"global"``.
    """
    svc = service if service is not None else draw(services)
    is_global = (
        global_service
        if global_service is not None
        else draw(st.booleans()) or svc in {"iam", "cloudfront"}
    )
    region = "" if is_global else draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]))
    account = draw(st.sampled_from(["123456789012", ""]))
    name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=12))
    separator = draw(st.sampled_from(["/", ":", ""]))
    resource = f"{draw(st.sampled_from(['role', 'function', 'bucket']))}{separator}{name}" if separator else name
    return f"arn:aws:{svc}:{region}:{account}:{resource}"


@st.composite
def tag_maps(draw: st.DrawFn) -> dict[str, str]:
    """A tag mapping: some required keys present, some absent, some empty, some mis-cased.

    Covers **shape 2** and **shape 3** together, and produces the full range from
    fully-compliant to entirely untagged -- which is what P7 and P9 need to be meaningful.
    """
    tags: dict[str, str] = {}
    for key in REQUIRED_TAGS:
        if draw(st.booleans()):
            tags[key] = draw(tag_values)
    if draw(st.booleans()):
        tags[draw(miscased_required_keys)] = draw(st.sampled_from(TAG_VALUE_POOL))
    if draw(st.booleans()):
        tags[draw(st.sampled_from(["Name", "environment", "team"]))] = draw(
            st.sampled_from(TAG_VALUE_POOL)
        )
    return tags


@st.composite
def resource_records(draw: st.DrawFn) -> ResourceRecord:
    """A `ResourceRecord` built directly, bypassing normalization."""
    arn = draw(arns())
    parts = arn.split(":", 5)
    service, region, resource = parts[2], parts[3], parts[5]
    positions = [resource.find(sep) for sep in ("/", ":")]
    present = [index for index in positions if index != -1]
    resource_type = resource[: min(present)] if present else service
    return ResourceRecord(
        arn=arn,
        service=service,
        resource_type=resource_type,
        region=region or "global",
        tags=draw(tag_maps()),
    )


# --------------------------------------------------------------------------------------------
# Raw upstream items
# --------------------------------------------------------------------------------------------


@st.composite
def raw_items(draw: st.DrawFn) -> dict[str, Any]:
    """A well-formed Resource Groups Tagging API item."""
    tags = draw(tag_maps())
    return {
        "ResourceARN": draw(arns()),
        "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
    }


# The annotation is required, not decorative: `st.just({})` gives mypy no key or value type to
# infer, so without it this name is unsolved and the ambiguity propagates into every function that
# draws from it -- which is how it first surfaced, as a confusing arg-type error on an unrelated
# `draw(st.booleans())` several lines away.
malformed_raw_items: st.SearchStrategy[dict[str, Any]] = st.one_of(
    st.just({}),
    st.just({"ResourceARN": ""}),
    st.just({"ResourceARN": "not-an-arn"}),
    st.just({"ResourceARN": "arn:aws:s3"}),
    st.just({"ResourceARN": "arn:aws::us-east-1:123:thing"}),
    st.just({"ResourceARN": "notarn:aws:s3:::bucket"}),
    st.just({"ResourceARN": "arn:aws:s3:::bucket", "Tags": "not-a-list"}),
    st.just({"ResourceARN": "arn:aws:s3:::bucket", "Tags": [{"Key": 1, "Value": "x"}]}),
    st.just({"ResourceARN": "arn:aws:s3:::bucket", "Tags": ["not-a-mapping"]}),
)
"""**Shape 5**: items BR-02 must skip and count rather than crash on.

Each is unparseable in a different way -- absent ARN, empty ARN, too few fields, empty service,
wrong scheme, tags not a list, non-string key, non-mapping entry. Together they are what make
`normalize_all`'s totality (NFR-R2) a claim worth testing.
"""


@st.composite
def raw_item_lists(draw: st.DrawFn) -> list[dict[str, Any]]:
    """A mixed upstream page: valid items, malformed items, and duplicate ARNs.

    Covers **shape 4** (duplicate ARNs within one input) and **shape 5** (malformed mixed with
    valid) simultaneously, which is the combination P8's accounting identity exists to police.
    """
    items = draw(st.lists(raw_items(), min_size=0, max_size=8))

    # Both booleans are drawn unconditionally, into locals, rather than inline in the conditions.
    # Two independent reasons:
    #
    # 1. A `draw()` inside a short-circuiting `and` is skipped whenever the left operand is falsy,
    #    so the draw sequence would depend on whether `items` came out empty. Hypothesis shrinks by
    #    simplifying the underlying choice sequence, and a sequence whose *shape* varies with
    #    earlier values gives the shrinker less to work with.
    # 2. mypy cannot solve the generic `DrawFn.__call__` in that position and reports a confusing
    #    arg-type error several lines away from the real construct. Hoisting fixes it.
    add_duplicate = draw(st.booleans())
    vary_duplicate_tags = draw(st.booleans())

    if items and add_duplicate:
        # Shape 4: re-append an existing item, sometimes with different tags so "last wins"
        # (BR-04) is observable rather than a no-op.
        duplicate = dict(draw(st.sampled_from(items)))
        if vary_duplicate_tags:
            duplicate["Tags"] = [{"Key": "cornell:owner", "Value": "changed"}]
        items.append(duplicate)
    items.extend(draw(st.lists(malformed_raw_items, min_size=0, max_size=3)))
    return draw(st.permutations(items))


# --------------------------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------------------------

timestamps = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
).map(lambda dt: dt.replace(tzinfo=UTC))
"""Timezone-aware UTC timestamps. Naive datetimes are rejected by the model, never coerced."""

stale_afters = st.sampled_from(
    [timedelta(minutes=15), timedelta(hours=1), timedelta(hours=3), timedelta(days=1)]
)


@st.composite
def clock_pairs(draw: st.DrawFn) -> tuple[datetime, datetime]:
    """`(collected_at, now)` covering **shape 6**: before, exactly equal, and after.

    The equal and after cases are the ones that matter. `collected_at == now` sits on the FRESH
    boundary, and `collected_at > now` is the clock-skew fault BR-07 returns `INVALID` for -- the
    case an implementation that checks FRESH first would silently misreport.
    """
    now = draw(timestamps)
    relation = draw(st.sampled_from(["before", "equal", "after"]))
    if relation == "equal":
        return now, now
    offset = draw(st.integers(min_value=1, max_value=100_000)).__mul__(1)
    delta = timedelta(seconds=offset)
    return (now - delta, now) if relation == "before" else (now + delta, now)


@st.composite
def snapshots(draw: st.DrawFn, min_resources: int = 0) -> Snapshot:
    """A `Snapshot` with a self-consistent accounting identity.

    **Shape 7**: `min_resources=0` means the empty snapshot is generated. That case is deliberately
    reachable, because "zero resources found" and "no snapshot collected yet" mean opposite things
    to a user and render identically under a naive implementation -- U-01 can represent only the
    first, and US-06 turns on the distinction.
    """
    records = draw(
        st.lists(resource_records(), min_size=min_resources, max_size=8, unique_by=lambda r: r.arn)
    )
    skipped = draw(st.integers(min_value=0, max_value=3))
    duplicates = draw(st.integers(min_value=0, max_value=3))
    reasons: dict[str, int] = {}
    remaining = skipped
    if remaining:
        arn_share = draw(st.integers(min_value=0, max_value=remaining))
        if arn_share:
            reasons["arn"] = arn_share
        if remaining - arn_share:
            reasons["tags"] = remaining - arn_share
    return build_snapshot(
        NormalizationResult(
            records=tuple(records),
            raw_returned=len(records) + skipped + duplicates,
            skipped_count=skipped,
            skipped_reasons=reasons,
            duplicates_removed=duplicates,
        ),
        collected_at=draw(timestamps),
        schema_version=SCHEMA_VERSION,
    )


def serialized_with_unknown_key(snapshot: Snapshot, key: str = "metrics") -> bytes:
    """Serialize a snapshot and inject an unrecognized top-level key.

    **Shape 8.** This is the forward-compatibility case: the queued telemetry amendment will add
    exactly such a sibling key, and BR-08 requires a reader at the same major version to ignore it
    rather than fail. Not a Hypothesis strategy because it transforms an existing snapshot; used
    directly by the properties and examples.
    """
    from dashboard.core import serialize_snapshot

    payload = json.loads(serialize_snapshot(snapshot))
    payload[key] = {"invocations": 42, "note": "added by a future writer"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
