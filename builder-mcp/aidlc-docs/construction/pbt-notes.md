# Property-Based Testing Notes (Gate 1.3-A: full enforcement)

Date: 2026-08-03. Framework: **Hypothesis** (PBT-09), added to the `dev` dependency
group in `pyproject.toml`. Tests live in `tests/test_properties.py`, deliberately
separate from the example-based files (PBT-10). Run with:

```sh
uv run pytest tests/test_properties.py -q
```

Profile: `max_examples=100`, `deadline=None` (Windows timing jitter, not slow code).
Shrinking and on-failure seed reporting are Hypothesis defaults and are not disabled
(PBT-08). Domain generators (PBT-07) are centralized at the top of the test file and
derive from the real grammars: `DEPLOYMENT_NAME_PATTERN` itself (via `st.from_regex`),
CFN parameter names, semver strings, NetIDs, and well-formed blueprint manifests /
spec dicts.

## Properties enforced (13 tests, all green)

### `patching.py` — text surgery on the real `pipeline/pipeline.yml`

All insertion properties run against the actual repo `pipeline/pipeline.yml`, not a
fixture, with `assume()` guarding against names that collide with actions already in
the file.

| Property | Category |
|---|---|
| `pascal_case` output is non-empty `[A-Za-z0-9]+`, deterministic, treats `-`/`_` identically, and case-folds back to the name minus hyphens (oracle) | Invariant + Oracle (PBT-03/05) |
| `insert_blueprint_action` is a pure splice: exactly one new `- Name:`/`Namespace:` pair, placed after `BlueprintDeploy` opens and before `Outputs:`; deleting the inserted block restores the original byte-for-byte (the reviewable-diff guarantee) | Invariant (PBT-03) |
| Inserting the same deployment name twice raises `ValueError` — including when the second insert targets a different environment's stack (action name is the duplicate signal) | Business-rule invariant (PBT-03) |
| Two distinct deployments compose: sequential inserts both land exactly once and strip back to the original | Structural induction (PBT-01) |
| The rendered `ParameterOverrides` folded scalar parses back to exactly the input dict, for arbitrary unicode values and the empty dict | Round-trip (PBT-02) |
| `deployment_repo_files`: `deployment.yaml` parses, and name/owner/blueprint/version/stack/parameters all round-trip — notably the pinned `version` string survives YAML's number coercion because PyYAML quotes ambiguous scalars | Round-trip (PBT-02) |
| Neither generated file ever contains `AWSTemplateFormatVersion` (D1: reference, never copy) | Invariant (PBT-03) |

### `catalog.py`

| Property | Category |
|---|---|
| `search` is a ranking, never a filter: for any query (empty, unicode, 500-char) it returns exactly the input catalog objects with finite, non-negative, non-increasing scores | Invariant (PBT-03) |
| Ties preserve catalog order (stable sort) and repeated searches reproduce the identical ranking | Invariant + determinism (PBT-03) |
| `validate_inputs` never raises for arbitrary `provided` dicts (str/int/None/list values, extra keys); missing-required detection is complete and exact — flags precisely the required-and-absent inputs, no more, no fewer | Invariant (PBT-03) |
| Unknown provided keys are always flagged; an enum problem is reported iff the value is outside the allowed set | Invariant (PBT-03) |

### `spec_export.py`

| Property | Category |
|---|---|
| `render_spec` is total over all six audiences for any well-formed spec (optional sections present or absent), and every rendering starts with the deployment-identity header | Invariant/totality (PBT-03) |
| Any audience string outside the declared six raises `ValueError` (including case variants like `"Coder"`), regardless of spec content | Business-rule invariant (PBT-03) |

### `config.py`

| Property | Category |
|---|---|
| For every valid `Application`/`Environment` pair, `Settings.stack_name()` starts with `<application>-<environment>-`, i.e. always inside the `stack/${Application}-${Environment}*` ARN prefix `BuildPipelineRole` is scoped to (the load-bearing convention from CLAUDE.md) | Business-rule invariant (PBT-03) |

## Surprising behaviors found (verified, not fixed — modules are frozen this session)

None of these caused a test failure once understood, but all three were discovered by
thinking in properties / probing with generated inputs. Per the write-surface rules for
this session they are documented here rather than patched.

1. **`pascal_case` is not injective, so distinct deployment names can be mutually
   exclusive.** `pascal_case("a-a") == pascal_case("a--a") == "AA"`
   (`DEPLOYMENT_NAME_PATTERN` permits interior hyphen runs). Both names map to action
   name `AACloudFormation`, so whichever registers second is rejected as "already has a
   pipeline action" even though its stack name is different. This fails safe
   (over-rejection, never a silent overwrite), but the error message blames the stack,
   not the name collision. The composition property test carries an explicit
   `assume(action_name_a != action_name_b)` because of this. Candidate fix later:
   forbid consecutive hyphens in `DEPLOYMENT_NAME_PATTERN` or include the raw name in
   the duplicate error.

2. **The empty query is a universal substring, so `search(catalog, "")` scores every
   blueprint `10 * len(matches)`.** `"" in phrase` is always true, so with an empty (or
   any very generic substring) query, blueprints with more `matches` phrases rank
   higher. Harmless under proposal D2 (search ranks, the model sees everything), but
   worth knowing: an empty query's ordering reflects phrase count, not relevance.

3. **`validate_inputs` assumes manifest input specs are dicts.** A malformed
   `blueprint.yaml` with `inputs: {foo: string}` (scalar instead of mapping) makes
   `validate_inputs` raise `AttributeError: 'str' object has no attribute 'get'`,
   because `Blueprint.from_manifest` does `dict(raw.get("inputs", {}))` without
   validating the values. The totality property holds for *arbitrary provided dicts
   against well-formed blueprints* — which is the contract today, since the platform
   team authors manifests — but a builder-authored manifest could hit this. Candidate
   fix later: normalize or reject non-dict specs in `from_manifest`.

Also confirmed as designed (not bugs): `version` strings like `1.0.0` survive the YAML
round-trip because `yaml.safe_dump` quotes number-looking strings, and
`insert_blueprint_action`'s duplicate check tolerates stack names written via `!Sub` in
the existing pipeline text (the action name carries the check).

## What to property-test next (future work)

- **`github_ops.py` / `aws_ops.py`** — currently untestable without I/O. Need fakes: a
  fake GitHub client (in-memory repo/branch/PR state) would enable *stateful* PBT
  (PBT-06) over command sequences (create branch → put files → open PR → merge), with
  the in-memory model as the reference state; a stubbed CloudFormation/`boto3` client
  would let the stack-status and tag-audit paths be property-tested for totality over
  arbitrary API response shapes. This is the main PBT-06 gap: nothing purely stateful
  exists in the pure modules today, so PBT-06 is N/A for this unit.
- **`server.py` tool layer** — out of scope this session (concurrent rename in
  flight). Once stable: property-test that every tool's response is JSON-serializable
  for arbitrary valid inputs, and that dry-run mode (no `GITHUB_TOKEN`) never attempts
  a write.
- **Round-trip through a real YAML consumer** — the `ParameterOverrides` property
  parses the folded scalar the way the tests do; a stronger version would feed the
  patched `pipeline.yml` to `cfn-lint` (already a repo tool) as an easy-verification
  property, at the cost of runtime.
- **Regression pinning (PBT-10)** — if any property fails in CI, add the shrunk
  counterexample to the example-based files as a permanent regression test.
