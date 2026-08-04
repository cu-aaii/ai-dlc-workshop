"""Property-based tests for builder-mcp's pure modules (Gate 1.3-A: full PBT enforcement).

Complements the example-based tests (PBT-10); this file contains ONLY property tests.
Each test's docstring names the property category from
docs/aidlc-rules/.../property-based-testing.md (PBT-02 round-trip, PBT-03 invariant, etc.).

Framework: Hypothesis (PBT-09). Shrinking and seed logging are Hypothesis defaults and
are not disabled (PBT-08). Domain generators (PBT-07) live in the "Strategies" section
below and mirror the real grammars: DEPLOYMENT_NAME_PATTERN, CFN parameter names,
semver, NetIDs, blueprint manifests.

Runtime is capped via the profile below (max_examples=100 <= 200).
"""

from __future__ import annotations

import json
import math
import re

import pytest
import yaml
from hypothesis import assume, example, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from builder_mcp.catalog import Blueprint, search, validate_inputs
from builder_mcp.config import Settings, find_repo_root
from builder_mcp.patching import (
    DEPLOYMENT_NAME_PATTERN,
    deployment_repo_files,
    insert_blueprint_action,
    pascal_case,
    render_pipeline_action,
)
from builder_mcp.spec_export import AUDIENCES, render_spec

PIPELINE_YML = (find_repo_root() / "pipeline" / "pipeline.yml").read_text(encoding="utf-8")

# deadline=None: text ops on the real 20 KB pipeline.yml are fast but Windows CI timing
# is jittery; Hypothesis still shrinks and prints the reproducing seed on failure.
hyp_settings.register_profile("builder-mcp-pbt", max_examples=100, deadline=None)
hyp_settings.load_profile("builder-mcp-pbt")

# ---------------------------------------------------------------------------
# Strategies (PBT-07: domain generators, centralized and reused)
# ---------------------------------------------------------------------------

# Mirrors the grammar the tool layer enforces. DEPLOYMENT_NAME_PATTERN now carries a
# negative lookahead (no consecutive hyphens — the '--' non-injectivity fix), which
# st.from_regex cannot generate reliably, so build names segment-wise and confirm each
# against the real pattern; the filter also enforces the 2-30 length bounds.
deployment_names = (
    st.lists(st.from_regex(r"[a-z0-9]{1,8}", fullmatch=True), min_size=1, max_size=3)
    .map("-".join)
    .filter(lambda s: DEPLOYMENT_NAME_PATTERN.fullmatch(s) is not None)
)

