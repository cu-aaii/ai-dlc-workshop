# Implementation Summary — U-01 Domain Core

**Phase**: CONSTRUCTION → Code Generation, Part 2 (complete)
**Date**: 2026-08-03
**Plan**: `construction/plans/u-01-domain-core-code-generation-plan.md` (approved)

---

## What was generated

| Path | Lines | Step | Contents |
|---|---|---|---|
| `blueprints/dashboard/pyproject.toml` | ~55 | 1 | hatchling, dev deps, pytest/hypothesis/mypy config |
| `blueprints/dashboard/.python-version` | 1 | 1 | `3.13` |
| `blueprints/dashboard/src/dashboard/__init__.py` | 6 | 1 | namespace anchor |
| `src/dashboard/core/errors.py` | ~115 | 2 | `SkipReason`, `CoreError`, 3 subclasses |
| `src/dashboard/core/model.py` | ~430 | 3–4 | entities, normalization, (de)serialization |
| `src/dashboard/core/aggregation.py` | ~250 | 5 | presence predicate, grouping, gaps, freshness, oracle |
| `src/dashboard/core/__init__.py` | ~95 | 6 | the `__all__` contract |
| `tests/conftest.py` | ~230 | 7 | generators for all eight shapes |
| `tests/test_properties.py` | ~300 | 8 | the ten properties |
| `tests/test_examples.py` | ~340 | 9 | example-based, incl. the 10k check |
| `blueprints/dashboard/README.md` | ~90 | 12 | blueprint README |

**Modified in place** (no duplicates created — brownfield rule verified):

| Path | Change |
|---|---|
| `tools/check` | Three additive blocks: dashboard tests, core-boundary grep, mypy. Header updated. |
| `pipeline/stacks.yml` | One entry: `dashboard-marker`, `deployed_by: manual` |
| `blueprints/dashboard/infra/hello-world.yml` | **`git mv`** → `dashboard-marker.yml`, rewritten (FR-6) |

---

## Verification actually performed

The plan warned that nothing could be executed here. **That turned out to be partly wrong, in a
useful direction**, and it is worth being precise about what was and was not checked.

### Ran, and passed

| Check | How |
|---|---|
| Python syntax, all 8 files | `python3 -m py_compile` |
| `tools/check` shell syntax | `bash -n` |
| The core-boundary grep against the real core | ran the exact grep from `tools/check` — clean |
| Registry consistency | reimplemented `discover_templates()` logic: **no orphans, none registered-but-missing** |
| **~45 behavioural assertions over the core logic** | ad-hoc stdlib script importing `dashboard.core` |

Python 3.14 is present in this environment, and **U-01 has no runtime dependencies** — so the core
was importable and exercisable without `uv`, `pytest` or Hypothesis. Covered: BR-03 region/type
derivation across five ARN shapes, all seven BR-01 presence cases, BR-05 ordering with the missing
group pinned last, P3/P5/P6/P9 on concrete inputs, BR-02 skip-and-count, BR-04 last-wins dedupe, P8
in both directions, all BR-07 boundaries including the future timestamp, P1/P2 round-trip and
determinism, unknown-key tolerance, major-mismatch and minor-bump handling, four malformed payloads,
naive-timestamp rejection, PAT-1 immutability and copy-on-construct, PAT-2 hash/eq agreement, the
closed allowlist, and NFR-P2 at 10,000 records (**0.012 s**, against a 10 s bound).

### Did NOT run

| Check | Why |
|---|---|
| `pytest` — the ten properties as property tests | Hypothesis not installed |
| `mypy --strict` | not installed |
| `cfn-lint` on `dashboard-marker.yml` | not installed; `pyyaml` absent so not even a parse check |
| `tools/check` end to end | needs `uv` **and** `terraform` |
| `uv.lock` generation | needs `uv` |

**The ten properties are written but have never been executed as properties.** The logic underneath
them was exercised on concrete inputs, which is meaningfully more than nothing and meaningfully less
than a Hypothesis run — the whole point of generated input is finding the case a human did not think
to write.

---

## One real bug, found by running the code

`_resource_type` checked `/` before `:` with a fixed preference. For
`arn:aws:logs:us-east-1:123:log-group:/aws/lambda/x` the type separator is `:` and the *id* then
contains `/`, so it returned **`"log-group:"`** — with the colon attached, which is what would have
appeared in the dashboard's type column.

Fixed to take the **earliest** separator. The case is now a permanent parametrized row in
`test_examples.py`, annotated as a regression, and the generator in `conftest.py` was updated in step
so the two derivations cannot drift.

Found by executing the code against real ARN shapes rather than by reasoning about them, which is
also the argument for having done the ad-hoc run at all.

---

## Deviations from the approved plan

