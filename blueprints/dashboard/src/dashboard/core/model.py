"""Entities and the (de)serialization pair -- component C-04 (BR-02, BR-03, BR-04, BR-08).

Pure. No AWS SDK, no network, no filesystem, no clock, no environment read, no logging. The
`tools/check` boundary grep enforces that mechanically; it is not a convention.

Two implementation details in here are requirements rather than idiom, and both are easy to
"tidy" into bugs:

1. **Every `Mapping` field is copied and wrapped in `MappingProxyType`** (PAT-1). `frozen=True`
   stops field *rebinding*; it does nothing about mutating a dict's contents. Since P1, P2 and P6
   are equality assertions, a caller mutating `record.tags` after construction invalidates all
   three -- and it would surface as a *flaky property failure* rather than an error at the
   mutation site. The `dict()` copy before wrapping is equally mandatory: wrapping the caller's
   own mapping leaves them holding a mutable reference into the contents of a supposedly immutable
   object.

2. **`__hash__` is explicit** (PAT-2). `@dataclass(frozen=True, eq=True)` would generate one from
   the field tuple, which calls `hash()` on a `MappingProxyType` and raises `TypeError` on first
   use. The explicit version hashes tags as a `frozenset` of items, which agrees with the
   generated `__eq__` because `MappingProxyType` compares by content. That agreement is what P1,
   P2 and P6 rest on; if it broke, they would fail looking like a serialization bug.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from dashboard.core.errors import InvalidSnapshot, IncompatibleSchema, MalformedResource, SkipReason

__all__ = [
    "REQUIRED_TAGS",
    "SCHEMA_VERSION",
    "NormalizationResult",
    "ResourceRecord",
    "Snapshot",
    "build_snapshot",
    "deserialize_snapshot",
    "normalize_all",
    "normalize_resource",
    "serialize_snapshot",
]


REQUIRED_TAGS: tuple[str, ...] = (
    "cornell:owner",
    "cornell:blueprint",
    "cornell:blueprint-version",
    "cornell:deployment-id",
)
"""The four tags every resource must carry (CLAUDE.md, FR-1.4).

Lowercase and ordered. Order matters: `TagGapReport.missing_tags` is produced by iterating this
tuple, which is what makes it deterministic (P2).
"""

SCHEMA_VERSION = "1.0"
"""Snapshot schema version this module writes, `MAJOR.MINOR`.

Read compatibility is **major-version equality** (BR-08). Bump the minor for an additive change
such as the queued telemetry amendment's sibling key; bump the major only for a change that makes
old snapshots unreadable.
"""

_GLOBAL_REGION = "global"
"""What `region` holds when an ARN's region segment is empty (BR-03).

