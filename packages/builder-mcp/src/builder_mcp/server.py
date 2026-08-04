"""Cornell Builder MCP server.

Eight tools that turn plain-language intent into governed deployments through the
existing deploy path. Tool names follow noun_verb (blueprint_search, deployment_create,
spec_export, ...). Design constraints this code is downstream of:

- Merge, and nothing else, deploys (D4). No tool here can deploy, merge, push to a
  tracked branch, or destroy. deployment_create opens a PR; a human approves it; the
  pipeline does the rest. deployment_delete is symmetric: a deregistration PR, never an
  AWS delete call.
- The builder's client holds no credentials (D3). GitHub and AWS calls run server-side.
- Stateless transport. Bedrock AgentCore runs streamable HTTP with no session affinity,
  which also rules out MCP elicitation (no back-channel). The confirm-before-doing UX is
  the dry_run pattern instead: mutating tools default to dry_run=true and return the full
  plan; the client re-calls with dry_run=false to execute.
"""

from __future__ import annotations

import functools
import logging
import os
import uuid
from typing import Any, Callable

try:  # SDK renamed FastMCP -> MCPServer; support both so the pinned version can float
    from mcp.server.mcpserver import MCPServer as _ServerClass
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _ServerClass

from . import aws_ops
from .catalog import CatalogError, load_catalog, search, validate_inputs
from .config import Settings
from .github_ops import GitHubOps
from .patching import (
    DEPLOYMENT_NAME_PATTERN,
    deployment_repo_files,
    insert_blueprint_action,
    pascal_case,
    remove_blueprint_action,
    render_pipeline_action,
)
from .spec_export import render_spec
from .validation import (
    files_problem,
    owner_netid_problem,
    safe_error,
    title_description_problem,
)

logger = logging.getLogger(__name__)

settings = Settings.from_env()


