"""C-10 cost collector (COST-04..08) and C-11 telemetry collector (TEL-02..05, TEL-10).

Example-based, not property-based, and deliberately so -- matching U-02's existing choice. A property
test over a stubbed AWS client tests the stub. The pure logic these collectors delegate to *is*
property-tested, in `test_money.py` and `test_telemetry_core.py`.

The behaviour worth the most attention here is the pair of **opposite failure policies**: cost fails
whole, telemetry degrades per half. Both are tested, because a reviewer seeing two same-shaped
collectors behave differently will otherwise read it as a bug.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError

from dashboard.core import TelemetryState, parse_catalog
from dashboard.core.catalog import CATALOG_SCHEMA_VERSION
from dashboard.cost.config import CostConfig
from dashboard.cost.errors import CostFailure, CostReason
from dashboard.cost.handler import run as run_cost
from dashboard.telemetry.config import TelemetryConfig
from dashboard.telemetry.handler import TelemetryFailure
from dashboard.telemetry.handler import run as run_telemetry

FIXED_NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


class _RecordingS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.puts.append(kwargs)

    @property
    def payload(self) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(self.puts[0]["Body"])
        return parsed


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "GetCostAndUsage")


# ---------------------------------------------------------------------------------------------
# C-10 cost collector
# ---------------------------------------------------------------------------------------------


class _FakeCE:
    """Returns a fixed shape; counts calls; can be told to fail on the Nth call."""

    def __init__(self, fail_on: int | None = None, error: Exception | None = None) -> None:
        self.calls = 0
        self.fail_on = fail_on
        self.error = error or _client_error("ThrottlingException")

    def get_cost_and_usage(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.fail_on is not None and self.calls == self.fail_on:
            raise self.error
        if "GroupBy" in kwargs:
            key = kwargs["GroupBy"][0]["Key"]
            group_key = "cornell:blueprint$" if key == "cornell:blueprint" else "Amazon S3"
            return {
                "ResultsByTime": [
                    {
                        "Groups": [
                            {
                                "Keys": [group_key],
                                "Metrics": {"UnblendedCost": {"Amount": "9.0231738003"}},
                            }
                        ]
                    }
                ]
            }
        return {"ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "1.23"}}}]}


def _cost_config(**overrides: str) -> CostConfig:
    env = {"SNAPSHOT_BUCKET": "b", **overrides}
    return CostConfig.from_env(env)


def test_cost_writes_one_object_with_a_separate_covered_through() -> None:
    """COST-04: `covered_through` is not `collected_at`. Cost Explorer lags 24-48h."""
    s3 = _RecordingS3()
    run_cost(config=_cost_config(), ce_client=_FakeCE(), s3_client=s3, clock=lambda: FIXED_NOW)
    assert len(s3.puts) == 1
    payload = s3.payload
    assert payload["collected_at"] == FIXED_NOW.isoformat()
    assert payload["covered_through"] == "2026-08-06"
    assert payload["schema_version"] == "v1-cost"
    assert s3.puts[0]["Key"] == "cost/current.json"


def test_cost_classifies_the_unattributed_group_before_storing() -> None:
    """COST-02: the classification happens at collection, not in the UI."""
    s3 = _RecordingS3()
    run_cost(config=_cost_config(), ce_client=_FakeCE(), s3_client=s3, clock=lambda: FIXED_NOW)
    by_blueprint = s3.payload["by_blueprint"]
    assert by_blueprint["attributed"] == []
    assert by_blueprint["unattributed"] == "9.0231738003"
    assert by_blueprint["fully_unattributed"] is True


def test_cost_records_its_own_call_count() -> None:
    """COST-06 / NFR-T8: the dashboard must be able to show what it costs, from measurement."""
    s3 = _RecordingS3()
    ce = _FakeCE()
    run_cost(config=_cost_config(), ce_client=ce, s3_client=s3, clock=lambda: FIXED_NOW)
    assert s3.payload["ce_calls"] == ce.calls == 7


def test_exceeding_the_call_budget_fails_and_writes_nothing() -> None:
    """COST-05: a budget is a failure, not a cap -- truncating would under-report spend."""
    s3 = _RecordingS3()
    with pytest.raises(CostFailure) as caught:
        run_cost(
            config=_cost_config(MAX_CE_CALLS="3"),
            ce_client=_FakeCE(),
            s3_client=s3,
            clock=lambda: FIXED_NOW,
        )
    assert caught.value.reason is CostReason.CALL_BUDGET_EXCEEDED
    assert s3.puts == []


def test_any_upstream_failure_writes_nothing() -> None:
    """COST-07: fail whole. A partial cost object would render missing groups as zero spend."""
    s3 = _RecordingS3()
    with pytest.raises(CostFailure):
        run_cost(
            config=_cost_config(),
            ce_client=_FakeCE(fail_on=5),
            s3_client=s3,
            clock=lambda: FIXED_NOW,
        )
    assert s3.puts == []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AccessDeniedException", CostReason.ACCESS_DENIED),
        ("ThrottlingException", CostReason.UPSTREAM_THROTTLED),
        ("SomethingElse", CostReason.UPSTREAM_UNAVAILABLE),
    ],
)
def test_access_denied_is_its_own_reason(code: str, expected: CostReason) -> None:
    """The measured linked-account case is PERMANENT, unlike every other reason here.

    Amendment A3.3: this account cannot activate cost allocation tags at any privilege level -- only
    the Organization payer can. So retrying tomorrow fails identically, and the alarm on this reason
    must tell a human to escalate rather than to wait.
    """
    with pytest.raises(CostFailure) as caught:
        run_cost(
            config=_cost_config(),
            ce_client=_FakeCE(fail_on=1, error=_client_error(code)),
            s3_client=_RecordingS3(),
            clock=lambda: FIXED_NOW,
        )
    assert caught.value.reason is expected


def test_amounts_are_kept_as_exact_decimal_strings() -> None:
    """COST-01: no float narrowing anywhere on the way through."""
    s3 = _RecordingS3()
    run_cost(config=_cost_config(), ce_client=_FakeCE(), s3_client=s3, clock=lambda: FIXED_NOW)
    assert s3.payload["by_service"][0]["amount"] == "9.0231738003"


# ---------------------------------------------------------------------------------------------
# C-11 telemetry collector
# ---------------------------------------------------------------------------------------------


class _FakeCW:
    """`list_metrics` via paginator, `get_metric_data` returning one value per query."""

    def __init__(
        self,
        models: tuple[str, ...] = ("nova-lite",),
        fail_list: bool = False,
        fail_data: bool = False,
        values: bool = True,
    ) -> None:
        self.models = models
        self.fail_list = fail_list
        self.fail_data = fail_data
        self.values = values
        self.data_calls = 0

    def get_paginator(self, name: str) -> Any:
        if self.fail_list:
            raise _client_error("AccessDeniedException")
        models = self.models

        class _Pager:
            def paginate(self, **_: Any) -> list[dict[str, Any]]:
                return [
                    {
                        "Metrics": [
                            {"Dimensions": [{"Name": "ModelId", "Value": m}]} for m in models
                        ]
                    }
                ]

        return _Pager()

    def get_metric_data(self, **kwargs: Any) -> dict[str, Any]:
        self.data_calls += 1
        if self.fail_data:
            raise _client_error("ThrottlingException")
        return {
            "MetricDataResults": [
                {"Id": q["Id"], "Values": [2.0] if self.values else []}
                for q in kwargs["MetricDataQueries"]
            ]
        }


def _telemetry_config(**overrides: str) -> TelemetryConfig:
    return TelemetryConfig.from_env({"SNAPSHOT_BUCKET": "b", **overrides})


def _catalog(emitting: bool = False) -> Any:
    blueprints: dict[str, Any] = {"hello-world": {"emits": False}, "teams-bot": {"emits": False}}
    if emitting:
        blueprints["teams-bot"] = {
            "emits": True,
            "namespace": "Cornell/Blueprints/teams-bot",
            "counters": [
                {"name": "queries_answered", "unit": "Count", "description": "queries served"}
            ],
        }
    return parse_catalog(
        json.dumps({"schema_version": CATALOG_SCHEMA_VERSION, "blueprints": blueprints})
    )


def test_telemetry_writes_its_own_object() -> None:
    s3 = _RecordingS3()
    run_telemetry(
        config=_telemetry_config(),
        cw_client=_FakeCW(),
        s3_client=s3,
        catalog=_catalog(),
        clock=lambda: FIXED_NOW,
    )
    assert s3.puts[0]["Key"] == "telemetry/current.json"
    assert s3.payload["schema_version"] == "v1-telemetry"


def test_no_declared_counters_is_not_instrumented_not_a_read_failure() -> None:
    """NFR-T7: conflating these would send an operator to debug CloudWatch instead of instrumenting."""
    s3 = _RecordingS3()
    run_telemetry(
        config=_telemetry_config(),
        cw_client=_FakeCW(),
        s3_client=s3,
        catalog=_catalog(),
        clock=lambda: FIXED_NOW,
    )
    declared = s3.payload["declared"]
    assert declared["state"] == TelemetryState.NOT_INSTRUMENTED.value
    assert declared["not_instrumented"] == ["hello-world", "teams-bot"]
    assert declared["counters"] == []


def test_aws_half_still_written_when_the_declared_half_fails() -> None:
    """TEL-05: independence. This is the opposite of the cost collector's policy, on purpose."""
    s3 = _RecordingS3()
    cw = _FakeCW()
    calls = {"n": 0}
    original = cw.get_metric_data

    def failing(**kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 2:  # the declared half
            raise _client_error("ThrottlingException")
        return original(**kwargs)

    cw.get_metric_data = failing  # type: ignore[method-assign]
    run_telemetry(
        config=_telemetry_config(),
        cw_client=cw,
        s3_client=s3,
        catalog=_catalog(emitting=True),
        clock=lambda: FIXED_NOW,
    )
    payload = s3.payload
    assert payload["aws"]["state"] == TelemetryState.OK.value
    assert payload["aws"]["counters"], "real AWS data must survive the other half failing"
    assert payload["declared"]["state"] == TelemetryState.CANNOT_READ.value


def test_both_halves_unreadable_writes_nothing() -> None:
    """The one case where telemetry does fail whole: there is genuinely nothing to write."""
    s3 = _RecordingS3()
    with pytest.raises(TelemetryFailure):
        run_telemetry(
            config=_telemetry_config(),
            cw_client=_FakeCW(fail_list=True, fail_data=True),
            s3_client=s3,
            catalog=_catalog(emitting=True),
            clock=lambda: FIXED_NOW,
        )
    assert s3.puts == []


def test_metric_budget_is_enforced_rather_than_truncated() -> None:
    """TEL-10: the model list is discovered, so the request count is a product, not a constant."""
    s3 = _RecordingS3()
    many = tuple(f"model-{i}" for i in range(50))
    run_telemetry(
        config=_telemetry_config(MAX_METRICS="10"),
        cw_client=_FakeCW(models=many),
        s3_client=s3,
        catalog=_catalog(),
        clock=lambda: FIXED_NOW,
    )
    # The AWS half refuses rather than reading a silent subset of models.
    assert s3.payload["aws"]["state"] == TelemetryState.CANNOT_READ.value


def test_no_datapoints_is_no_data_yet_not_zero() -> None:
    """NFR-T7 at the counter level: "unused" and "unmeasured" must not render alike."""
    s3 = _RecordingS3()
    run_telemetry(
        config=_telemetry_config(),
        cw_client=_FakeCW(values=False),
        s3_client=s3,
        catalog=_catalog(),
        clock=lambda: FIXED_NOW,
    )
    states = {c["state"] for c in s3.payload["aws"]["counters"]}
    assert states == {TelemetryState.NO_DATA_YET.value}


def test_only_declared_counters_are_requested() -> None:
    """TEL-03 / NFR-T5: an undeclared counter in CloudWatch is not read."""
    s3 = _RecordingS3()
    run_telemetry(
        config=_telemetry_config(),
        cw_client=_FakeCW(),
        s3_client=s3,
        catalog=_catalog(emitting=True),
        clock=lambda: FIXED_NOW,
    )
    names = {c["name"] for c in s3.payload["declared"]["counters"]}
    assert names == {"queries_answered"}


def test_aws_metrics_are_labelled_account_scoped() -> None:
    """They carry no cornell:deployment-id, so attributing them to one would be fabrication."""
    s3 = _RecordingS3()
    run_telemetry(
        config=_telemetry_config(),
        cw_client=_FakeCW(),
        s3_client=s3,
        catalog=_catalog(),
        clock=lambda: FIXED_NOW,
    )
    assert {c["deployment_id"] for c in s3.payload["aws"]["counters"]} == {"account"}
