"""Pure text transforms on pipeline/pipeline.yml and the deployment repo shell.

These are string operations, not YAML round-trips, because pipeline.yml is full of
CloudFormation short tags (!Sub, !GetAtt) that yaml.safe_load cannot parse, and because a
round-trip would reformat the whole file and make the registration PR unreviewable. The
insertion anchor is the `Outputs:` block that follows the last stage; if pipeline.yml
grows a stage after BlueprintDeploy, revisit _insertion_point.

Kept pure (text in, text out) so they are trivially testable without GitHub.
"""

from __future__ import annotations

import json
import re

DEPLOYMENT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,28}[a-z0-9]$")


def pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[-_]", name) if part)


def render_pipeline_action(
    deployment_name: str,
    template_path: str,
    stack_name: str,
    parameter_overrides: dict[str, str],
) -> str:
    """One BlueprintDeploy action, indented to sit in pipeline.yml's Actions list."""
    action_name = f"{pascal_case(deployment_name)}CloudFormation"
    overrides_json = json.dumps(parameter_overrides, indent=0).replace("\n", "\n                  ")
    return f"""
            - Name: '{action_name}'
              Namespace: '{action_name}'
              RunOrder: 1
              InputArtifacts:
                - Name: 'GitRepositoryArtifact'
              ActionTypeId:
                Category: 'Deploy'
                Owner: 'AWS'
                Provider: 'CloudFormation'
                Version: '1'
              Configuration:
                ActionMode: 'CREATE_UPDATE'
                Capabilities: 'CAPABILITY_NAMED_IAM'
                RoleArn: !Sub 'arn:${{AWS::Partition}}:iam::${{AWS::AccountId}}:role/cloudformation-deploy-role'
                StackName: '{stack_name}'
                TemplatePath: 'GitRepositoryArtifact::{template_path}'
                ParameterOverrides: >-
                  {overrides_json}
"""


def _insertion_point(pipeline_text: str) -> int:
    """Index just before the Outputs: block that terminates the Stages list."""
    match = re.search(r"\n(Outputs:\n)", pipeline_text)
    if not match:
        raise ValueError("pipeline.yml has no Outputs: block to anchor the insertion on")
    return match.start()


def insert_blueprint_action(pipeline_text: str, action_block: str, stack_name: str) -> str:
    """Add a deploy action for a new stack to the BlueprintDeploy stage."""
    # Existing actions may write the stack name literally or as !Sub with the
    # ${Application}-${Environment} prefix, so the reliable duplicate signal is the
    # action name, which render_pipeline_action derives 1:1 from the deployment name.
    action_name_match = re.search(r"- Name: '(\w+CloudFormation)'", action_block)
    if action_name_match and f"'{action_name_match.group(1)}'" in pipeline_text:
        raise ValueError(f"stack {stack_name!r} already has a pipeline action")
    if f"'{stack_name}'" in pipeline_text:
        raise ValueError(f"stack {stack_name!r} already has a pipeline action")
    if "BlueprintDeploy" not in pipeline_text:
        raise ValueError("pipeline.yml has no BlueprintDeploy stage")
    point = _insertion_point(pipeline_text)
    return pipeline_text[:point] + action_block + pipeline_text[point:]


def remove_blueprint_action(pipeline_text: str, deployment_name: str) -> str:
    """Remove a deployment's deploy action from the BlueprintDeploy stage.

    The exact inverse of insert_blueprint_action: match from the action's
    `- Name: '<PascalCase(deployment)>CloudFormation'` line to the start of the next
    action at the same indent (or the `Outputs:` anchor for the last action), and cut
    that span only, so untouched text stays byte-identical and the deregistration PR
    diff is reviewable.
    """
    stage_match = re.search(r"- Name: 'BlueprintDeploy'", pipeline_text)
    if not stage_match:
        raise ValueError("pipeline.yml has no BlueprintDeploy stage")
    action_name = f"{pascal_case(deployment_name)}CloudFormation"
    start_match = re.search(
        rf"\n([ ]+)- Name: '{re.escape(action_name)}'", pipeline_text[stage_match.end():]
    )
    if not start_match:
        raise ValueError(
            f"deployment {deployment_name!r} has no {action_name!r} action in the "
            "BlueprintDeploy stage"
        )
    start = stage_match.end() + start_match.start()  # the newline before the action line
    indent = start_match.group(1)
    tail = pipeline_text[start + 1 :]  # skip past our own line before searching onward
    next_action = re.search(rf"\n{re.escape(indent)}- Name: '", tail)
    outputs = re.search(r"\nOutputs:\n", tail)
    if not outputs:
        raise ValueError("pipeline.yml has no Outputs: block to anchor the removal on")
    end = start + 1 + min(m.start() for m in (next_action, outputs) if m)
    return pipeline_text[:start] + pipeline_text[end:]


def deployment_repo_files(
    blueprint_name: str,
    blueprint_version: str,
    template_path: str,
    deployment_name: str,
    stack_name: str,
    owner_netid: str,
    parameters: dict[str, str],
    workshop_repo_full: str,
) -> dict[str, str]:
    """The thin shell a deployment repo starts with (proposal D1: reference, never copy).

    The repo holds the deployment's identity and parameters; the blueprint's code stays in
    the catalog and is referenced by pinned version. This is the builder's iteration home:
    deployment_update targets this repo, and its spec regenerates from deployment.yaml.
    """
    deployment_manifest = {
        "apiVersion": "builder.cornell.edu/v1",
        "kind": "Deployment",
        "metadata": {
            "name": deployment_name,
            "owner": owner_netid,
        },
        "blueprint": {
            "name": blueprint_name,
            "version": blueprint_version,          # pinned -- upgrades are dependency-bump PRs
            "source": f"{workshop_repo_full}//{template_path}",
        },
        "stack": stack_name,
        "parameters": parameters,
    }
    import yaml as _yaml

    readme = f"""# {deployment_name}

Deployment of the **{blueprint_name}** blueprint (v{blueprint_version}), owned by `{owner_netid}`.

This repo is a thin shell: `deployment.yaml` records which blueprint version this
deployment pins and the parameters it was created with. The blueprint's code lives in the
catalog ({workshop_repo_full}) and is *referenced*, never copied, so platform patches reach
this deployment as version-bump pull requests.

- Stack: `{stack_name}` (us-east-1)
- Deploys on merge to the tracked branch of {workshop_repo_full} -- merge is the only
  trigger; there is no deploy button.
- To change this deployment, open a pull request (your AI harness's `deployment_update`
  tool does this). Nobody -- human or agent -- has direct write access.
"""
    return {
        "deployment.yaml": _yaml.safe_dump(deployment_manifest, sort_keys=False),
        "README.md": readme,
    }