def _guarded(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap a tool so it never raises to the transport (C3 error contract / NFR7) and
    logs exactly one structured line per call (SECURITY-03).

    Any exception becomes a redacted {"error": ...} narrative (SECURITY-09); CatalogError
    messages are crafted caller-safe and pass through verbatim.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        subject = (
            kwargs.get("deployment_name")
            or kwargs.get("blueprint")
            or kwargs.get("repo")
            or kwargs.get("query")
            or (args[0] if args else "")
        )
        error_class: str | None = None
        try:
            result = func(*args, **kwargs)
        except CatalogError as error:
            result = {"error": str(error)}
            error_class = error.__class__.__name__
        except Exception as error:  # the transport must only ever see a narrative
            logger.debug("tool %s raised", func.__name__, exc_info=True)
            result = safe_error(error, f"running {func.__name__}")
            error_class = error.__class__.__name__
        if error_class is None and isinstance(result, dict) and "error" in result:
            error_class = "handled"
        logger.info(
            "tool=%s subject=%s dry_run=%s outcome=%s",
            func.__name__,
            str(subject)[:80],
            kwargs.get("dry_run", "n/a"),
            f"error:{error_class}" if error_class else "ok",
        )
        return result

    return wrapper

mcp = _ServerClass(
    "cornell-builder",
    instructions=(
        "The Cornell Builder: search governed infrastructure blueprints "
        "(blueprint_search), create deployments of them (deployment_create), and "
        "operate what you deployed (deployment_read, deployment_update, "
        "deployment_health, deployment_restart, deployment_delete, spec_export). "
        "Deployments go live — and are torn down — only when a human approves the pull "
        "request this server opens; there is no deploy or delete button, by design. "
        "Mutating tools default to dry_run=true; show the user the plan and get their "
        "confirmation before re-calling with dry_run=false — unless a tool's own "
        "description says otherwise."
    ),
)


def _blueprint_or_error(name: str):
    catalog = load_catalog(settings)
    for blueprint in catalog:
        if blueprint.name == name:
            return blueprint
    return {"error": f"no blueprint named {name!r}; catalog has {[b.name for b in catalog]}"}


@mcp.tool()
@_guarded
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
@_guarded
def deployment_create(
    blueprint: str,
    deployment_name: str,
    owner_netid: str,
    parameters: dict[str, str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a deployment of a blueprint: a deployment shell plus a registration pull
    request that makes the pipeline deploy the stack on merge.

    Where the shell lands depends on the server's deployment mode (SPEC C2): in 'folder'
    mode (testing-phase default) it is written to outputs/<deployment_name>/ in the
    workshop repo on the same branch as the registration PR — one PR carries both; in
    'repo' mode (target state) a new deploy-<name> repo is created in the Cornell org.

    Let the requestor choose whether to preview, rather than deciding for them. Ask which
    they want: dry_run=true renders the plan (shell location, PR to be opened, stack name,
    parameters, estimated cost) and opens nothing; dry_run=false opens the registration PR
    straight away. Default to offering the preview for a first deployment or an unfamiliar
    blueprint, and take "just open it" at face value when they say so.

    Neither choice deploys anything. Nothing reaches AWS until a human approves and merges
    the PR — merge is the only deploy trigger — so the question is whether they want to read
    the plan first, not whether something goes live.
    """
    netid_problem = owner_netid_problem(owner_netid)
    if netid_problem:
        return {"error": netid_problem}
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
    folder_mode = settings.deployment_mode == "folder"
    repo_name = f"deploy-{deployment_name}"
    shell_files = deployment_repo_files(
        found.name, found.version, found.template, deployment_name,
        stack_name, owner_netid, parameters, settings.workshop_repo_full,
        shell_location="folder" if folder_mode else "repo",
    )
    if folder_mode:
        # The folder is always derived server-side: 'outputs/' + the already-validated
        # deployment_name (DEPLOYMENT_NAME_PATTERN forbids '/', '.', and '..') + '/' +
        # a fixed basename from deployment_repo_files — never a caller-supplied path.
        shell_files = {
            f"outputs/{deployment_name}/{path}": content
            for path, content in shell_files.items()
        }

    plan = {
        "blueprint": f"{found.name} v{found.version} ({found.maturity})",
        "stack": stack_name,
        "estimated_cost": found.cost,
        "registration_pr": {
            "repo": settings.workshop_repo_full,
            "edits": (
                "pipeline/pipeline.yml — one new BlueprintDeploy action; "
                f"outputs/{deployment_name}/ — the deployment shell (same PR)"
                if folder_mode
                else "pipeline/pipeline.yml — one new BlueprintDeploy action"
            ),
            "parameter_overrides": overrides,
        },
        "governance": "Deploys only when a human approves and merges the registration PR.",
    }
    if folder_mode:
        plan["shell_folder"] = (
            f"outputs/{deployment_name}/ (in {settings.workshop_repo_full}, same PR)"
        )
    else:
        plan["new_repo"] = f"{settings.github_org}/{repo_name}"
    # F1 denylist: every path this tool writes is validated, even the server-generated
    # shell files — no write can ever land under .github/ or outside the repo.
    files_issue = files_problem(shell_files)
    if files_issue:
        return {"error": files_issue}

    if dry_run:
        return {"dry_run": True, "plan": plan}

    results: dict[str, Any] = {"plan": plan}
    completed_steps: list[str] = []
    branch = f"deploy/{deployment_name}"
    try:
        with GitHubOps(settings) as github:
            if not folder_mode:
                # Target-state path (D1/D5): a dedicated deploy-<name> repo. Stashed
                # behind BUILDER_MCP_DEPLOYMENT_MODE=repo while the testing-phase
                # credential cannot create org repos; reactivate by setting the env var.
                results["repo"] = github.create_org_repo(
                    repo_name, f"{found.name} v{found.version} deployment owned by {owner_netid}"
                )
                completed_steps.append(f"created repo {settings.github_org}/{repo_name}")
                for path, content in shell_files.items():
                    github.put_file(
                        f"{settings.github_org}/{repo_name}", path, content,
                        f"Initialize {deployment_name} shell", "main",
                    )
                completed_steps.append("initialized deployment repo shell files")
            github.create_branch(settings.workshop_repo_full, branch)
            completed_steps.append(f"created branch {branch} on {settings.workshop_repo_full}")
            if folder_mode:
                # Folder mode: the shell rides the same branch as the pipeline edit, so
                # the registration PR carries both (one PR, no repo creation).
                for path, content in shell_files.items():
                    github.put_file(
                        settings.workshop_repo_full, path, content,
                        f"Initialize {deployment_name} shell", branch,
                    )
                completed_steps.append(
                    f"wrote the deployment shell under outputs/{deployment_name}/"
                )
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
                completed_steps.append("registered the deploy action on pipeline/pipeline.yml")
            shell_line = (
                f"- Deployment shell: `outputs/{deployment_name}/` (in this PR)"
                if folder_mode
                else f"- Deployment repo: {settings.github_org}/{repo_name}"
            )
            results["pull_request"] = github.create_pull(
                settings.workshop_repo_full,
                branch,
                # Prefixed so a reviewer scanning the PR list can tell a Builder-generated
                # PR from one a developer opened by hand -- these arrive from a builder
                # talking to a chatbot, not from someone who has read pipeline.yml.
                f"(blueprint create)/{found.name}: {stack_name} for {owner_netid} "
                f"(v{found.version})",
                f"Registration PR opened by the Cornell Builder.\n\n"
                f"- Blueprint: `{found.name}` v{found.version}\n- Stack: `{stack_name}`\n"
                f"- Owner: `{owner_netid}`\n{shell_line}\n\n"
                "Merging this PR is the deploy action. Review the pipeline action diff carefully.",
            )
            completed_steps.append("opened the registration PR")
    except Exception as error:
        # SECURITY-15: the multi-step sequence is not atomic — report exactly how far
        # it got and what may need cleanup, instead of raising mid-way.
        cleanup = (
            f"Partial state may remain: branch {branch!r} on "
            f"{settings.workshop_repo_full} can be deleted safely and the create retried."
            if folder_mode
            else (
                f"Partial state may remain: check for repo "
                f"{settings.github_org}/{repo_name} and branch {branch!r} on "
                f"{settings.workshop_repo_full}; delete whichever exists before "
                "retrying, or ask the platform team."
            )
        )
        return {
            **safe_error(error, f"creating deployment {deployment_name!r}"),
            "completed_steps": completed_steps,
            "cleanup": cleanup,
        }
    return results


@mcp.tool()
@_guarded
def deployment_read(deployment_name: str) -> dict[str, Any]:
    """Full-chain status of a deployment: registration PR, pipeline stages, and
    CloudFormation stack state."""
    stack_name = settings.stack_name(deployment_name)
    with GitHubOps(settings) as github:
        try:
            prs = github.open_prs(
                settings.workshop_repo_full, head_contains=f"deploy/{deployment_name}"
            )
        except Exception as error:  # GitHub unreachable should not hide AWS state
            prs = [safe_error(error, "listing registration PRs")]
    return {
        "deployment": deployment_name,
        "open_registration_prs": prs,
        "pipeline": aws_ops.pipeline_state(settings),
        "stack": aws_ops.stack_status(settings, stack_name),
    }


@mcp.tool()
@_guarded
def deployment_update(
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
    # F1: the server's credential only ever writes to the workshop repo or a deploy-*
    # deployment repo — never an arbitrary org/name the caller typed.
    if repo_full != settings.workshop_repo_full and not repo_full.startswith(
        f"{settings.github_org}/deploy-"
    ):
        return {
            "error": (
                f"repo {repo_full!r} is outside this server's write scope: only "
                f"{settings.workshop_repo_full} and {settings.github_org}/deploy-* "
                "deployment repos can be targeted"
            )
        }
    issue = title_description_problem(title, description) or files_problem(files)
    if issue:
        return {"error": issue}
    # Folder mode (testing phase): deployments have no deploy-* repo — their shell lives
    # at outputs/<name>/ in the workshop repo, so a deploy-* target is a mistake worth
    # explaining rather than a repo that will 404.
    if settings.deployment_mode == "folder" and repo_full.startswith(
        f"{settings.github_org}/deploy-"
    ):
        shell_name = repo_full.removeprefix(f"{settings.github_org}/deploy-")
        return {
            "error": (
                f"this server runs in 'folder' deployment mode: {repo_full!r} does not "
                f"exist as a repo. The deployment's shell lives in "
                f"{settings.workshop_repo_full} under outputs/{shell_name}/ — call "
                f"deployment_update again with repo={settings.workshop_repo!r} and file "
                f"paths prefixed outputs/{shell_name}/"
            )
        }
    # uuid4, not hash(): hash() is randomized per process (PYTHONHASHSEED), so the
    # branch would differ between the dry-run plan and a post-restart execute.
    branch = f"propose/{uuid.uuid4().hex[:8]}"
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
    completed_steps: list[str] = []
    written = []
    try:
        with GitHubOps(settings) as github:
            github.create_branch(repo_full, branch)
            completed_steps.append(f"created branch {branch} on {repo_full}")
            for path, content in files.items():
                sha = None
                if github.can_write:
                    try:
                        _, sha = github.get_file(repo_full, path, ref=branch)
                    except Exception:
                        sha = None  # new file
                written.append(
                    github.put_file(repo_full, path, content, f"{title}: {path}", branch, sha=sha)
                )
                completed_steps.append(f"wrote {path}")
            # Same reviewer signal as create/delete. The caller-supplied title is kept
            # verbatim after the prefix; it was already bounded by title_description_problem.
            pr = github.create_pull(
                repo_full, branch, f"(blueprint update): {title}", description
            )
            completed_steps.append("opened the PR")
    except Exception as error:
        return {
            **safe_error(error, f"proposing change {title!r}"),
            "completed_steps": completed_steps,
            "cleanup": (
                f"Partial state may remain: branch {branch!r} on {repo_full} can be "
                "deleted safely and the change retried."
            ),
        }
    return {"files": written, "pull_request": pr}


@mcp.tool()
@_guarded
def deployment_health(deployment_name: str) -> dict[str, Any]:
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
@_guarded
def deployment_restart(deployment_name: str, dry_run: bool = True) -> dict[str, Any]:
    """Re-run the deployment at its current version: retries the failed pipeline stage if
    one exists, otherwise starts a fresh pipeline execution. Cannot change what is
    deployed — changes require a PR. Call with dry_run=true first."""
    # deployment_name is accepted for symmetry and future per-deployment pipelines; today
    # all blueprint stacks deploy through the one shared pipeline.
    return {"deployment": deployment_name, **aws_ops.restart(settings, dry_run=dry_run)}


@mcp.tool()
@_guarded
def deployment_delete(deployment_name: str, dry_run: bool = True) -> dict[str, Any]:
    """Delete a deployment the governed way: a deregistration pull request that removes
    its action from the pipeline, symmetric with deployment_create's registration PR.
    In 'folder' deployment mode the same PR also removes the outputs/<name>/ shell
    folder, mirroring what deployment_create wrote.

    This tool never calls an AWS delete API. After a human approves and merges the PR,
    the platform removes the stack itself according to its DeletionPolicy — merge is the
    only trigger, for teardown exactly as for deploys. Always call with dry_run=true
    first and show the user the plan for confirmation.
    """
    if not DEPLOYMENT_NAME_PATTERN.match(deployment_name):
        return {
            "error": f"deployment_name {deployment_name!r} must match "
            f"{DEPLOYMENT_NAME_PATTERN.pattern}"
        }
    stack_name = settings.stack_name(deployment_name)
    action_name = f"{pascal_case(deployment_name)}CloudFormation"
    branch = f"undeploy/{deployment_name}"
    folder_mode = settings.deployment_mode == "folder"
    plan = {
        "deployment": deployment_name,
        "stack": stack_name,
        "deregistration_pr": {
            "repo": settings.workshop_repo_full,
            "branch": branch,
            "edits": (
                f"pipeline/pipeline.yml — remove the {action_name} BlueprintDeploy "
                f"action; outputs/{deployment_name}/ — remove the deployment shell "
                "folder (same PR)"
                if folder_mode
                else f"pipeline/pipeline.yml — remove the {action_name} BlueprintDeploy action"
            ),
        },
        "warning": (
            "The stack itself is deleted by the platform after the PR merges, per its "
            "DeletionPolicy — this tool only removes the deployment's registration."
        ),
        "governance": "Tears down only when a human approves and merges the deregistration PR.",
    }
    if dry_run:
        return {"dry_run": True, "plan": plan}

    results: dict[str, Any] = {"plan": plan}
    completed_steps: list[str] = []
    try:
        with GitHubOps(settings) as github:
            results["branch"] = github.create_branch(settings.workshop_repo_full, branch)
            completed_steps.append(f"created branch {branch}")
            if github.can_write:
                pipeline_text, sha = github.get_file(
                    settings.workshop_repo_full, "pipeline/pipeline.yml", ref=branch
                )
                try:
                    patched = remove_blueprint_action(pipeline_text, deployment_name)
                except ValueError as error:
                    return {"error": str(error)}
                github.put_file(
                    settings.workshop_repo_full, "pipeline/pipeline.yml", patched,
                    f"Deregister {stack_name}", branch, sha=sha,
                )
                completed_steps.append("removed the deploy action on the branch")
                if folder_mode:
                    # Symmetric teardown: the same PR that deregisters the pipeline
                    # action also removes the outputs/<name>/ shell folder. The path is
                    # server-derived from the validated deployment_name, never caller
                    # input; list_dir returns [] when the folder does not exist.
                    for path, blob_sha in github.list_dir(
                        settings.workshop_repo_full, f"outputs/{deployment_name}", ref=branch
                    ):
                        github.delete_file(
                            settings.workshop_repo_full, path,
                            f"Remove outputs/{deployment_name}/ shell (undeploy {stack_name})",
                            branch, sha=blob_sha,
                        )
                    completed_steps.append(
                        f"removed the outputs/{deployment_name}/ shell folder on the branch"
                    )
            removes_line = (
                f"- Removes: the `{action_name}` action from the BlueprintDeploy stage "
                f"and the `outputs/{deployment_name}/` deployment shell"
                if folder_mode
                else f"- Removes: the `{action_name}` action from the BlueprintDeploy stage"
            )
            results["pull_request"] = github.create_pull(
                settings.workshop_repo_full,
                branch,
                f"(blueprint delete)/{deployment_name}: undeploy {stack_name}",
                f"Deregistration PR opened by the Cornell Builder.\n\n"
                f"- Deployment: `{deployment_name}`\n- Stack: `{stack_name}`\n"
                f"{removes_line}\n\n"
                "Merging this PR is the teardown action: the platform deletes the stack per its "
                "DeletionPolicy. If this was the blueprint's *last* deployment, its "
                "`pipeline/stacks.yml` entry should be removed in a follow-up PR.",
            )
            completed_steps.append("opened the deregistration PR")
    except Exception as error:
        return {
            **safe_error(error, f"deleting deployment {deployment_name!r}"),
            "completed_steps": completed_steps,
            "cleanup": (
                f"Partial state may remain: branch {branch!r} on "
                f"{settings.workshop_repo_full} can be deleted safely and the delete "
                "retried."
            ),
        }
    return results


@mcp.tool()
@_guarded
def spec_export(deployment_name: str, blueprint: str, audience: str = "coder") -> dict[str, Any]:
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
        markdown = render_spec(audience, spec)
    except ValueError as error:
        return {"error": str(error)}
    return {"audience": audience, "spec_markdown": markdown}


def main() -> None:
    # SECURITY-03: logging is configured here and only here — importing the package
    # never touches global logging state. Stdout is where AgentCore forwards logs from.
    logging.basicConfig(
        level=os.environ.get("BUILDER_MCP_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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
