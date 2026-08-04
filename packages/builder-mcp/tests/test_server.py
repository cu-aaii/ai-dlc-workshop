import asyncio
import dataclasses

from builder_mcp import server

EXPECTED_TOOLS = {
    "blueprint_search",
    "deployment_create",
    "deployment_read",
    "deployment_update",
    "deployment_health",
    "deployment_restart",
    "deployment_delete",
    "spec_export",
}


def test_all_eight_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_blueprint_search_returns_full_contract():
    result = server.blueprint_search("prove the deploy path")
    assert result["results"][0]["name"] == "hello-world"
    assert "inputs" in result["results"][0]
    assert "cost" in result["results"][0]


def test_deployment_create_dry_run_needs_no_credentials():
    # default deployment mode is 'folder' (testing phase): the shell lands in
    # outputs/<name>/ in the workshop repo, same PR as the pipeline action — no new repo.
    result = server.deployment_create(
        blueprint="hello-world", deployment_name="ignored-for-singleton",
        owner_netid="tmf77", dry_run=True,
    )
    assert result["dry_run"] is True
    plan = result["plan"]
    # singleton blueprint pins its own name; stack follows <app>-<env>-<name>
    assert plan["stack"] == "aidlc-main-hello-world"
    assert plan["registration_pr"]["edits"].startswith("pipeline/pipeline.yml")
    assert "human approves" in plan["governance"]
    assert plan["shell_folder"].startswith("outputs/hello-world/")
    assert "same PR" in plan["shell_folder"]
    assert "new_repo" not in plan


def test_deployment_create_repo_mode_still_plans_a_new_repo(monkeypatch):
    # the stashed target-state path (D1/D5): BUILDER_MCP_DEPLOYMENT_MODE=repo restores it
    monkeypatch.setattr(
        server, "settings", dataclasses.replace(server.settings, deployment_mode="repo")
    )
    result = server.deployment_create(
        blueprint="hello-world", deployment_name="ignored-for-singleton",
        owner_netid="tmf77", dry_run=True,
    )
    plan = result["plan"]
    assert plan["new_repo"] == "cu-aaii/deploy-hello-world"
    assert "shell_folder" not in plan


def test_deployment_create_rejects_bad_inputs():
    result = server.deployment_create(
        blueprint="no-such-blueprint", deployment_name="x", owner_netid="tmf77",
    )
    assert "error" in result


def test_deployment_update_folder_mode_redirects_deploy_repo_targets():
    # folder mode (the default): deploy-* repos do not exist; the error explains where
    # the shell actually lives and how to target it.
    result = server.deployment_update(
        repo="deploy-hello-world", title="Tune README", description="d",
        files={"README.md": "hi"}, dry_run=True,
    )
    assert "folder" in result["error"]
    assert "outputs/hello-world/" in result["error"]


def test_deployment_update_dry_run_plans_a_pr_not_a_push(monkeypatch):
    monkeypatch.setattr(
        server, "settings", dataclasses.replace(server.settings, deployment_mode="repo")
    )
    result = server.deployment_update(
        repo="deploy-hello-world", title="Tune README", description="d",
        files={"README.md": "hi"}, dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["plan"]["repo"] == "cu-aaii/deploy-hello-world"
    assert result["plan"]["branch"].startswith("propose/")


def test_deployment_update_workshop_repo_stays_allowlisted_in_folder_mode():
    result = server.deployment_update(
        repo="ai-dlc-workshop", title="Tune shell", description="d",
        files={"outputs/hello-world/README.md": "hi"}, dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["plan"]["repo"] == "cu-aaii/ai-dlc-workshop"


def test_deployment_delete_dry_run_needs_no_credentials():
    result = server.deployment_delete(deployment_name="hello-world", dry_run=True)
    assert result["dry_run"] is True
    plan = result["plan"]
    assert plan["stack"] == "aidlc-main-hello-world"
    assert plan["deregistration_pr"]["branch"] == "undeploy/hello-world"
    assert "HelloWorldCloudFormation" in plan["deregistration_pr"]["edits"]
    # folder mode (default): teardown is symmetric — the PR also removes the shell folder
    assert "outputs/hello-world/" in plan["deregistration_pr"]["edits"]
    # the governance invariant: a delete is a PR, never an AWS delete call
    assert "DeletionPolicy" in plan["warning"]
    assert "human approves" in plan["governance"]


def test_deployment_delete_repo_mode_leaves_shell_folder_out(monkeypatch):
    monkeypatch.setattr(
        server, "settings", dataclasses.replace(server.settings, deployment_mode="repo")
    )
    result = server.deployment_delete(deployment_name="hello-world", dry_run=True)
    assert "outputs/" not in result["plan"]["deregistration_pr"]["edits"]


def test_deployment_delete_rejects_bad_name():
    result = server.deployment_delete(deployment_name="Not_A_Valid_Name!", dry_run=True)
    assert "error" in result


def test_deployment_mode_env_default_and_fallback(monkeypatch):
    from builder_mcp.config import _resolve_deployment_mode

    monkeypatch.delenv("BUILDER_MCP_DEPLOYMENT_MODE", raising=False)
    assert _resolve_deployment_mode() == "folder"  # testing-phase default
    monkeypatch.setenv("BUILDER_MCP_DEPLOYMENT_MODE", "repo")
    assert _resolve_deployment_mode() == "repo"
    monkeypatch.setenv("BUILDER_MCP_DEPLOYMENT_MODE", "bogus")
    assert _resolve_deployment_mode() == "folder"  # degrade, never crash (NFR7)