### 1. Step 11 was wrong: the template had to be registered

The plan said *"Not registered in `pipeline/stacks.yml` in this step"*, reasoning that registration
needs a matching pipeline action.

**That would have left `tools/check` red.** `validate_stacks.py` discovers templates by scanning for
`AWSTemplateFormatVersion` and fails on any that is unregistered — independently of pipeline
actions. Its own error text names the resolution: *"or register it as `deployed_by: manual`"*, and
`check_pipeline_actions` only demands an action when `deployed_by == 'pipeline'`.

So `dashboard-marker` is registered **`deployed_by: manual`**, which satisfies both invariants and
still avoids the silent-failure mode the plan was trying to avoid. U-02 flips it to `pipeline` in the
same change that adds the BlueprintDeploy action.

**Related pre-existing finding**: the stray `blueprints/dashboard/infra/hello-world.yml` was *also*
unregistered, so `validate_stacks.py` — and therefore `tools/check` and CI — **was already failing on
this branch before any of this work**. This change fixes that rather than causing it.

### 2. `blueprint.yaml` deliberately not created

Not in the plan's steps, and correctly so: `unit-of-work.md` assigns it to U-02. It is now also
*required* to be absent for consistency, because `CLAUDE.md` and `check_blueprint_manifests` require
a manifest to name a **registered, pipeline-deployable** template — and the marker is deliberately
`manual`. Creating the manifest now would fail the check it exists to satisfy.

### 3. A naming refinement inside Step 5's template rewrite

The plan said "resources renamed out of the `hello-world` namespace". Concretely: `HelloWorldBucket`
→ `MarkerBucket`, `HelloWorldDeploymentMarker` → `DashboardDeploymentMarker`, and a
**`DeploymentName` parameter added** so `cornell:deployment-id` and every resource name derive from
it — implementing Q9b's `singleton: false` decision rather than leaving it as a manifest field with
no template support.

---

## Requirement and story traceability

| Story | Implemented by | Verified by |
|---|---|---|
| **US-03** group by deployment/owner/blueprint | `group_by_tag` | P3, P4, P5, P6, P9 + examples |
| **US-04** spot resources missing required tags | `classify_tag_gaps`, `has_required_tag` | P7, P9 + examples |
| **US-05** know how fresh the data is | `evaluate_freshness`, `Snapshot.collected_at` | P10 + boundary examples |
| **US-10** property-based test suite | `tests/` | the suite |
| **FR-6** repurpose the stray template | `infra/dashboard-marker.yml` | registry check |

| Rule | Where |
|---|---|
| BR-01 tag presence | `aggregation.has_required_tag` — the single predicate both consumers use |
| BR-02 skip and count | `model.normalize_all` |
| BR-03 region / type | `model._resource_type`, `_GLOBAL_REGION` |
| BR-04 dedupe, last wins | `model.normalize_all` |
| BR-05 grouping and order | `aggregation.group_by_tag` |
| BR-06 gap classification | `aggregation.classify_tag_gaps` |
| BR-07 freshness | `aggregation.evaluate_freshness` |
| BR-08 serialization | `model.serialize_snapshot` / `deserialize_snapshot` |

| Pattern | Where |
|---|---|
| PAT-1 enforced immutability | `__post_init__` on all three dataclasses with Mapping fields |
| PAT-2 content hashing | explicit `__hash__` on all three |
| PAT-3 total wrapping partial | `normalize_all` over `normalize_resource` |
| PAT-4 explicit invariants | `_check_accounting` raising `InvalidSnapshot` |
| PAT-5 discriminated result | `Freshness` |
| PAT-6 injected ambient deps | `now`, `stale_after`, `collected_at` all parameters |
| PAT-7 error hierarchy | `errors.py` |
| PAT-8 closed allowlist | `group_by_tag` tag-key check, `str.split` ARN parsing |
| PAT-9 independent oracle | `_reference_group_by_tag` — written from BR-05 prose |

---

## Carried forward

- **`uv.lock` must be generated and committed** by the first person with `uv`
- **The ten properties need a real Hypothesis run** — that is Build and Test's job
- **`cfn-lint` has never seen `dashboard-marker.yml`** — not even a YAML parse check was possible
- **NFR-T5 remains review-only**: the oracle was written from BR-05's prose, but only a reader can
  confirm it was not derived from the implementation. If it was, P5 is vacuous.
- **Four cross-unit obligations to U-02** unchanged: `Freshness.INVALID` → 503; the three accounting
  counts must reach the UI; C-01 must log what U-01 deliberately cannot; RESILIENCY-04/-15 assigned
- **U-02 flips `dashboard-marker` to `deployed_by: pipeline`** when it adds the BlueprintDeploy action
