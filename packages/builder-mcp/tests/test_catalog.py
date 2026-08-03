from builder_mcp.catalog import load_catalog, search, validate_inputs
from builder_mcp.config import Settings, find_repo_root

REPO_ROOT = find_repo_root()

SETTINGS = Settings(
    github_org="cu-aaii", workshop_repo="ai-dlc-workshop", application="aidlc",
    environment="main", aws_region="us-east-1", github_token=None, repo_root=REPO_ROOT,
)


def test_catalog_loads_hello_world():
    catalog = load_catalog(SETTINGS)
    names = [b.name for b in catalog]
    assert "hello-world" in names
    hello = next(b for b in catalog if b.name == "hello-world")
    assert hello.template == "blueprints/hello-world/infra/hello-world.yml"
    assert hello.singleton is True
    assert (REPO_ROOT / hello.template).is_file()


def test_search_ranks_relevant_blueprint_first():
    catalog = load_catalog(SETTINGS)
    ranked = search(catalog, "smoke test that the deploy path works")
    assert ranked[0][1].name == "hello-world"
    assert ranked[0][0] > 0
    # every blueprint is returned -- search ranks, it never hides (D2)
    assert len(ranked) == len(catalog)


def test_validate_inputs_flags_missing_and_unknown():
    catalog = load_catalog(SETTINGS)
    hello = next(b for b in catalog if b.name == "hello-world")
    problems = validate_inputs(hello, {})
    assert any("owner_netid" in p for p in problems)
    problems = validate_inputs(hello, {"owner_netid": "tmf77", "bogus": "x"})
    assert any("unknown input 'bogus'" in p for p in problems)
    assert validate_inputs(hello, {"owner_netid": "tmf77"}) == []