IAM roles, CloudFront distributions and other global resources have no region in their ARN. The
console and AWS's own documentation call these "global", so a reader of the dashboard will not be
surprised, and `region` stays a plain non-empty string with no optionality to propagate.
"""

_ARN_FIELDS = 6
"""`arn:partition:service:region:account:resource` -- six colon-delimited fields."""


@dataclass(frozen=True, eq=True)
class ResourceRecord:
    """One AWS resource as the inventory knows it.

    Identity is `arn` alone (BR-04). Equality is structural over all five fields, because three
    properties are equality assertions.
    """

    arn: str
    service: str
    resource_type: str
    region: str
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        # object.__setattr__ is mandatory: a frozen dataclass rejects normal assignment here.
        # dict() before MappingProxyType is mandatory: see the module docstring.
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))

    def __hash__(self) -> int:
        # Explicit, and it must agree with the generated __eq__ -- see the module docstring.
        return hash(
            (
                self.arn,
                self.service,
                self.resource_type,
                self.region,
                frozenset(self.tags.items()),
            )
        )


@dataclass(frozen=True, eq=True)
class NormalizationResult:
    """Outcome of normalizing one upstream page set. Input to `build_snapshot`.

    Carries the three counts P8 relates, so the accounting identity is checkable at the point the
    snapshot is built rather than reconstructed later.
    """

    records: tuple[ResourceRecord, ...]
    raw_returned: int
    skipped_count: int
    skipped_reasons: Mapping[str, int]
    duplicates_removed: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "skipped_reasons", MappingProxyType(dict(self.skipped_reasons))
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.records,
                self.raw_returned,
                self.skipped_count,
                frozenset(self.skipped_reasons.items()),
                self.duplicates_removed,
            )
        )


@dataclass(frozen=True, eq=True)
class Snapshot:
    """One collection run's complete result, including what it could not use.

    The aggregate. Nothing else in this unit has an independent lifecycle.

    The four counts exist so P8 can be asserted: it is mechanically impossible for a resource to
    vanish without landing in exactly one of `resources`, `skipped_count` or
    `duplicates_removed`. That is what makes "we skipped one" a verifiable claim rather than a
    reassuring sentence.
    """

    schema_version: str
    collected_at: datetime
    resources: tuple[ResourceRecord, ...]
    raw_returned: int
    skipped_count: int
    skipped_reasons: Mapping[str, int] = field(default_factory=dict)
    duplicates_removed: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "skipped_reasons", MappingProxyType(dict(self.skipped_reasons))
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.schema_version,
                self.collected_at,
                self.resources,
                self.raw_returned,
                self.skipped_count,
                frozenset(self.skipped_reasons.items()),
                self.duplicates_removed,
            )
        )


def _is_naive(value: datetime) -> bool:
    """True when a datetime carries no usable UTC offset.

    A naive datetime is rejected rather than coerced: assuming a timezone invents information, and
    `evaluate_freshness` compares this against a supplied `now` whose meaning depends on it.
    """
    return value.tzinfo is None or value.tzinfo.utcoffset(value) is None


def _major(version: str) -> str:
    """Major component of a `MAJOR.MINOR` version string."""
    return version.split(".", 1)[0]


def normalize_resource(raw: Mapping[str, object]) -> ResourceRecord:
    """Turn one Resource Groups Tagging API item into a `ResourceRecord` (BR-02, BR-03).

    Raises `MalformedResource` on a structurally unreadable item. "Malformed" means unparseable --
    a resource merely *missing* `cornell:*` tags is entirely normal and is US-04's whole subject.

    ARN parsing is `str.split` with explicit checks, never a regular expression (NFR-S3). An ARN
    is a fixed six-field grammar, so a pattern buys nothing a split does not, while adding a
    backtracking surface; and a permissive pattern would silently accept malformed ARNs that these
    checks reject -- and rejecting them is what feeds `skipped_reasons`.
    """
    arn = raw.get("ResourceARN")
    if not isinstance(arn, str) or not arn:
        raise MalformedResource(SkipReason.ARN)

    parts = arn.split(":", _ARN_FIELDS - 1)
    if len(parts) != _ARN_FIELDS or parts[0] != "arn":
        raise MalformedResource(SkipReason.ARN)

    _, _partition, service, region, _account, resource = parts
    if not service or not resource:
        raise MalformedResource(SkipReason.ARN)

    raw_tags = raw.get("Tags", [])
    if not isinstance(raw_tags, Iterable) or isinstance(raw_tags, (str, bytes)):
        raise MalformedResource(SkipReason.TAGS)

    tags: dict[str, str] = {}
    for entry in raw_tags:
        if not isinstance(entry, Mapping):
            raise MalformedResource(SkipReason.TAGS)
        key = entry.get("Key")
        value = entry.get("Value", "")
        if not isinstance(key, str) or not isinstance(value, str):
            raise MalformedResource(SkipReason.TAGS)
        tags[key] = value

    return ResourceRecord(
        arn=arn,
        service=service,
        resource_type=_resource_type(service, resource),
        region=region or _GLOBAL_REGION,
        tags=tags,
    )


def _resource_type(service: str, resource: str) -> str:
    """Resource type from an ARN's resource segment.

    The segment is either `type/id`, `type:id`, or a bare id -- an S3 bucket ARN
    (`arn:aws:s3:::my-bucket`) carries no type at all. When a separator is present the prefix is
    the type. When it is absent, the **service** is the only type information the ARN contains, so
    that is what is reported: for a bucket that yields `"s3"`, which is what a reader of the
    dashboard expects, rather than an empty cell or the bucket's own name.

    **The earliest separator wins, not a fixed `/`-then-`:` preference.** A CloudWatch log group
    ARN is `...:log-group:/aws/lambda/x` -- the type separator is `:` and the *id* then contains
    `/`. Preferring `/` unconditionally yields `"log-group:"`, with the colon attached, which is
    what a reader would see in the type column. Found by running this against real ARN shapes
    rather than by reasoning about them.

    Documented rather than obvious, because it is a derivation and not a field.
    """
    positions = [resource.find(sep) for sep in ("/", ":")]
    present = [index for index in positions if index != -1]
    if not present:
        return service
    return resource[: min(present)]


def normalize_all(raw_items: Sequence[Mapping[str, object]]) -> NormalizationResult:
    """Normalize a whole collection, absorbing failures into counts (BR-02, BR-04).

    **Total** (PAT-3, NFR-R2): no input makes this raise. That is Q1 of Functional Design expressed
    in types -- the only normalization function the collector calls cannot fail on a malformed
    item, so one bad ARN cannot take down a snapshot.

    P8 holds by construction: every input takes exactly one of three paths -- skipped, counted as a
    duplicate, or present in the result. The identity is not an extra check bolted on afterwards;
    it is what this loop's shape guarantees.
    """
    records: dict[str, ResourceRecord] = {}
    skipped = 0
    reasons: dict[str, int] = {}
    duplicates = 0

    for item in raw_items:
        try:
            record = normalize_resource(item)
        except MalformedResource as exc:
            skipped += 1
            reasons[exc.reason.value] = reasons.get(exc.reason.value, 0) + 1
            continue
        if record.arn in records:
            duplicates += 1
        # Last occurrence wins (BR-04). Insertion order is preserved for the first sighting of
        # each ARN, which keeps output order deterministic (P2).
        records[record.arn] = record

    return NormalizationResult(
        records=tuple(records.values()),
        raw_returned=len(raw_items),
        skipped_count=skipped,
        skipped_reasons=reasons,
        duplicates_removed=duplicates,
    )


def _check_accounting(
    raw_returned: int,
    kept: int,
    skipped_count: int,
    duplicates_removed: int,
) -> None:
    """Enforce P8, the accounting identity.

    Raises `InvalidSnapshot` -- **never `assert`**. `assert` is stripped under `python -O`, and
    NFR-R3 requires this check on deserialization, which is a production read path inside a
    Lambda. An invariant that vanishes under an optimization flag is not an invariant (PAT-4).
    """
    if min(raw_returned, kept, skipped_count, duplicates_removed) < 0:
        raise InvalidSnapshot("counts must not be negative")
    if raw_returned != kept + skipped_count + duplicates_removed:
        raise InvalidSnapshot(
            "accounting identity violated: raw_returned must equal "
            "len(resources) + skipped_count + duplicates_removed"
        )


def build_snapshot(
    result: NormalizationResult,
    collected_at: datetime,
    schema_version: str = SCHEMA_VERSION,
) -> Snapshot:
    """Stamp a normalization result into a `Snapshot` (BR-08).

    The clock is **injected** -- this function never reads one (PAT-6).

    The duplicate-ARN re-check is deliberate redundancy: `normalize_all` cannot produce duplicates,
    but `build_snapshot` is also called directly from tests, and guarding the invariant at the
    aggregate boundary means a hand-built snapshot cannot violate the uniqueness P3 and P4 assume.
    """
    if _is_naive(collected_at):
        raise InvalidSnapshot("collected_at must be timezone-aware")

    arns = {record.arn for record in result.records}
    if len(arns) != len(result.records):
        raise InvalidSnapshot("resources must be unique by ARN")

    _check_accounting(
        result.raw_returned,
        len(result.records),
        result.skipped_count,
        result.duplicates_removed,
    )

    return Snapshot(
        schema_version=schema_version,
        collected_at=collected_at,
        resources=result.records,
        raw_returned=result.raw_returned,
        skipped_count=result.skipped_count,
        skipped_reasons=result.skipped_reasons,
        duplicates_removed=result.duplicates_removed,
    )


def serialize_snapshot(snapshot: Snapshot) -> bytes:
    """Serialize to deterministic JSON bytes (BR-08).

    JSON only -- no `pickle`, no `yaml` (SECURITY-14, NFR-S4).

    Determinism is a **requirement**, not an optimization: without it P1 and P2 would be flaky
    rather than failing, which is worse than not having them. `sort_keys` plus a fixed datetime
    encoding is what delivers it.
    """
    payload = {
        "schema_version": snapshot.schema_version,
        "collected_at": snapshot.collected_at.isoformat(),
        "raw_returned": snapshot.raw_returned,
        "skipped_count": snapshot.skipped_count,
        "skipped_reasons": dict(snapshot.skipped_reasons),
        "duplicates_removed": snapshot.duplicates_removed,
        "resources": [
            {
                "arn": record.arn,
                "service": record.service,
                "resource_type": record.resource_type,
                "region": record.region,
                "tags": dict(record.tags),
            }
            for record in snapshot.resources
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_snapshot(raw: bytes) -> Snapshot:
    """Parse stored bytes back into a `Snapshot` (BR-08).

    Rejects malformed JSON, a mismatched schema **major** version, and a naive `collected_at`
    rather than best-effort parsing -- the "corrupt object read as valid data" path is exactly what
    US-06 exists to distinguish from "no data yet".

    **Unknown top-level keys are ignored, not preserved.** Safe here specifically because no code
    path in this system reads a snapshot and writes it back: the collector always constructs a
    fresh one and does a single PutObject, the API only ever reads. So a dropped key is
    unobservable by construction, and P1 is correspondingly scoped to snapshots produced at the
    same major version. This is what makes the queued telemetry amendment's sibling key an additive
    change rather than a migration.
    """
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidSnapshot("payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidSnapshot("payload is not a JSON object")

    version = payload.get("schema_version")
    if not isinstance(version, str):
        raise InvalidSnapshot("schema_version is missing or not a string")
    if _major(version) != _major(SCHEMA_VERSION):
        raise IncompatibleSchema(version, _major(SCHEMA_VERSION))

    collected_raw = payload.get("collected_at")
    if not isinstance(collected_raw, str):
        raise InvalidSnapshot("collected_at is missing or not a string")
    try:
        collected_at = datetime.fromisoformat(collected_raw)
    except ValueError as exc:
        raise InvalidSnapshot("collected_at is not an ISO-8601 timestamp") from exc
    if _is_naive(collected_at):
        raise InvalidSnapshot("collected_at must be timezone-aware")

    resources_raw = payload.get("resources")
    if not isinstance(resources_raw, list):
        raise InvalidSnapshot("resources is missing or not a list")

    records: list[ResourceRecord] = []
    for entry in resources_raw:
        if not isinstance(entry, dict):
            raise InvalidSnapshot("a resource entry is not a JSON object")
        try:
            records.append(
                ResourceRecord(
                    arn=_require_str(entry, "arn"),
                    service=_require_str(entry, "service"),
                    resource_type=_require_str(entry, "resource_type"),
                    region=_require_str(entry, "region"),
                    tags=_require_str_map(entry, "tags"),
                )
            )
        except KeyError as exc:
            raise InvalidSnapshot("a resource entry is missing a required field") from exc

    counts = {
        name: payload.get(name, 0)
        for name in ("raw_returned", "skipped_count", "duplicates_removed")
    }
    for name, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidSnapshot(f"{name} is not an integer")

    reasons_raw = payload.get("skipped_reasons", {})
    if not isinstance(reasons_raw, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
        for k, v in reasons_raw.items()
    ):
        raise InvalidSnapshot("skipped_reasons is not a mapping of string to integer")

    _check_accounting(
        counts["raw_returned"],
        len(records),
        counts["skipped_count"],
        counts["duplicates_removed"],
    )

    return Snapshot(
        schema_version=version,
        collected_at=collected_at,
        resources=tuple(records),
        raw_returned=counts["raw_returned"],
        skipped_count=counts["skipped_count"],
        skipped_reasons=reasons_raw,
        duplicates_removed=counts["duplicates_removed"],
    )


def _require_str(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str):
        raise KeyError(key)
    return value


def _require_str_map(entry: Mapping[str, object], key: str) -> dict[str, str]:
    value = entry.get(key)
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise KeyError(key)
    return dict(value)
