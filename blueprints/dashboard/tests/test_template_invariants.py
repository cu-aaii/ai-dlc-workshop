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
