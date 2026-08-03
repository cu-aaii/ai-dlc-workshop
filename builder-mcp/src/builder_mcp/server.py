"""Cornell Builder MCP server.

Seven tools that turn plain-language intent into governed deployments through the
existing deploy path. Design constraints this code is downstream of:

- Merge, and nothing else, deploys (D4). No tool here can deploy, merge, or push to a
  tracked branch. create_deployment opens a PR; a human approves it; the pipeline does
  the rest.
- The builder's client holds no credentials (D3). GitHub and AWS calls run server-side.
- Stateless transport. Bedrock AgentCore runs streamable HTTP with no session affinity,
  which also rules out MCP elicitation (no back-channel). The confirm-before-doing UX is
  the dry_run pattern instead: mutating tools default to dry_run=true and return the full
  plan; the client re-calls with dry_run=false to execute.
"""

from __future__ import annotations

import os
from typing import Any

try:  # SDK renamed FastMCP -> MCPServer; support both so the pinned version can float
    from mcp.server.mcpserver import MCPServer as _ServerClass
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _ServerClass

from . import aws_ops, spec_export
from .catalog import load_catalog, search, validate_inputs
from .config import Settings
from .github_ops import GitHubOps
from .patching import (
    DEPLOYMENT_NAME_PATTERN,
    deployment_repo_files,
    insert_blueprint_action,
    render_pipeline_action,
)

settings = Settings.from_env()

mcp = _ServerClass(
    "cornell-builder",
    instructions=(
        "The Cornell Builder: search governed infrastructure blueprints, create "
        "deployments of them, and operate what you deployed. Deployments go live only "
        "when a human approves the pull request this server opens — there is no deploy "
        "button, by design. Mutating tools default to dry_run=true; show the user the "
        "plan and get their confirmation before re-calling with dry_run=false."
    ),
)


def _blueprint_or_error(name: str):
    catalog = load_catalog(settings)
    for blueprint in catalog:
        if blueprint.name == name:
            return blueprint
    return {"error": f"no blueprint named {name!r}; catalog has {[b.name for b in catalog]}"}


@mcp.tool()
def blueprint_search(query: str) -> dict[str, Any]:
    """Search the blueprint catalog with a plain-language description of what you want.

    Returns every blueprint ranked by match quality, each with its full contract
    (inputs, cost, maturity, data classification) so you can gather parameters next.
    """
    ranked = search(load_catalog(settings), query)
    return {
        "query": query,
        "results": [
            {"match_score": round(score, 1), **blueprint.summary_dict()}
            for score, blueprint in ranked
        ],
    }


