"""Security-remediation tests: F1 path denylist, SECURITY-05 input caps, SECURITY-09
safe errors, SECURITY-15 error contract (tools never raise to the transport)."""

from pathlib import Path

import httpx
import pytest

from builder_mcp import server
from builder_mcp.config import Settings
from builder_mcp.patching import DEPLOYMENT_NAME_PATTERN
from builder_mcp.validation import (
    MAX_FILE_COUNT,
    MAX_FILES_TOTAL_BYTES,
    file_path_problem,
    files_problem,
    owner_netid_problem,
    safe_error,
)


# -- F1: the path denylist ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/deploy.yml",
        ".github/workflows/x.yaml",
        ".github/anything",
        ".github",
        "../x",
        "a/../../etc/passwd",
        "docs/..",
        "/etc/passwd",
        "\\windows\\path",
        "C:/temp/x",
        "c:evil",
    ],
)
def test_denylist_rejects_dangerous_paths(path):
    problem = file_path_problem(path)
    assert problem is not None
    assert repr(path) in problem  # the narrative names the offending path


@pytest.mark.parametrize("path", ["README.md", "deployment.yaml", "docs/notes.md", "a/b/c.txt"])
def test_denylist_allows_ordinary_repo_paths(path):
    assert file_path_problem(path) is None


def test_deployment_update_refuses_workflow_files_even_in_dry_run():
    result = server.deployment_update(
        repo="deploy-hello-world", title="t", description="d",
        files={".github/workflows/deploy.yml": "on: push"}, dry_run=True,
    )
    assert ".github/workflows/deploy.yml" in result["error"]


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd"])
def test_deployment_update_refuses_traversal_and_absolute_paths(bad):
    result = server.deployment_update(
        repo="deploy-hello-world", title="t", description="d",
        files={bad: "x"}, dry_run=True,
    )
    assert bad in result["error"]


def test_deployment_update_refuses_out_of_scope_repos():
    result = server.deployment_update(
        repo="someone-else/some-repo", title="t", description="d",
        files={"README.md": "x"}, dry_run=True,
    )
    assert "write scope" in result["error"]


# -- SECURITY-05: input validation caps --------------------------------------------------


def test_deployment_create_rejects_non_netid_owner():
    result = server.deployment_create(
        blueprint="hello-world", deployment_name="hello-world",
        owner_netid="Robert'); DROP TABLE--", dry_run=True,
    )
    assert "NetID" in result["error"]


def test_deployment_update_rejects_too_many_files():
    files = {f"f{i}.txt": "x" for i in range(MAX_FILE_COUNT + 1)}
    result = server.deployment_update(
        repo="deploy-hello-world", title="t", description="d", files=files, dry_run=True,
    )
    assert "cap" in result["error"]


def test_deployment_update_rejects_oversized_content():
    files = {"big.txt": "x" * (MAX_FILES_TOTAL_BYTES + 1)}
    result = server.deployment_update(
        repo="deploy-hello-world", title="t", description="d", files=files, dry_run=True,
    )
    assert "cap" in result["error"]


def test_deployment_update_rejects_oversized_title():
    result = server.deployment_update(
        repo="deploy-hello-world", title="t" * 201, description="d",
        files={"README.md": "x"}, dry_run=True,
    )
    assert "cap" in result["error"]


def test_owner_netid_pattern():
    assert owner_netid_problem("tmf77") is None
    assert owner_netid_problem("abcd12345") is None
    for bad in ("", "TMF77", "tmf", "77tmf", "t7", "a" * 30, "tmf77; rm -rf"):
        assert owner_netid_problem(bad) is not None


def test_name_pattern_rejects_consecutive_hyphens():
    assert DEPLOYMENT_NAME_PATTERN.match("a-a")
    assert not DEPLOYMENT_NAME_PATTERN.match("a--a")
    result = server.deployment_delete(deployment_name="a--a", dry_run=True)
    assert "error" in result


# -- SECURITY-15: tools surface {"error": ...}, never raise ------------------------------


def _settings(repo_root):
    return Settings(
        github_org="cu-aaii", workshop_repo="ai-dlc-workshop", application="aidlc",
        environment="main", aws_region="us-east-1", github_token=None,
        repo_root=repo_root,
    )


def test_blueprint_search_errors_cleanly_when_catalog_root_missing(monkeypatch):
    monkeypatch.setattr(server, "settings", _settings(Path("Z:/no-such-checkout")))
    result = server.blueprint_search("anything")  # must not raise
    assert "catalog" in result["error"]


def test_blueprint_search_errors_cleanly_when_github_unreachable(monkeypatch):
    monkeypatch.setattr(server, "settings", _settings(None))

    def offline(settings):
        raise httpx.ConnectError("simulated offline")

    monkeypatch.setattr("builder_mcp.catalog._load_remote", offline)
    result = server.blueprint_search("anything")  # must not raise
    assert "error" in result
    assert "ConnectError" in result["error"]


def test_deployment_create_errors_cleanly_when_catalog_root_missing(monkeypatch):
    monkeypatch.setattr(server, "settings", _settings(Path("Z:/no-such-checkout")))
    result = server.deployment_create(
        blueprint="hello-world", deployment_name="hello-world",
        owner_netid="tmf77", dry_run=True,
    )
    assert "catalog" in result["error"]


# -- SECURITY-09: safe error rendering ---------------------------------------------------


def test_safe_error_is_one_line_with_class_and_redaction():
    error = RuntimeError(
        "boom token=ghp_secret123 at arn:aws:iam::123456789012:role/x\ntraceback line 2"
    )
    result = safe_error(error, "doing the thing")
    assert result["error"].startswith("doing the thing failed (RuntimeError)")
    assert "\n" not in result["error"]
    assert "ghp_secret123" not in result["error"]
    assert "123456789012" not in result["error"]


def test_files_problem_requires_map():
    assert files_problem({}) is not None
    assert files_problem("not a dict") is not None
    assert files_problem({"a.txt": "ok"}) is None