cfn_param_names = st.from_regex(r"[A-Za-z][A-Za-z0-9]{0,19}", fullmatch=True)
semvers = st.from_regex(r"[0-9]{1,2}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)
netids = st.from_regex(r"[a-z]{2,3}[0-9]{1,4}", fullmatch=True)

override_dicts = st.dictionaries(cfn_param_names, st.text(max_size=40), max_size=6)

# Free-form text for parameters that end up in the deployment repo shell; keep the
# CloudFormation marker out so the "never embeds the template" assertion is meaningful.
_shell_text = st.text(max_size=30).filter(lambda s: "AWSTemplateFormat" not in s)
shell_param_dicts = st.dictionaries(_shell_text, _shell_text, max_size=5)

input_spec_dicts = st.dictionaries(
    st.from_regex(r"[a-z][a-z0-9_]{0,11}", fullmatch=True),
    st.fixed_dictionaries(
        {},
        optional={
            "required": st.booleans(),
            "type": st.sampled_from(["string", "int", "enum"]),
            "values": st.lists(st.text(max_size=6), max_size=4),
            "description": st.text(max_size=15),
        },
    ),
    max_size=4,
)

blueprint_objects = st.builds(
    Blueprint,
    name=deployment_names,
    version=semvers,
    summary=st.text(max_size=40),
    maturity=st.sampled_from(["experimental", "beta", "stable"]),
    maintainer=netids,
    matches=st.lists(st.text(max_size=25), max_size=4),
    inputs=input_spec_dicts,
    template=st.just("blueprints/x/infra/x.yml"),
)

catalogs = st.lists(blueprint_objects, max_size=6)

queries = st.one_of(st.just(""), st.text(max_size=500))


@st.composite
def blueprint_with_provided(draw):
    """A well-formed blueprint plus an arbitrary `provided` dict that may hit, miss, or
    add to its declared inputs."""
    bp = draw(blueprint_objects)
    provided: dict = {}
    arbitrary_values = st.one_of(
        st.text(max_size=8),
        st.integers(-5, 5),
        st.none(),
        st.lists(st.integers(0, 3), max_size=2),
    )
    for input_name in bp.inputs:
        if draw(st.booleans()):
            provided[input_name] = draw(arbitrary_values)
    provided.update(draw(st.dictionaries(st.text(max_size=6), arbitrary_values, max_size=3)))
    return bp, provided


@st.composite
def well_formed_specs(draw):
    """A spec dict shaped like server-side spec assembly: required keys always present,
    optional sections (cost, state, repo, status, tag_audit) present or absent."""
    dep_name = draw(deployment_names)
    spec: dict = {
        "blueprint": {
            "name": draw(deployment_names),
            "version": draw(semvers),
            "maturity": draw(st.sampled_from(["experimental", "beta", "stable"])),
            "summary": draw(st.text(max_size=40)),
            "maintainer": draw(netids),
            "template": "blueprints/x/infra/x.yml",
            "inputs": draw(input_spec_dicts),
        },
        "deployment": {
            "name": dep_name,
            "owner": draw(netids),
            "stack": f"aidlc-main-{dep_name}",
            "pipeline": "aidlc-main",
            "parameters": draw(st.dictionaries(cfn_param_names, st.text(max_size=15), max_size=4)),
        },
    }
    if draw(st.booleans()):
        spec["blueprint"]["cost"] = {"baseline_monthly_usd": draw(st.integers(0, 500))}
    if draw(st.booleans()):
        spec["blueprint"]["state"] = draw(
            st.lists(st.fixed_dictionaries({"kind": st.sampled_from(["s3", "dynamodb"])}), max_size=2)
        )
    if draw(st.booleans()):
        spec["blueprint"]["data_classification"] = draw(
            st.lists(st.sampled_from(["public", "internal"]), max_size=2)
        )
    if draw(st.booleans()):
        spec["deployment"]["repo"] = "cu-aaii/deploy-x"
    if draw(st.booleans()):
        spec["status"] = {
            "status": "CREATE_COMPLETE",
            "outputs": draw(st.dictionaries(cfn_param_names, st.text(max_size=10), max_size=2)),
        }
    if draw(st.booleans()):
        spec["tag_audit"] = draw(st.dictionaries(cfn_param_names, st.text(max_size=8), max_size=3))
    return spec


def _action_name(deployment_name: str) -> str:
    return f"{pascal_case(deployment_name)}CloudFormation"


def _fresh_in_pipeline(deployment_name: str) -> bool:
    """True when this generated name does not collide with actions already present in
    the real pipeline.yml (e.g. hello-world)."""
    return (
        f"'{_action_name(deployment_name)}'" not in PIPELINE_YML
        and f"'aidlc-main-{deployment_name}'" not in PIPELINE_YML
    )


def _render(name: str, overrides: dict[str, str], env: str = "main") -> tuple[str, str]:
    stack = f"aidlc-{env}-{name}"
    block = render_pipeline_action(
        deployment_name=name,
        template_path=f"blueprints/{name}/infra/{name}.yml",
        stack_name=stack,
        parameter_overrides=overrides,
    )
    return block, stack


# ---------------------------------------------------------------------------
# patching.pascal_case
# ---------------------------------------------------------------------------


@given(name=deployment_names)
def test_pascal_case_shape_determinism_and_character_oracle(name):
    """PBT-03 invariant + PBT-05 oracle: for every grammar-valid deployment name the
    action-name stem is non-empty [A-Za-z0-9]+, deterministic, treats '-' and '_' the
    same, and preserves exactly the non-hyphen characters (case-folded oracle)."""
    out = pascal_case(name)
    assert re.fullmatch(r"[A-Za-z0-9]+", out), out
    assert out == pascal_case(name)  # deterministic
    assert out == pascal_case(name.replace("-", "_"))  # separator equivalence
    assert out.lower() == name.replace("-", "")  # character-preservation oracle


# ---------------------------------------------------------------------------
# patching.render_pipeline_action + insert_blueprint_action
# ---------------------------------------------------------------------------


@given(name=deployment_names, overrides=override_dicts)
def test_insert_adds_exactly_one_action_and_splices_cleanly(name, overrides):
    """PBT-03 invariant: insertion is a pure splice. Exactly one new action appears,
    inside the Stages list (before Outputs), and deleting the inserted block restores
    the original byte-for-byte (reviewable diff guarantee)."""
    assume(_fresh_in_pipeline(name))
    block, stack = _render(name, overrides)
    patched = insert_blueprint_action(PIPELINE_YML, block, stack)

    action = _action_name(name)
    assert patched.count(f"- Name: '{action}'") == 1
    assert patched.count(f"Namespace: '{action}'") == 1
    # the new action lands after the BlueprintDeploy stage opens and before Outputs
    assert (
        patched.index("- Name: 'BlueprintDeploy'")
        < patched.index(f"- Name: '{action}'")
        < patched.index("\nOutputs:")
    )
    # splice property: original text is untouched outside the insertion
    assert patched.replace(block, "", 1) == PIPELINE_YML
    point = patched.index(block)
    assert patched[:point] == PIPELINE_YML[:point]
    assert patched[point + len(block):] == PIPELINE_YML[point:]


@given(name=deployment_names, overrides=override_dicts)
def test_insert_same_deployment_twice_raises(name, overrides):
    """PBT-03 business-rule invariant: re-registering an already-registered deployment
    is always rejected, never silently duplicated."""
    assume(_fresh_in_pipeline(name))
    block, stack = _render(name, overrides)
    patched = insert_blueprint_action(PIPELINE_YML, block, stack)
    with pytest.raises(ValueError, match="already has a pipeline action"):
        insert_blueprint_action(patched, block, stack)
    # ... even when the second registration targets a different environment's stack:
    # the action name (derived 1:1 from the deployment name) is the duplicate signal.
    block2, stack2 = _render(name, overrides, env="test")
    with pytest.raises(ValueError):
        insert_blueprint_action(patched, block2, stack2)


@given(name_a=deployment_names, name_b=deployment_names, overrides=override_dicts)
def test_insert_two_distinct_deployments_composes(name_a, name_b, overrides):
    """PBT-01 structural induction: registrations compose. Two distinct deployments
    insert sequentially, both actions are present exactly once, and removing both
    blocks restores the original file."""
    assume(_fresh_in_pipeline(name_a) and _fresh_in_pipeline(name_b))
    assume(name_a != name_b)
    # The '--' collision ('a-a' vs 'a--a') is now rejected by DEPLOYMENT_NAME_PATTERN
    # itself, but pascal_case is still not injective for digit-initial segments
    # ('a-1b' and 'a1b' both map to 'A1b'); colliding pairs are rejected as duplicates
    # by design, so restrict to distinct action names here.
    assume(_action_name(name_a) != _action_name(name_b))
    block_a, stack_a = _render(name_a, overrides)
    block_b, stack_b = _render(name_b, overrides)
    patched = insert_blueprint_action(PIPELINE_YML, block_a, stack_a)
    patched = insert_blueprint_action(patched, block_b, stack_b)
    assert patched.count(f"- Name: '{_action_name(name_a)}'") == 1
    assert patched.count(f"- Name: '{_action_name(name_b)}'") == 1
    assert patched.replace(block_b, "", 1).replace(block_a, "", 1) == PIPELINE_YML


@given(name=deployment_names, overrides=override_dicts)
def test_parameter_overrides_round_trip_through_rendered_block(name, overrides):
    """PBT-02 round-trip: the ParameterOverrides folded scalar in the rendered action
    parses back to exactly the dict that was passed in, for any CFN-shaped keys and
    arbitrary unicode values (including empty dicts)."""
    block, _ = _render(name, overrides)
    match = re.search(r"ParameterOverrides: >-\n\s+(\{.*)", block, re.DOTALL)
    assert match, block
    json_text = "\n".join(line.strip() for line in match.group(1).splitlines())
    assert json.loads(json_text) == overrides


# ---------------------------------------------------------------------------
# patching.deployment_repo_files
# ---------------------------------------------------------------------------


@given(
    bp_name=deployment_names,
    version=semvers,
    dep_name=deployment_names,
    owner=netids,
    params=shell_param_dicts,
)
def test_deployment_repo_manifest_round_trips_and_never_embeds_template(
    bp_name, version, dep_name, owner, params
):
    """PBT-02 round-trip: deployment.yaml parses as YAML and every identity field —
    including the pinned blueprint version, which YAML could otherwise coerce to a
    number — round-trips exactly. PBT-03 invariant: the shell references the blueprint
    and never contains the CloudFormation format-version marker (D1: reference, never
    copy)."""
    stack = f"aidlc-main-{dep_name}"
    files = deployment_repo_files(
        blueprint_name=bp_name,
        blueprint_version=version,
        template_path=f"blueprints/{bp_name}/infra/{bp_name}.yml",
        deployment_name=dep_name,
        stack_name=stack,
        owner_netid=owner,
        parameters=params,
        workshop_repo_full="cu-aaii/ai-dlc-workshop",
    )
    assert set(files) == {"deployment.yaml", "README.md"}

    manifest = yaml.safe_load(files["deployment.yaml"])
    assert manifest["metadata"]["name"] == dep_name
    assert manifest["metadata"]["owner"] == owner
    assert manifest["blueprint"]["name"] == bp_name
    assert manifest["blueprint"]["version"] == version  # pinned, still a string
    assert manifest["stack"] == stack
    assert manifest["parameters"] == params

    for content in files.values():
        assert "AWSTemplateFormatVersion" not in content


# ---------------------------------------------------------------------------
# catalog.search
# ---------------------------------------------------------------------------


@given(catalog=catalogs, query=queries)
@example(catalog=[], query="")
def test_search_is_a_ranking_never_a_filter(catalog, query):
    """PBT-03 invariant: for any query (empty, unicode, long) search returns exactly
    the input catalog — same size, same objects — with finite non-negative scores in
    non-increasing order."""
    ranked = search(catalog, query)
    assert len(ranked) == len(catalog)
    assert sorted(id(bp) for _, bp in ranked) == sorted(id(bp) for bp in catalog)
    scores = [score for score, _ in ranked]
    assert all(isinstance(score, float) and math.isfinite(score) and score >= 0 for score in scores)
    assert all(a >= b for a, b in zip(scores, scores[1:]))


@given(catalog=catalogs, query=queries)
def test_search_is_deterministic_and_ties_keep_catalog_order(catalog, query):
    """PBT-03 invariant (ordering stability) + determinism: equal-scored blueprints
    stay in catalog order, and repeating the same search reproduces the same ranking."""
    ranked = search(catalog, query)
    position = {id(bp): i for i, bp in enumerate(catalog)}
    for (score_a, bp_a), (score_b, bp_b) in zip(ranked, ranked[1:]):
        if score_a == score_b:
            assert position[id(bp_a)] < position[id(bp_b)]
    again = search(catalog, query)
    assert [(score, id(bp)) for score, bp in ranked] == [(score, id(bp)) for score, bp in again]


# ---------------------------------------------------------------------------
# catalog.validate_inputs
# ---------------------------------------------------------------------------


@given(pair=blueprint_with_provided())
def test_validate_inputs_is_total_and_missing_required_detection_is_complete(pair):
    """PBT-03 invariant: validate_inputs never raises for arbitrary provided dicts,
    and flags exactly the required-but-missing inputs — no more, no fewer."""
    bp, provided = pair
    problems = validate_inputs(bp, provided)  # must not raise
    assert all(isinstance(p, str) for p in problems)

    missing_required = [
        name for name, spec in bp.inputs.items() if spec.get("required") and name not in provided
    ]
    flagged = [p for p in problems if p.startswith("missing required input")]
    assert len(flagged) == len(missing_required)
    for name in missing_required:
        assert any(f"missing required input {name!r}" in p for p in problems)


@given(pair=blueprint_with_provided())
def test_validate_inputs_flags_unknown_inputs_and_enum_violations_exactly(pair):
    """PBT-03 invariant: every provided key outside the manifest is flagged as unknown,
    and an enum problem is reported iff the provided value is outside the allowed set."""
    bp, provided = pair
    problems = validate_inputs(bp, provided)
    for name in provided:
        if name not in bp.inputs:
            assert any(f"unknown input {name!r}" in p for p in problems)
    for name, spec in bp.inputs.items():
        if name in provided and spec.get("type") == "enum":
            violates = provided[name] not in spec.get("values", [])
            reported = any(p.startswith(f"input {name!r} must be one of") for p in problems)
            assert reported == violates


# ---------------------------------------------------------------------------
# spec_export.render_spec
# ---------------------------------------------------------------------------


@given(spec=well_formed_specs())
def test_render_spec_is_total_over_all_six_audiences(spec):
    """PBT-03 invariant (type preservation/totality): for a well-formed spec, every
    declared audience renders without raising, and every rendering carries the
    deployment identity header."""
    assert len(AUDIENCES) == 6
    for audience in AUDIENCES:
        out = render_spec(audience, spec)
        assert isinstance(out, str)
        assert out.startswith(f"# {spec['deployment']['name']} — {audience} spec")
        assert spec["blueprint"]["name"] in out


@given(
    audience=st.text(max_size=20).filter(lambda s: s not in AUDIENCES),
    spec=well_formed_specs(),
)
@example(audience="Coder", spec=None)  # case matters; spec replaced below
def test_render_spec_rejects_unknown_audiences(audience, spec):
    """PBT-03 business-rule invariant: any audience outside the declared six raises
    ValueError before the spec is touched."""
    if spec is None:  # from the @example: the spec must be irrelevant to the rejection
        spec = {"blueprint": {}, "deployment": {}}
    with pytest.raises(ValueError, match="audience must be one of"):
        render_spec(audience, spec)


# ---------------------------------------------------------------------------
# config.Settings naming conventions
# ---------------------------------------------------------------------------


@given(
    app=st.from_regex(r"[a-z0-9]{1,10}", fullmatch=True),
    env=st.from_regex(r"[a-z0-9]{1,4}", fullmatch=True),
    dep_name=deployment_names,
    org=st.from_regex(r"[a-z][a-z0-9-]{0,10}", fullmatch=True),
    repo=st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True),
)
def test_settings_stack_names_always_fall_under_pipeline_role_scope(app, env, dep_name, org, repo):
    """PBT-03 business-rule invariant: for every valid Application/Environment pair,
    generated stack names start with `<application>-<environment>-`, i.e. they always
    fall inside the `stack/${Application}-${Environment}*` ARN prefix that
    BuildPipelineRole is scoped to — the convention CLAUDE.md calls load-bearing."""
    settings = Settings(
        github_org=org,
        workshop_repo=repo,
        application=app,
        environment=env,
        aws_region="us-east-1",
        github_token=None,
        repo_root=None,
    )
    assert settings.pipeline_name == f"{app}-{env}"
    assert settings.stack_name(dep_name) == f"{app}-{env}-{dep_name}"
    assert settings.stack_name(dep_name).startswith(settings.pipeline_name + "-")
    assert settings.workshop_repo_full == f"{org}/{repo}"
