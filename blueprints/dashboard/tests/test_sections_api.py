"""The FR-9/FR-10 read path, end to end through `run` (A4.1, FR-9.5.5, NFR-T7).

The behaviour these tests exist to pin down is **per-section independence**: cost being absent must not
degrade a usage response, and vice versa. That is a requirement rather than an optimisation -- with no
blueprint instrumented, usage is empty while cost has real data, so a viewer will routinely see one
populated panel beside an unpopulated one, and collapsing them would misreport both.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest

from dashboard.api.config import ApiConfig
from dashboard.api.handler import run

BUCKET = "test-bucket"


class _FakeS3:
    """Serves objects by key; a key not present raises a NoSuchKey-shaped error."""

    def __init__(self, objects: dict[str, bytes], unreadable: set[str] | None = None) -> None:
        self.objects = objects
        self.unreadable = unreadable or set()

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        if Key in self.unreadable:
            raise RuntimeError("boom")
        if Key not in self.objects:
            error = type("NoSuchKey", (Exception,), {})
            raise error(f"no such key")
        return {"Body": BytesIO(self.objects[Key])}


def _config() -> ApiConfig:
    return ApiConfig.from_env({"SNAPSHOT_BUCKET": BUCKET})


def _event(path: str) -> dict[str, Any]:
    return {"requestContext": {"http": {"method": "GET", "path": path}}}


def _cost_payload() -> bytes:
    return json.dumps(
        {
            "schema_version": "v1-cost",
            "collected_at": "2026-08-07T00:00:00+00:00",
            "covered_through": "2026-08-06",
            "currency": "USD",
            "totals": {"day": "0.31", "month_to_date": "9.0231738003", "year_to_date": "12.30"},
            "by_service": [{"key": "Amazon OpenSearch Service", "amount": "6.4436666667"}],
            "by_usage_type": [{"key": "USE1-NovaLite-input-tokens", "amount": "0.0000123"}],
            "by_blueprint": {
                "attributed": [],
                "unattributed": "9.0231738003",
                "fully_unattributed": True,
            },
            "by_deployment": {"attributed": [], "unattributed": "9.02", "fully_unattributed": True},
            "ce_calls": 7,
        }
    ).encode()


def _telemetry_payload() -> bytes:
    return json.dumps(
        {
            "schema_version": "v1-telemetry",
            "collected_at": "2026-08-07T01:00:00+00:00",
            "window": {"start": "2026-08-06T01:00:00+00:00", "end": "2026-08-07T01:00:00+00:00"},
            "aws": {
                "state": "ok",
                "counters": [
                    {
                        "deployment_id": "account",
                        "agent_id": "account",
                        "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                        "name": "Invocations",
                        "value": 2.0,
                        "state": "ok",
                    },
                    {
                        "deployment_id": "account",
                        "agent_id": "account",
                        "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                        "name": "InputTokenCount",
                        "value": 14.0,
                        "state": "ok",
                    },
                    {
                        "deployment_id": "account",
                        "agent_id": "account",
                        "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                        "name": "OutputTokenCount",
                        "value": 4.0,
                        "state": "ok",
                    },
                ],
            },
            "declared": {
                "state": "not_instrumented",
                "counters": [],
                "not_instrumented": ["hello-world", "teams-bot"],
                "emitting": [],
            },
        }
    ).encode()


def _body(response: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(response["body"])
    return parsed


# ---------------------------------------------------------------------------------------------
# Per-section independence -- the point of A4.1
# ---------------------------------------------------------------------------------------------


def test_usage_is_served_when_cost_is_absent() -> None:
    """A missing cost object must not affect a usage response."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    response = run(_event("/api/usage/models"), config=_config(), s3_client=s3)
    assert response["statusCode"] == 200
    body = _body(response)
    assert body["state"] == "ok"
    assert body["data"]["models"][0]["input_tokens"] == 14


def test_cost_is_served_when_telemetry_is_absent() -> None:
    """And the converse -- the state today, since no blueprint is instrumented."""
    s3 = _FakeS3({"cost/current.json": _cost_payload()})
    response = run(_event("/api/cost/breakdown"), config=_config(), s3_client=s3)
    assert _body(response)["state"] == "ok"


def test_absent_section_is_200_with_a_state_not_an_error_status() -> None:
    """A section's absence is carried in `state`, not in the HTTP status (see `section_response`)."""
    response = run(_event("/api/cost/summary"), config=_config(), s3_client=_FakeS3({}))
    assert response["statusCode"] == 200
    body = _body(response)
    assert body["state"] == "absent"
    assert body["data"] is None


def test_unreadable_section_is_distinguished_from_absent() -> None:
    """NFR-T7: "never collected" and "collected but unreadable" are different operator actions."""
    s3 = _FakeS3({"cost/current.json": b"{}"}, unreadable={"cost/current.json"})
    body = _body(run(_event("/api/cost/summary"), config=_config(), s3_client=s3))
    assert body["state"] == "unreadable"


def test_malformed_section_json_is_unreadable_not_a_crash() -> None:
    s3 = _FakeS3({"cost/current.json": b"not json at all"})
    body = _body(run(_event("/api/cost/summary"), config=_config(), s3_client=s3))
    assert body["state"] == "unreadable"


# ---------------------------------------------------------------------------------------------
# The A3.3 trap, end to end
# ---------------------------------------------------------------------------------------------