@mcp.tool()
def create_deployment(
    blueprint: str,
    deployment_name: str,
    owner_netid: str,
    parameters: dict[str, str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a deployment of a blueprint: a new repo in the Cornell GitHub org plus a
    registration pull request that makes the pipeline deploy the stack on merge.

    Always call with dry_run=true first and show the user the plan (repo to be created,
    PR to be opened, stack name, parameters, estimated cost) for confirmation. Nothing
    deploys until a human approves the PR — merge is the only deploy trigger.
    """
    found = _blueprint_or_error(blueprint)
    if isinstance(found, dict):
        return found
    parameters = dict(parameters or {})
    parameters.setdefault("owner_netid", owner_netid)

    problems = validate_inputs(found, parameters)
    if found.singleton:
        deployment_name = found.name  # template hardcodes its identity; one per environment
    elif not DEPLOYMENT_NAME_PATTERN.match(deployment_name):
        problems.append(
            f"deployment_name {deployment_name!r} must match {DEPLOYMENT_NAME_PATTERN.pattern}"
        )
    if problems:
        return {"error": "invalid request", "problems": problems}

    stack_name = settings.stack_name(deployment_name)
    overrides = {
        "Application": settings.application,
        "Environment": settings.environment,
        "Owner": owner_netid,
        **found.pipeline_parameters,
    }
    action_block = render_pipeline_action(deployment_name, found.template, stack_name, overrides)
    repo_name = f"deploy-{deployment_name}"
    shell_files = deployment_repo_files(
        found.name, found.version, found.template, deployment_name,
        stack_name, owner_netid, parameters, settings.workshop_repo_full,
    )

    plan = {
        "blueprint": f"{found.name} v{found.version} ({found.maturity})",
        "stack": stack_name,
        "estimated_cost": found.cost,
        "new_repo": f"{settings.github_org}/{repo_name}",
        "registration_pr": {
            "repo": settings.workshop_repo_full,
            "edits": "pipeline/pipeline.yml — one new BlueprintDeploy action",
            "parameter_overrides": overrides,
        },
        "governance": "Deploys only when a human approves and merges the registration PR.",
    }
    if dry_run:
        return {"dry_run": True, "plan": plan}

    github = GitHubOps(settings)
    results: dict[str, Any] = {"plan": plan}
    results["repo"] = github.create_org_repo(
        repo_name, f"{found.name} v{found.version} deployment owned by {owner_netid}"
    )
    for path, content in shell_files.items():
        github.put_file(
            f"{settings.github_org}/{repo_name}", path, content,
            f"Initialize {deployment_name} shell", "main",
        )
    branch = f"deploy/{deployment_name}"
    github.create_branch(settings.workshop_repo_full, branch)
    if github.can_write:
        pipeline_text, sha = github.get_file(
            settings.workshop_repo_full, "pipeline/pipeline.yml", ref=branch
        )
        patched = insert_blueprint_action(pipeline_text, action_block, stack_name)
        github.put_file(
            settings.workshop_repo_full, "pipeline/pipeline.yml", patched,
            f"Register {stack_name} deployment of {found.name} v{found.version}",
            branch, sha=sha,
        )
    results["pull_request"] = github.create_pull(
        settings.workshop_repo_full,
        branch,
        f"Deploy {found.name} v{found.version} as {stack_name} for {owner_netid}",
        f"Registration PR opened by the Cornell Builder.\n\n"
        f"- Blueprint: `{found.name}` v{found.version}\n- Stack: `{stack_name}`\n"
        f"- Owner: `{owner_netid}`\n- Deployment repo: {settings.github_org}/{repo_name}\n\n"
        "Merging this PR is the deploy action. Review the pipeline action diff carefully.",
    )
    return results


@mcp.tool()
def deployment_status(deployment_name: str) -> dict[str, Any]:
    """Full-chain status of a deployment: registration PR, pipeline stages, and
    CloudFormation stack state."""
    stack_name = settings.stack_name(deployment_name)
    github = GitHubOps(settings)
    try:
        prs = github.open_prs(settings.workshop_repo_full, head_contains=f"deploy/{deployment_name}")
    except Exception as error:  # GitHub unreachable should not hide AWS state
        prs = [{"error": f"could not list PRs: {error}"}]
    return {
        "deployment": deployment_name,
        "open_registration_prs": prs,
        "pipeline": aws_ops.pipeline_state(settings),
        "stack": aws_ops.stack_status(settings, stack_name),
    }


@mcp.tool()
def propose_change(
    repo: str,
    title: str,
    description: str,
    files: dict[str, str],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Propose a change to a deployment repo (or the workshop repo) as a pull request.

    `files` maps repo-relative paths to their full new contents. The change lands on a
    branch and becomes a PR — never a direct push. Call with dry_run=true first and show
    the user what will change.
    """
    repo_full = repo if "/" in repo else f"{settings.github_org}/{repo}"
    branch = f"propose/{abs(hash(title)) % 100000}"
    if dry_run:
        return {
            "dry_run": True,
            "plan": {
                "repo": repo_full,
                "branch": branch,
                "files_changed": sorted(files),
                "pr_title": title,
            },
        }
    github = GitHubOps(settings)
    github.create_branch(repo_full, branch)
    written = []
    for path, content in files.items():
        sha = None
        if github.can_write:
            try:
                _, sha = github.get_file(repo_full, path, ref=branch)
            except Exception:
                sha = None  # new file
        written.append(github.put_file(repo_full, path, content, f"{title}: {path}", branch, sha=sha))
    pr = github.create_pull(repo_full, branch, title, description)
    return {"files": written, "pull_request": pr}


@mcp.tool()
def health_check(deployment_name: str) -> dict[str, Any]:
    """Health of a running deployment: stack status, failure events if any, and an
    inventory audit that every resource carries the four required cornell:* tags."""
    stack_name = settings.stack_name(deployment_name)
    status = aws_ops.stack_status(settings, stack_name)
    return {
        "deployment": deployment_name,
        "stack": status,
        "tag_inventory": aws_ops.tagged_resources(settings, stack_name),
        "healthy": bool(status.get("healthy")),
    }


@mcp.tool()
def restart_deployment(deployment_name: str, dry_run: bool = True) -> dict[str, Any]:
    """Re-run the deployment at its current version: retries the failed pipeline stage if
    one exists, otherwise starts a fresh pipeline execution. Cannot change what is
    deployed — changes require a PR. Call with dry_run=true first."""
    # deployment_name is accepted for symmetry and future per-deployment pipelines; today
    # all blueprint stacks deploy through the one shared pipeline.
    return {"deployment": deployment_name, **aws_ops.restart(settings, dry_run=dry_run)}


@mcp.tool()
def export_spec(deployment_name: str, blueprint: str, audience: str = "coder") -> dict[str, Any]:
    """Export a reviewable spec of a deployment for a given audience: coder (validation),
    narrative (business logic for non-coders), security (auth review), transfer (rebuild
    elsewhere), user (how to use as-is), or offboarding (leaving Cornell)."""
    found = _blueprint_or_error(blueprint)
    if isinstance(found, dict):
        return found
    stack_name = settings.stack_name(deployment_name)
    status = aws_ops.stack_status(settings, stack_name)
    spec = {
        "blueprint": {
            "name": found.name, "version": found.version, "maturity": found.maturity,
            "maintainer": found.maintainer, "summary": found.summary,
            "template": found.template, "inputs": found.inputs, "cost": found.cost,
            "data_classification": found.data_classification, "state": found.state,
        },
        "deployment": {
            "name": deployment_name, "stack": stack_name,
            "owner": status.get("outputs", {}).get("Owner", "see stack parameters"),
            "pipeline": settings.pipeline_name,
            "parameters": status.get("outputs", {}),
        },
        "status": status,
    }
    try:
        markdown = spec_export.render_spec(audience, spec)
    except ValueError as error:
        return {"error": str(error)}
    return {"audience": audience, "spec_markdown": markdown}


def main() -> None:
    transport = os.environ.get("BUILDER_MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    # AgentCore contract: 0.0.0.0:8000, path /mcp, stateless. Locally the defaults bind
    # 127.0.0.1:8000 -- set BUILDER_MCP_HOST=0.0.0.0 and BUILDER_MCP_STATELESS=1 in the
    # container.
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("BUILDER_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("BUILDER_MCP_PORT", "8000")),
        stateless_http=os.environ.get("BUILDER_MCP_STATELESS", "") == "1",
    )


if __name__ == "__main__":
    main()
