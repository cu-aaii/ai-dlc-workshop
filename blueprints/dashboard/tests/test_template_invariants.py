"""Two template invariants that are silent when wrong and unguardable by cfn-lint (business-logic-model.md).

These are text assertions over dashboard.yml rather than code tests -- unusual, and recorded as such,
because nothing else catches a bundler-driven CSP loosening or a flipped cache policy before deploy.
"""

from __future__ import annotations

from pathlib import Path

_TEMPLATE = (Path(__file__).resolve().parent.parent / "infra" / "dashboard.yml").read_text()

# Managed CloudFront cache policy IDs (see dashboard.yml).
_CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
_CACHING_OPTIMIZED = "658327ea-f89d-4fab-a63d-7e88639e58f6"


def test_csp_has_no_unsafe_inline_or_eval() -> None:
    # SEC-2 / ER-04: the strict CSP is the whole reason the UI disables Vite's modulepreload polyfill.
    assert "default-src 'none'" in _TEMPLATE
    assert "unsafe-inline" not in _TEMPLATE
    assert "unsafe-eval" not in _TEMPLATE


def test_api_path_is_no_cache_and_site_is_cached() -> None:
    # ER-03: /api/* must not cache (two viewers disagreeing about freshness is the US-05 failure),
    # while the static site is cached (P-6). Assert both the path pattern and the two policy ids.
    assert "/api/*" in _TEMPLATE
    assert _CACHING_DISABLED in _TEMPLATE  # applied to the /api/* behavior
    assert _CACHING_OPTIMIZED in _TEMPLATE  # applied to the default (site) behavior


def test_collector_schedule_has_no_retries() -> None:
    # Q6: fail-clean scheduled collector -- no DLQ, no retries. The alarm is the signal.
    assert "MaximumRetryAttempts: 0" in _TEMPLATE


# --- FR-9 / FR-10 _TEMPLATE invariants ---------------------------------------------------------


def test_new_functions_reuse_the_collector_image_rather_than_new_targets() -> None:
    """The Q3 refinement: one digest across four functions cannot drift; four images can.

    If someone later gives these their own image URIs, this fails -- which is the point, because it
    would also mean two new Build actions in a pipeline.yml with ~800 bytes of headroom.
    """
    for handler in ("dashboard.cost.handler.handler", "dashboard.telemetry.handler.handler"):
        assert handler in _TEMPLATE, f"{handler} must be wired via ImageConfig.Command"
    assert _TEMPLATE.count("ImageConfig") >= 2
    # No third or fourth image parameter crept in.
    assert "CostImageUri" not in _TEMPLATE
    assert "TelemetryImageUri" not in _TEMPLATE


def test_each_collector_writes_only_its_own_key() -> None:
    """A4.1: per-key IAM is what makes "one writer per object" a permission, not a convention."""
    assert "${CostKey}" in _TEMPLATE
    assert "${TelemetryKey}" in _TEMPLATE
    # The wildcard that would undo it.
    assert "-snapshot-${AWS::AccountId}/*" not in _TEMPLATE


def test_the_rate_table_ships_empty() -> None:
    """COST-14 / FR-10.8: a guessed per-model rate is confident wrong money, so ship none."""
    assert "model-rates" in _TEMPLATE
    assert "Value: '{}'" in _TEMPLATE


def test_access_denied_has_its_own_alarm() -> None:
    """It is the one PERMANENT failure here -- only the Organization payer can clear it."""
    assert "CostAccessDeniedAlarm" in _TEMPLATE
    assert "access_denied" in _TEMPLATE
    assert "Escalate rather than wait" in _TEMPLATE


def test_new_log_groups_have_shorter_retention_than_the_originals() -> None:
    """NFR-T8: CloudWatch is already ~18% of this account's spend, so 30 days was not the default."""
    assert "RetentionInDays: 14" in _TEMPLATE


def test_cost_schedule_is_a_parameter_and_defaults_to_daily() -> None:
    """FR-10.4: hourly Cost Explorer polling would cost ~$5/mo against a ~$9/mo account."""
    assert "CostScheduleExpression" in _TEMPLATE
    assert "rate(1 day)" in _TEMPLATE
