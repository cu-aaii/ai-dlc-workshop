import pytest

from builder_mcp.spec_export import AUDIENCES, render_spec

SPEC = {
    "blueprint": {
        "name": "hello-world", "version": "0.1.0", "maturity": "supported",
        "maintainer": "ai-sei@cornell.edu",
        "summary": "Trivial tagged stack that proves the deploy path.",
        "template": "blueprints/hello-world/infra/hello-world.yml",
        "inputs": {"owner_netid": {"type": "string", "required": True}},
        "cost": {"baseline_monthly_usd": 0},
        "data_classification": ["public"],
        "state": [],
    },
    "deployment": {
        "name": "hello-world", "stack": "aidlc-main-hello-world", "owner": "tmf77",
        "pipeline": "aidlc-main", "parameters": {"owner_netid": "tmf77"},
    },
    "status": {"status": "CREATE_COMPLETE", "outputs": {"BucketName": "aidlc-main-hello-world-123"}},
}


@pytest.mark.parametrize("audience", AUDIENCES)
def test_every_audience_renders(audience):
    text = render_spec(audience, SPEC)
    assert text.startswith("# hello-world")
    assert "hello-world" in text


def test_unknown_audience_rejected():
    with pytest.raises(ValueError, match="audience must be one of"):
        render_spec("marketing", SPEC)


def test_security_spec_covers_the_gate_and_tags():
    text = render_spec("security", SPEC)
    assert "merge to the tracked branch only" in text
    assert "cornell:owner" in text


def test_narrative_spec_has_no_jargon_anchor():
    text = render_spec("narrative", SPEC)
    assert "plain language" in text
    assert "CloudFormation" not in text  # the narrative audience never sees IaC vocabulary