def test_unattributed_cost_is_never_presented_as_a_blueprint(  # noqa: D103
) -> None:
    """FR-10.3.6 / US-17 through the API: the unattributed bucket stays a named sibling.

    This is the measured case -- the real account returns 100% of spend under `cornell:blueprint$`.
    """
    s3 = _FakeS3({"cost/current.json": _cost_payload()})
    data = _body(run(_event("/api/cost/breakdown"), config=_config(), s3_client=s3))["data"]
    assert data["by_blueprint"]["attributed"] == []
    assert data["by_blueprint"]["unattributed"] == "9.0231738003"
    assert data["by_blueprint"]["fully_unattributed"] is True
    # And no group anywhere is keyed with the bare tag key.
    assert "cornell:blueprint$" not in json.dumps(data["by_blueprint"]["attributed"])


# ---------------------------------------------------------------------------------------------
# Estimates, rates, and the not-instrumented states
# ---------------------------------------------------------------------------------------------


def test_estimate_flag_is_in_the_body_not_only_the_ui() -> None:
    """COST-10 / NFR-T1: a JSON consumer must not be able to lose the distinction."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/models"), config=_config(), s3_client=s3))["data"]
    assert data["is_estimate"] is True


def test_no_rates_configured_reports_missing_not_zero() -> None:
    """COST-09/COST-14: the shipped rate table is empty, so every model must say so."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/models"), config=_config(), s3_client=s3))["data"]
    assert data["rates_state"] == "not_configured"
    assert data["models"][0]["rate_missing"] is True
    assert data["models"][0]["estimated_cost"] is None
    assert data["missing_rates"]


def test_malformed_rate_table_is_reported_not_silently_empty() -> None:
    config = ApiConfig.from_env({"SNAPSHOT_BUCKET": BUCKET, "MODEL_RATES": "{not json"})
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/models"), config=config, s3_client=s3))["data"]
    assert data["rates_state"] == "malformed"


def test_configured_rates_produce_a_decimal_estimate() -> None:
    rates = json.dumps(
        {
            "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
                "input": "0.001",
                "output": "0.005",
                "per_unit": 1000,
            }
        }
    )
    config = ApiConfig.from_env({"SNAPSHOT_BUCKET": BUCKET, "MODEL_RATES": rates})
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/models"), config=config, s3_client=s3))["data"]
    assert data["models"][0]["rate_missing"] is False
    assert data["models"][0]["estimated_cost"] is not None
    assert data["rates_state"] == "ok"


def test_uninstrumented_blueprints_are_named_not_blank() -> None:
    """FR-9.7.3: the empty state must say WHICH blueprints report nothing."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/quality"), config=_config(), s3_client=s3))["data"]
    assert data["not_instrumented"] == ["hello-world", "teams-bot"]
    assert data["declared_state"] == "not_instrumented"


def test_application_semantic_rates_are_not_instrumented_not_zero() -> None:
    """US-22: approval and success rates report their absence rather than a reassuring 0%."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/quality"), config=_config(), s3_client=s3))["data"]
    for key in ("approval_rate", "success_rate", "timeout_rate"):
        assert data[key]["rate"] is None
        assert data[key]["state"] == "not_instrumented"


def test_aws_error_rate_has_real_data_and_keeps_its_counts() -> None:
    """A3.1: error rate comes from AWS metrics, so it works with no instrumentation. TEL-06 counts."""
    s3 = _FakeS3({"telemetry/current.json": _telemetry_payload()})
    data = _body(run(_event("/api/usage/quality"), config=_config(), s3_client=s3))["data"]
    error_rate = data["error_rate"]
    # No InvocationClientErrors datapoints in the fixture, but Invocations has 2 -> not_instrumented
    # for the numerator, which must surface rather than being read as a 0% error rate.
    assert error_rate["rate"] is None
    assert error_rate["state"] == "not_instrumented"


# ---------------------------------------------------------------------------------------------
# US-19 -- cost per completed task
# ---------------------------------------------------------------------------------------------


def test_cost_per_task_reports_no_tasks_rather_than_zero() -> None:
    """COST-12 / US-19: with no completed-task counter there is no figure, not a zero."""
    s3 = _FakeS3(
        {"cost/current.json": _cost_payload(), "telemetry/current.json": _telemetry_payload()}
    )
    per_task = _body(run(_event("/api/cost/summary"), config=_config(), s3_client=s3))["per_task"]
    assert per_task["outcome"] == "no_tasks"
    assert per_task["amount"] is None


def test_cost_per_task_needs_both_sections() -> None:
    """Derived from half the data would be wrong in a way the number cannot show."""
    s3 = _FakeS3({"cost/current.json": _cost_payload()})
    per_task = _body(run(_event("/api/cost/summary"), config=_config(), s3_client=s3))["per_task"]
    assert per_task["state"] == "absent"
    assert per_task["outcome"] is None


# ---------------------------------------------------------------------------------------------
# Route table + boundary
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/cost", "/api/cost/", "/api/usage", "/api/cost/summary/extra", "/api/COST/summary"],
)
def test_near_miss_paths_are_404_with_no_storage_access(path: str) -> None:
    """The table stays closed: SEC-5 validation is structural, not a parameter check."""

    class _Exploding:
        def get_object(self, **_: Any) -> dict[str, Any]:
            raise AssertionError("a 404 route must not touch storage")

    response = run(_event(path), config=_config(), s3_client=_Exploding())
    assert response["statusCode"] == 404


def test_post_to_a_section_route_is_404() -> None:
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/cost/summary"}}}
    assert run(event, config=_config(), s3_client=_FakeS3({}))["statusCode"] == 404


def test_covered_through_is_reported_separately_from_collected_at() -> None:
    """COST-04 / US-16: what the figure covers is not when we asked for it."""
    s3 = _FakeS3({"cost/current.json": _cost_payload()})
    body = _body(run(_event("/api/cost/summary"), config=_config(), s3_client=s3))
    assert body["collected_at"] == "2026-08-07T00:00:00+00:00"
    assert body["data"]["covered_through"] == "2026-08-06"
