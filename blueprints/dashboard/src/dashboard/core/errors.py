"""Error types for the domain core (PAT-7).

Three things about this module are load-bearing rather than stylistic.

**A hierarchy, not one type with a category attribute.** U-02 needs to distinguish these because
they produce *different HTTP outcomes*: a malformed resource is absorbed and counted, whereas an
incompatible schema means there is no usable snapshot at all. Distinguishing by `except` is
checkable by a type checker; distinguishing by inspecting a string attribute is not.

**No exception here carries an ARN, a tag key, a tag value, or an input index (NFR-S1).**
`cornell:owner` holds a NetID, and an exception message can reach a log group or -- through an
unhandled error -- an HTTP response body. Making the rule structural means it does not depend on
every future exception message being written carefully by someone who remembers this. Debugging
detail belongs to U-02's collector, at a boundary where it can decide what is safe to emit.

**`SkipReason` is a closed enum, not free text (NFR-S2).** Its members become the keys of
`Snapshot.skipped_reasons`, so a free-text reason would make that mapping unbounded and could
carry fragments of unparseable input into the snapshot itself.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CoreError",
    "IncompatibleSchema",
    "InvalidSnapshot",
    "MalformedResource",
    "SkipReason",
]


class SkipReason(StrEnum):
    """Why an upstream item could not be normalized (BR-02).

    Closed set. These are the keys of `Snapshot.skipped_reasons`, and they must stay a small
    fixed vocabulary -- see the module docstring.
    """

    ARN = "arn"
    """The ARN was absent or did not parse into its six colon-delimited fields."""

    TAGS = "tags"
    """The tag structure was not a list of key/value pairs."""


class CoreError(Exception):
    """Base for every error the domain core raises.

    U-02 can catch all of U-01 with one `except CoreError`. Never raised directly.
    """


class MalformedResource(CoreError):
    """One upstream item could not be normalized (BR-02).

    Raised by `normalize_resource`. **U-02 should never see this**: `normalize_all` catches it and
    converts it into `skipped_count` and `skipped_reasons` (PAT-3), which is what makes one bad
    ARN unable to take down a whole snapshot. If U-02 finds itself catching this, something is
    wired wrong.

    Carries the reason category and nothing else.
    """

    def __init__(self, reason: SkipReason) -> None:
        super().__init__(reason.value)
        self.reason = reason

    def __str__(self) -> str:
        return f"resource could not be normalized: {self.reason.value}"


class IncompatibleSchema(CoreError):
    """A stored snapshot's schema major version does not match this reader's (BR-08).

    Raised by `deserialize_snapshot`. The snapshot is unreadable, so U-02 maps this to
    `UNREADABLE` and a **503** -- not a 200 with empty data, which would present a fault as a
    state of the world.

    Carries both versions because a schema version is not user data: it is a constant this
    codebase writes.
    """

    def __init__(self, found: str, expected_major: str) -> None:
        super().__init__(found, expected_major)
        self.found = found
        self.expected_major = expected_major

    def __str__(self) -> str:
        return (
            f"snapshot schema version {self.found!r} is not readable by this version "
            f"(expected major {self.expected_major!r})"
        )


class InvalidSnapshot(CoreError):
    """A snapshot is structurally invalid (BR-08, and P8's accounting identity).

    Raised by `build_snapshot` and `deserialize_snapshot` for malformed JSON, a naive
    `collected_at`, negative counts, duplicate ARNs, or a violated accounting identity.

    **This type exists so P8 can be enforced without `assert`.** `assert` statements are stripped
    entirely under `python -O`, and NFR-R3 requires the accounting identity to hold on
    deserialization -- a production read path inside a Lambda. An invariant that disappears under
    an optimization flag is not an invariant.

    `detail` is a fixed description written by this codebase. It never contains input data.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        return f"snapshot is invalid: {self.detail}"
