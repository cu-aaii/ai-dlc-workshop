"""Render, locally, exactly what a `deployment_create` PR would send to CloudFormation.

`deployment_create` returns a *plan* -- a paragraph of prose. This renders the artifacts
that plan describes, into a gitignored folder, so you can read the template AWS receives,
the parameter values it receives with it, and the diff the registration PR would apply to
pipeline/pipeline.yml -- before anyone opens that PR.

It is **not part of the deploy path** and cannot deploy anything: no template registered in
pipeline/stacks.yml, no image target, no pipeline action, no AWS call, no GitHub call. It
only reads the checkout and writes under outputs-preview/ (gitignored).

Deliberately calls the server's own functions -- `render_pipeline_action`,
`deployment_repo_files`, `insert_blueprint_action`, `Blueprint.from_manifest`, `Settings` --
rather than reimplementing them. A preview that reimplemented the transforms would drift
from the server and start lying, which is worse than having no preview.

    cd packages/builder-mcp
    uv run python devtools/preview_deploy.py tiny-chatbot --owner ef436

Preflight findings are advisory, printed and written to PREFLIGHT.md. Exit status is 1 when
a BLOCKER is found (something that would fail PR checks or deploy wrong), so this is usable
in a script; WARN and NOTE do not affect it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# devtools/ is not a package and this file is run as a script, so the package under src/
# is not importable yet. Same reason console.py does its own path setup.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

import yaml  # noqa: E402

from builder_mcp.catalog import Blueprint, CatalogError, load_catalog  # noqa: E402
from builder_mcp.config import Settings  # noqa: E402
from builder_mcp.patching import (  # noqa: E402
    DEPLOYMENT_NAME_PATTERN,
    deployment_repo_files,
    insert_blueprint_action,
    pascal_case,
    render_pipeline_action,
)

PREVIEW_DIR = "outputs-preview"

# A CodePipeline action-namespace variable, e.g. #{TinyChatbotContainer.CONTAINER_DIGEST}.
# Resolved by the pipeline at run time, so its value is unknowable from a checkout -- but
# whether the namespace exists at all is not, and that is the check worth making.
PIPELINE_VAR = re.compile(r"#\{([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\}")


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that tolerates CloudFormation short tags.

    `yaml.safe_load` raises on `!Sub` / `!GetAtt` / `!Ref`, so reading a template's
    Parameters block needs the tags to resolve to *something*. Nothing here inspects
    resource bodies, so mapping every unknown tag to a placeholder is sufficient and keeps
    this from becoming a second CloudFormation parser.
    """


