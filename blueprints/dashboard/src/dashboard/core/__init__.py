"""U-01 Domain Core: every decision the dashboard makes about its data, as pure functions.

**The boundary.** Nothing beneath this package imports an AWS SDK, opens a socket, touches the
filesystem, reads an environment variable, reads a clock, or emits a log line. `now` and
`stale_after` are always parameters. That is not a convention -- `tools/check` greps for it, and it
is what makes ten property-based tests possible without an AWS account, a deployed stack, or a
pipeline run.

**`__all__` below is the contract with U-02.** A reviewer can read one list and know everything the
collector and the read API are permitted to depend on. Two deliberate consequences:

- The four error types are exported, because U-02 must catch them. An `__all__` listing only
  functions and entities would push U-02 toward `except Exception`, which swallows genuine bugs
  alongside expected failures.
- `_reference_group_by_tag` is **not** exported. It is P5's oracle; reachable from production code
  it could be used as if it were the real implementation, and P5 would then be comparing an
  implementation against itself.

U-02 imports from `dashboard.core`, never from `dashboard.core.model` or `dashboard.core.aggregation`
directly, so this package's internal file layout can change without breaking a unit boundary.

Business rules BR-01..BR-08 live in
`aidlc-docs/construction/u-01-domain-core/functional-design/business-rules.md`; each public
function's docstring names the rule it implements.
"""

from __future__ import annotations

from dashboard.core.aggregation import (
    Freshness,
    Group,
    GroupingResult,
    IncompleteRecord,
    TagGapReport,
    classify_tag_gaps,
    evaluate_freshness,
    group_by_tag,
    has_required_tag,
)
from dashboard.core.catalog import (
    Catalog,
    DeclaredCounter,
    MalformedCatalog,
    declared_counters,
    emits,
    parse_catalog,
)
from dashboard.core.errors import (
    CoreError,
    IncompatibleSchema,
    InvalidSnapshot,
    MalformedResource,
    SkipReason,
)
from dashboard.core.money import (
    AttributionSplit,
    CostEstimate,
    CostGroup,
    MalformedRateTable,
    ModelRate,
    ModelUsage,
    PerTaskOutcome,
    PerTaskResult,
    RateTable,
    cost_per_task,
    estimate_model_cost,
    is_unattributed,
    parse_amount,
    parse_rate_table,
    split_attribution,
)
from dashboard.core.telemetry import (
    Counter,
    CounterKey,
    CounterSeries,
    RateResult,
    TelemetryState,
    aggregate_by_agent,
    counter_key,
    derive_rate,
    total_tokens_by_model,
)
from dashboard.core.model import (
    REQUIRED_TAGS,
    SCHEMA_VERSION,
    NormalizationResult,
    ResourceRecord,
    Snapshot,
    build_snapshot,
    deserialize_snapshot,
    normalize_all,
    normalize_resource,
    serialize_snapshot,
)

__all__ = [
    # Constants
    "REQUIRED_TAGS",
    "SCHEMA_VERSION",
    # --- FR-9 / FR-10 additions (C-12 money, C-13 telemetry, C-14 catalog) ---
    # Money (C-12). Every monetary value is Decimal, never float (COST-01).
    "AttributionSplit",
    "CostEstimate",
    "CostGroup",
    "MalformedRateTable",
    "ModelRate",
    "ModelUsage",
    "PerTaskOutcome",
    "PerTaskResult",
    "RateTable",
    "cost_per_task",
    "estimate_model_cost",
    "is_unattributed",
    "parse_amount",
    "parse_rate_table",
    "split_attribution",
    # Telemetry (C-13). agent_id defaults to deployment_id in counter_key (TEL-01).
    "Counter",
    "CounterKey",
    "CounterSeries",
    "RateResult",
    "TelemetryState",
    "aggregate_by_agent",
    "counter_key",
    "derive_rate",
    "total_tokens_by_model",
    # Catalog (C-14). Parser only -- loading the file is U-02's job (CAT-04).
    "Catalog",
    "DeclaredCounter",
    "MalformedCatalog",
    "declared_counters",
    "emits",
    "parse_catalog",
    # Entities
    "Freshness",
    "Group",
    "GroupingResult",
    "IncompleteRecord",
    "NormalizationResult",
    "ResourceRecord",
    "Snapshot",
    "TagGapReport",
    # Model operations (C-04)
    "build_snapshot",
    "deserialize_snapshot",
    "normalize_all",
    "normalize_resource",
    "serialize_snapshot",
    # Aggregation operations (C-05)
    "classify_tag_gaps",
    "evaluate_freshness",
    "group_by_tag",
    "has_required_tag",
    # Errors -- U-02 must be able to catch these
    "CoreError",
    "IncompatibleSchema",
    "InvalidSnapshot",
    "MalformedResource",
    "SkipReason",
]
