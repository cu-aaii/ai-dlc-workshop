import json
import re

import pytest

from builder_mcp.config import find_repo_root
from builder_mcp.patching import (
    deployment_repo_files,
    insert_blueprint_action,
    pascal_case,
    remove_blueprint_action,
    render_pipeline_action,
)

PIPELINE_YML = (find_repo_root() / "pipeline" / "pipeline.yml").read_text(encoding="utf-8")


def _action(name="team-x-hello"):
    return render_pipeline_action(
        deployment_name=name,
        template_path="blueprints/hello-world/infra/hello-world.yml",
        stack_name=f"aidlc-main-{name}",
        parameter_overrides={
            "Application": "aidlc",
            "Environment": "main",
            "Owner": "tmf77",
            "SourceCommitId": "#{GitRepository.CommitId}",
        },
    )


def test_pascal_case():
    assert pascal_case("team-x-hello") == "TeamXHello"


def test_insert_places_action_inside_blueprint_deploy_stage():
    patched = insert_blueprint_action(PIPELINE_YML, _action(), "aidlc-main-team-x-hello")
    assert "TeamXHelloCloudFormation" in patched
    # the action lands after the existing hello-world action and before Outputs
    assert (
        patched.index("HelloWorldCloudFormation")
        < patched.index("TeamXHelloCloudFormation")
        < patched.index("\nOutputs:")
    )
    # untouched text is byte-identical outside the insertion (reviewable diff)
    assert patched.startswith(PIPELINE_YML[: patched.index("TeamXHelloCloudFormation") - 300])


def test_insert_refuses_duplicate_stack():
    with pytest.raises(ValueError, match="already has a pipeline action"):
        insert_blueprint_action(PIPELINE_YML, _action("hello-world"), "aidlc-main-hello-world")


def test_parameter_overrides_render_as_valid_json():
    block = _action()
    match = re.search(r"ParameterOverrides: >-\n\s+(\{.*)", block, re.DOTALL)
    assert match
    json_text = "\n".join(line.strip() for line in match.group(1).splitlines())
    parsed = json.loads(json_text)
    assert parsed["SourceCommitId"] == "#{GitRepository.CommitId}"


def test_remove_cuts_exactly_the_action_block():
    removed = remove_blueprint_action(PIPELINE_YML, "hello-world")
    assert "HelloWorldCloudFormation" not in removed
    # the neighbouring action and the Outputs anchor survive intact
    assert "BuilderMcpCloudFormation" in removed
    assert "\nOutputs:" in removed
    # nothing outside the block moved: the removal is a pure cut of one span
    cut_at = PIPELINE_YML.index("\n", PIPELINE_YML.index("Actions:", PIPELINE_YML.index("BlueprintDeploy")))
    assert removed.startswith(PIPELINE_YML[:cut_at])


def test_insert_then_remove_round_trips_byte_identically():
    patched = insert_blueprint_action(PIPELINE_YML, _action(), "aidlc-main-team-x-hello")
    assert remove_blueprint_action(patched, "team-x-hello") == PIPELINE_YML


def test_remove_absent_action_raises():
    with pytest.raises(ValueError, match="no 'NoSuchThingCloudFormation' action"):
        remove_blueprint_action(PIPELINE_YML, "no-such-thing")


def test_remove_then_remove_again_raises():
    removed = remove_blueprint_action(PIPELINE_YML, "hello-world")
    with pytest.raises(ValueError, match="no 'HelloWorldCloudFormation' action"):
        remove_blueprint_action(removed, "hello-world")


def test_deployment_repo_shell_pins_version_and_never_copies():
    files = deployment_repo_files(
        "hello-world", "0.1.0", "blueprints/hello-world/infra/hello-world.yml",
        "team-x-hello", "aidlc-main-team-x-hello", "tmf77",
        {"owner_netid": "tmf77"}, "cu-aaii/ai-dlc-workshop",
    )
    assert set(files) == {"deployment.yaml", "README.md"}
    assert "version: 0.1.0" in files["deployment.yaml"]
    # the shell references the template, it does not contain it
    assert "AWSTemplateFormatVersion" not in files["deployment.yaml"]
    assert "merge is the only\n  trigger" in files["README.md"] or "merge is the only" in files["README.md"]


def test_deployment_shell_folder_variant_describes_the_outputs_folder():
    files = deployment_repo_files(
        "hello-world", "0.1.0", "blueprints/hello-world/infra/hello-world.yml",
        "team-x-hello", "aidlc-main-team-x-hello", "tmf77",
        {"owner_netid": "tmf77"}, "cu-aaii/ai-dlc-workshop",
        shell_location="folder",
    )
    assert set(files) == {"deployment.yaml", "README.md"}
    # same manifest either way; only the README wording knows where the shell lives
    assert "version: 0.1.0" in files["deployment.yaml"]
    assert "outputs/team-x-hello/" in files["README.md"]
    assert "This repo is a thin shell" not in files["README.md"]
