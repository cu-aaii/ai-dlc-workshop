import asyncio

from builder_mcp import server

EXPECTED_TOOLS = {
    "blueprint_search",
    "create_deployment",
    "deployment_status",
    "propose_change",
    "health_check",
    "restart_deployment",
    "export_spec",
}


def test_all_seven_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_blueprint_search_returns_full_contract():
    result = server.blueprint_search("prove the deploy path")
    assert result["results"][0]["name"] == "hello-world"
    assert "inputs" in result["results"][0]
    assert "cost" in result["results"][0]


def test_create_deployment_dry_run_needs_no_credentials():
    result = server.create_deployment(
        blueprint="hello-world", deployment_name="ignored-for-singleton",
        owner_netid="tmf77", dry_run=True,
    )
    assert result["dry_run"] is True
    plan = result["plan"]
    # singleton blueprint pins its own name; stack follows <app>-<env>-<name>
    assert plan["stack"] == "aidlc-main-hello-world"
    assert plan["registration_pr"]["edits"].startswith("pipeline/pipeline.yml")
    assert "human approves" in plan["governance"]


def test_create_deployment_rejects_bad_inputs():
    result = server.create_deployment(
        blueprint="no-such-blueprint", deployment_name="x", owner_netid="tmf77",
    )
    assert "error" in result


def test_propose_change_dry_run_plans_a_pr_not_a_push():
    result = server.propose_change(
        repo="deploy-hello-world", title="Tune README", description="d",
        files={"README.md": "hi"}, dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["plan"]["repo"] == "cu-aaii/deploy-hello-world"
    assert result["plan"]["branch"].startswith("propose/")