def _ignore_unknown(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> str:
    return f"<!{tag_suffix}>"


_CfnLoader.add_multi_constructor("!", _ignore_unknown)


class Finding:
    __slots__ = ("level", "title", "detail")

    def __init__(self, level: str, title: str, detail: str) -> None:
        self.level = level  # BLOCKER | WARN | NOTE
        self.title = title
        self.detail = detail


def preflight(
    blueprint: Blueprint,
    deployment_name: str,
    overrides: dict[str, str],
    template_params: dict[str, dict[str, Any]],
    pipeline_text: str,
    stacks_text: str,
) -> list[Finding]:
    """Everything checkable from a checkout that deployment_create does not check.

    These are the failure modes this repo has actually hit: a dangling pipeline variable, a
    parked blueprint, a declared input that never reaches the template. Each one produces a
    green plan and then either a red PR check or a wrong stack.
    """
    findings: list[Finding] = []

    # 1. Dangling pipeline variables. #{Ns.VAR} needs an action declaring Namespace: 'Ns'.
    #    Without it CodePipeline cannot resolve the reference and the pipeline update fails
    #    -- and the plan gives no hint, because the variable looks like a real value.
    for name, value in overrides.items():
        for match in PIPELINE_VAR.finditer(str(value)):
            namespace = match.group(1)
            if f"Namespace: '{namespace}'" not in pipeline_text:
                findings.append(
                    Finding(
                        "BLOCKER",
                        f"{name} references the undefined pipeline namespace {namespace!r}",
                        f"The value is {value!r}, but no action in pipeline/pipeline.yml "
                        f"declares Namespace: '{namespace}'. Nothing exports that variable, "
                        f"so the reference cannot resolve. Usually this means the component's "
                        f"Build stage action has not been wired yet -- see "
                        f"pipeline/README.md, 'Adding a container image'.",
                    )
                )

    # 2. stacks.yml registration vs. the action we are about to add. validate_stacks.py
    #    fails a `manual` entry that the pipeline deploys, so this is a red `validate`
    #    check and an unmergeable PR rather than a bad deploy.
    entry = re.search(
        rf"template: '{re.escape(blueprint.template)}'\s*\n\s*deployed_by: '(\w+)'",
        stacks_text,
    )
    if entry is None:
        findings.append(
            Finding(
                "BLOCKER",
                f"{blueprint.template} is not registered in pipeline/stacks.yml",
                "validate_stacks.py fails on an unregistered template, so the PR cannot "
                "merge. Add the entry in the same PR as the template.",
            )
        )
    elif entry.group(1) == "manual":
        findings.append(
            Finding(
                "BLOCKER",
                f"{blueprint.name} is registered deployed_by: 'manual' but this PR adds a "
                f"pipeline action",
                "validate_stacks.py rejects that combination (a manual entry the pipeline "
                "deploys), so the `validate` check fails and branch protection blocks the "
                "merge. Flip the entry to deployed_by: 'pipeline' in the same PR -- which "
                "deployment_create does not do.",
            )
        )

    # 3. Overrides for parameters the template does not declare -- CloudFormation rejects
    #    the whole stack operation on an unknown parameter key.
    for name in overrides:
        if name not in template_params:
            findings.append(
                Finding(
                    "BLOCKER",
                    f"override {name!r} is not a parameter of the template",
                    f"{blueprint.template} declares "
                    f"{sorted(template_params) or '(none)'}. CloudFormation fails the stack "
                    f"operation on an unrecognised parameter.",
                )
            )

    # 4. Declared blueprint inputs that never reach the template. The input is collected
    #    from the builder, validated, recorded in deployment.yaml -- and then dropped,
    #    because overrides is Application/Environment/Owner + pipeline_parameters only.
    #    The stack name honours it; the resources inside do not.
    for input_name in blueprint.inputs:
        if input_name == "owner_netid":
            continue  # arrives as the Owner override
        candidate = pascal_case(input_name)
        if candidate in template_params and candidate not in overrides:
            declared_default = template_params[candidate].get("Default")
            # Common half: the input is advertised, collected, validated, written to
            # deployment.yaml -- and then dropped, because overrides is
            # Application/Environment/Owner + pipeline_parameters and nothing else.
            common = (
                f"The template declares {candidate} (default {declared_default!r}) and the "
                f"manifest advertises {input_name!r} as an input, but deployment_create's "
                f"overrides are Application/Environment/Owner plus pipeline_parameters -- so "
                f"{candidate} silently keeps its default. Whatever the builder supplies is "
                f"recorded in deployment.yaml and has no effect on the stack. CLAUDE.md: "
                f"'Pass every parameter explicitly from the pipeline.'"
            )
            # The severity split is about consequence, not about whether it is a bug. For a
            # non-singleton the dropped parameter is also the one that makes resource names
            # unique, so a second deployment collides with the first; for a singleton there
            # is no second deployment and the damage stops at the ignored input.
            if blueprint.singleton:
                findings.append(
                    Finding(
                        "WARN",
                        f"input {input_name!r} is collected but never reaches the template",
                        common
                        + f" This blueprint is a singleton, so nothing collides -- but a "
                        f"builder who sets {input_name!r} gets no error and no effect.",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "BLOCKER",
                        f"input {input_name!r} is collected but never reaches the template",
                        common
                        + f" This blueprint is not a singleton, so {candidate} is also what "
                        f"makes resource names unique: the stack name uses the deployment "
                        f"name, the resources inside keep the default. A second deployment "
                        f"collides with the first on resource names.",
                    )
                )

    # 5. Parameters with neither an override nor a default: CloudFormation prompts, and a
    #    non-interactive pipeline deploy fails outright.
    for name, spec in template_params.items():
        if name not in overrides and "Default" not in spec:
            findings.append(
                Finding(
                    "BLOCKER",
                    f"parameter {name!r} has no override and no default",
                    "The pipeline deploy is non-interactive, so CloudFormation fails rather "
                    "than prompting.",
                )
            )

    # 6. AllowedPattern violations we can check now rather than at deploy time.
    for name, value in overrides.items():
        spec = template_params.get(name)
        if not spec:
            continue
        pattern = spec.get("AllowedPattern")
        if pattern and not PIPELINE_VAR.search(str(value)):
            if not re.fullmatch(pattern, str(value)):
                findings.append(
                    Finding(
                        "BLOCKER",
                        f"{name}={value!r} violates its AllowedPattern",
                        f"The template requires {pattern!r}. CloudFormation rejects the "
                        f"parameter before creating anything.",
                    )
                )

    # 7. Already registered. insert_blueprint_action refuses, so deployment_create would
    #    error rather than open a PR -- meaning this preview describes a create that cannot
    #    happen. Worth saying out loud: without it the aws/ artifacts read as a pending
    #    deploy when they are really a description of a live one.
    action_name = f"{pascal_case(deployment_name)}CloudFormation"
    if f"'{action_name}'" in pipeline_text:
        findings.append(
            Finding(
                "NOTE",
                f"{deployment_name!r} already has a {action_name!r} action in pipeline.yml",
                "deployment_create would refuse this as a duplicate, so there is no PR to "
                "preview. The aws/ artifacts still show what that existing action deploys -- "
                "but compare them against the action in pipeline/pipeline.yml, which was "
                "written by hand and may pass parameters this tool's generated action does "
                "not. Use deployment_update to change a live deployment.",
            )
        )

    if blueprint.maturity != "supported":
        findings.append(
            Finding(
                "NOTE",
                f"blueprint maturity is {blueprint.maturity!r}",
                "Not a defect -- just not a blueprint the platform team has committed to.",
            )
        )
    return findings


def check_action_placement(patched: str, action_name: str) -> Finding | None:
    """Assert the inserted action actually landed inside the BlueprintDeploy stage.

    `_insertion_point` anchors on the `Outputs:` block after the *last* stage, which is the
    BlueprintDeploy stage only while BlueprintDeploy is last. patching.py's module docstring
    flags this ("if pipeline.yml grows a stage after BlueprintDeploy, revisit
    _insertion_point"), and test_patching.py asserts only that the action lands somewhere
    between the previous action and `Outputs:` -- a window that includes every later stage.
    So this is checked here against the real file, by stage bounds rather than by ordering.
    """
    stage = re.search(r"\n        - Name: 'BlueprintDeploy'", patched)
    if stage is None:
        return Finding("BLOCKER", "pipeline.yml has no BlueprintDeploy stage", "")
    # The stage ends at the next stage header at the same indent, or at Outputs:.
    tail = patched[stage.end() :]
    next_stage = re.search(r"\n        - Name: '", tail)
    outputs = re.search(r"\nOutputs:\n", tail)
    ends = [m.start() for m in (next_stage, outputs) if m]
    stage_end = stage.end() + min(ends) if ends else len(patched)
    where = patched.find(f"- Name: '{action_name}'")
    if where == -1 or stage.end() < where < stage_end:
        return None
    # Name the stage it actually landed in, so the report is actionable rather than a
    # bare "wrong place".
    landed_in = "after every stage"
    for match in re.finditer(r"\n        - Name: '(\w+)'", patched):
        if match.start() < where:
            landed_in = f"the {match.group(1)!r} stage"
    return Finding(
        "BLOCKER",
        f"the generated action lands in {landed_in}, not BlueprintDeploy",
        "patching._insertion_point anchors on the 'Outputs:' block after the last stage, "
        "which was BlueprintDeploy when it was written. pipeline.yml has since grown a "
        "stage after it, so every action deployment_create generates is now appended to "
        "that later stage instead -- while the plan it returns still says 'BlueprintDeploy'. "
        "CodePipeline permits mixed action types in a stage, so this misplaces the deploy "
        "silently rather than failing. Anchor the insertion on the end of the "
        "BlueprintDeploy stage instead. Note test_patching.py's "
        "test_insert_places_action_inside_blueprint_deploy_stage asserts only that the "
        "action sits before 'Outputs:', so it cannot catch this.",
    )


def _read(path: Path, what: str) -> str:
    if not path.is_file():
        sys.exit(f"error: cannot read {what}: {path} does not exist")
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render what a deployment_create PR would deploy, into "
        f"{PREVIEW_DIR}/ (gitignored). Deploys nothing; touches no network.",
    )
    parser.add_argument("blueprint", help="blueprint name, e.g. tiny-chatbot")
    parser.add_argument("--owner", required=True, help="owner NetID (cornell:owner)")
    parser.add_argument(
        "--name",
        help="deployment name (default: the blueprint name; forced to it for singletons)",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="extra blueprint input, repeatable",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if settings.repo_root is None:
        sys.exit(
            "error: no workshop checkout found (looked for pipeline/stacks.yml in this "
            "file's parents). Set BUILDER_MCP_REPO_ROOT."
        )
    root = settings.repo_root

    try:
        catalog = load_catalog(settings)
    except CatalogError as exc:
        sys.exit(f"error: {exc}")
    found = next((b for b in catalog if b.name == args.blueprint), None)
    if found is None:
        sys.exit(
            f"error: no blueprint named {args.blueprint!r}. Available: "
            f"{', '.join(sorted(b.name for b in catalog))}"
        )

    # Mirror deployment_create's own precedence exactly (server.py): singletons take the
    # blueprint name, everything else validates against DEPLOYMENT_NAME_PATTERN.
    deployment_name = args.name or found.name
    if found.singleton:
        deployment_name = found.name
    elif not DEPLOYMENT_NAME_PATTERN.match(deployment_name):
        sys.exit(
            f"error: deployment_name {deployment_name!r} must match "
            f"{DEPLOYMENT_NAME_PATTERN.pattern}"
        )

    parameters: dict[str, str] = {"owner_netid": args.owner}
    for pair in args.set:
        if "=" not in pair:
            sys.exit(f"error: --set expects KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        parameters[key] = value

    stack_name = settings.stack_name(deployment_name)
    # Identical construction to server.deployment_create -- if that changes, this must too,
    # and the mismatch is the point: a preview that guesses is worthless.
    overrides = {
        "Application": settings.application,
        "Environment": settings.environment,
        "Owner": args.owner,
        **found.pipeline_parameters,
    }

    template_path = root / found.template
    template_text = _read(template_path, "blueprint template")
    template_doc = yaml.load(template_text, Loader=_CfnLoader) or {}
    template_params: dict[str, dict[str, Any]] = template_doc.get("Parameters") or {}

    pipeline_path = root / "pipeline" / "pipeline.yml"
    pipeline_text = _read(pipeline_path, "pipeline/pipeline.yml")
    stacks_text = _read(root / "pipeline" / "stacks.yml", "pipeline/stacks.yml")

    action_block = render_pipeline_action(
        deployment_name, found.template, stack_name, overrides
    )
    patched: str | None = None
    try:
        patched = insert_blueprint_action(pipeline_text, action_block, stack_name)
        pipeline_diff = "".join(
            difflib.unified_diff(
                pipeline_text.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile="a/pipeline/pipeline.yml",
                tofile="b/pipeline/pipeline.yml",
                n=3,
            )
        )
    except ValueError as exc:
        pipeline_diff = f"# no diff: {exc}\n"

    shell_files = deployment_repo_files(
        found.name,
        found.version,
        found.template,
        deployment_name,
        stack_name,
        args.owner,
        parameters,
        settings.workshop_repo_full,
        shell_location="folder" if settings.deployment_mode == "folder" else "repo",
    )

    findings = preflight(
        found, deployment_name, overrides, template_params, pipeline_text, stacks_text
    )
    if patched is not None:
        placement = check_action_placement(
            patched, f"{pascal_case(deployment_name)}CloudFormation"
        )
        if placement is not None:
            findings.insert(0, placement)

    # ---- write the preview -------------------------------------------------------------
    out = root / PREVIEW_DIR / deployment_name
    if out.exists():
        shutil.rmtree(out)  # regenerate wholesale; a stale mixed folder is a trap
    (out / "aws").mkdir(parents=True)
    (out / "pipeline").mkdir()
    (out / "shell").mkdir()

    # The template is what CloudFormation receives, byte for byte. There is no render step:
    # a CFN template is passed verbatim alongside its parameter values.
    (out / "aws" / "template.yml").write_text(template_text, encoding="utf-8", newline="")

    runtime_resolved = {
        k: v for k, v in overrides.items() if PIPELINE_VAR.search(str(v))
    }
    resolved = {k: v for k, v in overrides.items() if k not in runtime_resolved}
    defaults_used = {
        name: spec.get("Default")
        for name, spec in template_params.items()
        if name not in overrides
    }
    (out / "aws" / "parameters.json").write_text(
        json.dumps(
            {
                "stack": stack_name,
                "region": settings.aws_region,
                "template": "aws/template.yml",
                "capabilities": ["CAPABILITY_NAMED_IAM"],
                "resolved": resolved,
                "runtime_resolved": runtime_resolved,
                "template_defaults_used": defaults_used,
                "cli_parameter_overrides": [
                    f"{k}={v}" for k, v in sorted(resolved.items())
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )

    (out / "pipeline" / "action.yml").write_text(action_block, encoding="utf-8", newline="")
    (out / "pipeline" / "pipeline.yml.diff").write_text(
        pipeline_diff, encoding="utf-8", newline=""
    )
    for name, content in shell_files.items():
        (out / "shell" / name).write_text(content, encoding="utf-8", newline="")

    blockers = [f for f in findings if f.level == "BLOCKER"]
    lines = [
        f"# Preflight — {deployment_name}",
        "",
        f"Blueprint `{found.name}` v{found.version} ({found.maturity}) → stack "
        f"`{stack_name}` in {settings.aws_region}.",
        "",
        f"**{len(blockers)} blocker(s), {len(findings) - len(blockers)} advisory.**"
        if findings
        else "**No findings.**",
        "",
        "Generated by `devtools/preview_deploy.py` from the checkout. Advisory: it checks "
        "what a checkout can prove, not what only AWS can.",
        "",
    ]
    for level in ("BLOCKER", "WARN", "NOTE"):
        group = [f for f in findings if f.level == level]
        if not group:
            continue
        lines += [f"## {level}", ""]
        for finding in group:
            lines += [f"- **{finding.title}**", f"  {finding.detail}", ""]
    (out / "PREFLIGHT.md").write_text("\n".join(lines), encoding="utf-8", newline="")

    (out / "README.md").write_text(
        f"""# {deployment_name} — deploy preview (generated, gitignored)

What a `deployment_create` PR for **{found.name}** v{found.version} would result in. Nothing
here is deployed, and nothing here is committed: `{PREVIEW_DIR}/` is gitignored.

Regenerate (from `packages/builder-mcp/`):

    uv run python devtools/preview_deploy.py {found.name} --owner {args.owner}\
{"" if found.singleton else f" --name {deployment_name}"}

| Path | What it is |
|---|---|
| `aws/template.yml` | The template CloudFormation receives, byte-identical to `{found.template}`. Copied, not rendered — a CFN template is passed verbatim with its parameter values. |
| `aws/parameters.json` | The values it receives with it: `resolved` (known now), `runtime_resolved` (CodePipeline `#{{...}}` variables, known only at run time), `template_defaults_used` (declared but never overridden). |
| `pipeline/action.yml` | The exact `BlueprintDeploy` action the PR appends to `pipeline/pipeline.yml`. |
| `pipeline/pipeline.yml.diff` | That insertion as a unified diff — the reviewable half of the PR. |
| `shell/` | The two files the Builder writes to `outputs/{deployment_name}/`. A record of intent; **nothing reads them at deploy time.** |
| `PREFLIGHT.md` | What would go wrong, and why. |

## What actually deploys

`shell/` does not. The deploy is driven entirely by `pipeline/action.yml` landing in
`pipeline/pipeline.yml`: on merge, `PipelineDeploy` re-deploys the pipeline with that action
present, then `BlueprintDeploy` runs it against `{found.template}`. Delete the shell and the
stack still deploys identically.
""",
        encoding="utf-8",
        newline="",
    )

    rel = f"{PREVIEW_DIR}/{deployment_name}"
    print(f"wrote {rel}/")
    print(f"  aws/template.yml         {len(template_text.splitlines())} lines (verbatim)")
    print(f"  aws/parameters.json      {len(resolved)} resolved, {len(runtime_resolved)} at run time")
    print(f"  pipeline/action.yml      stack {stack_name}")
    print(f"  shell/                   {len(shell_files)} files (deploy reads none of them)")
    print()
    if not findings:
        print("preflight: no findings")
        return 0
    for finding in findings:
        print(f"  [{finding.level}] {finding.title}")
    print()
    print(f"see {rel}/PREFLIGHT.md")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
