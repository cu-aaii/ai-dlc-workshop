# Tech Stack Decisions — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Requirements (artifact 2 of 2)
**Date**: 2026-08-03

Two kinds of entry below, kept separate on purpose: choices the **repo already made**, cited rather than
re-argued; and choices **made here**, with rationale and rejected alternatives.

---

## Part 1 — Established by precedent, not re-decided

Found in `packages/builder-mcp/` before writing this stage's questions. Re-deciding these would have
produced a second convention for no benefit.

| Decision | Value | Where it comes from |
|---|---|---|
| Language | Python | Repo-wide; `CLAUDE.md` |
| PBT framework | **Hypothesis** `>=6.100` | `packages/builder-mcp/pyproject.toml`; `test_properties.py` cites PBT-09 |
| Test runner | **pytest** `>=8`, `testpaths = ["tests"]` | same |
| Python floor | `requires-python = ">=3.11"` | same |
| Interpreter pin | **`.python-version` = `3.13`** | same, and required by the `uv`-picks-32-bit gotcha in `CLAUDE.md` |
| Build backend | **hatchling**, `src/` layout | same |
| Dependency manager | **`uv`** with a committed lockfile | repo-wide; `tools/check`'s only Python prerequisite |
| Container arch | **arm64** | Q8 of Units Generation |

**The `.python-version` pin is not boilerplate.** `CLAUDE.md` records that `uv` will pick a 32-bit Python
if that is what it finds, and on such a machine `cryptography` has no wheel and the install disappears
into a failing Rust build. U-01 does not depend on `cryptography` — but it shares a lockfile with U-02's
code, which depends on `boto3`, so the pin belongs here regardless.

---

## Part 2 — Decided at this stage

### TSD-1 — Layout: `src/`, one package, subpackages per component

**Decision**
```
blueprints/dashboard/
  blueprint.yaml
  README.md
  Dockerfile              targets: collector, api  (context = this directory)
  pyproject.toml          the blueprint's Python project
  .python-version         3.13
  uv.lock
  infra/                  dashboard-storage.yml, dashboard.yml
  src/dashboard/
    core/                 U-01 — no boto3, no os, no datetime.now()
    collector/            U-02
    api/                  U-02
  ui/                     U-02 — Node, deliberately outside src/
  tests/
```

**From** Q1 = A (adopt `src/`) plus the naming refinement in Part A2 Interaction 4.

**Why `src/`**: both blueprints written since the monorepo reorganization use it
(`blueprints/tiny-chatbot/src/app.py`, `blueprints/aisei-site/app/`), and `CLAUDE.md` documents the
blueprint shape as "`blueprint.yaml` + `infra/` (+ `src/`, `infra/azure/`)". Checked empirically rather
than inferred from the doc alone.

**Why one package rather than three**: the alternative implied `import core` — a top-level importable named
`core` is generic enough to collide and tells a reader nothing about what project it belongs to. One
package gives namespaced imports (`from dashboard.core import group_by_tag`), one hatchling target, and a
boundary check that is still a single grep.

**Rejected**: the approved Q3 = A flat layout — supersedes it, recorded as **amendment A3** with a pointer
in `unit-of-work.md`. Also rejected: `ui/` under `src/`, since `src/` reads as Python here and a Node
project inside it surprises more than it helps.

**Preserved**: the Dockerfile context stays `blueprints/dashboard/`. Only `COPY` paths move from `core/`
to `src/dashboard/core/`. The A2.2 reasoning — both images need the core package, so a `collector/`-scoped
context cannot work — is unaffected.

### TSD-2 — One `pyproject.toml` for the whole blueprint's Python

**From** Q2 = A.

Covers both Lambdas and the tests. Hosts the `.python-version` pin, pytest config, Hypothesis profile,
and mypy config. `uv.lock` committed beside it.

**Why not per-unit**: U-01 and U-02's Python ship in the same two images and are tested by the same suite.
Two projects would mean two lockfiles that must agree about `boto3` and Hypothesis, with nothing enforcing
the agreement.

**Why not none** (which is what `tiny-chatbot` does): no lockfile means a laptop, PR checks and CodeBuild
can resolve different Hypothesis versions, and `.python-version` would have nowhere to live — reintroducing
the exact failure `CLAUDE.md` documents.

**Why not `packages/dashboard-core/`**: it would break TSD-1's Docker context, and `packages/` is
documented as being for "a component that **isn't** a blueprint."

### TSD-3 — Dependency inventory

| Scope | Dependencies |
|---|---|
| **U-01 runtime** | **None. Standard library only.** |
| U-02 runtime | `boto3` (both Lambdas) |
| Dev / test | `pytest`, `hypothesis`, `mypy` |

**U-01's empty runtime row is a designed property, enforced by NFR-M5**, not an accident of a small
codebase. Three consequences:

1. **It is the reason arm64 carries no risk here.** The one concern flagged when Q8 of Units Generation
   chose arm64 was a Python wheel with no aarch64 build compiling from source. A standard-library-only
   package has no wheels to resolve. `boto3` is pure Python. So the flagged arm64 risk is, for this
   blueprint, **empty** — worth stating because it was recorded as an open risk.
2. **It makes US-09 and Q11 = B nearly moot for U-01.** There is no U-01 dependency to pin, scan, or put in
   an SBOM. The supply-chain surface is entirely U-02's `boto3` plus the npm tree, which is where Q11 = B's
   scanning decision actually applies.
3. **A new runtime dependency under `core/` is a boundary violation signal**, not a dependency decision.

### TSD-4 — mypy strict, scoped to the core package

**From** Q4 = A. `[[tool.mypy.overrides]]` targets `dashboard.core.*` with `strict = true`; the rest of the
blueprint is unchecked for now.

**Why scoped**: strict mode over frozen dataclasses and pure functions is nearly free and catches the two
places this design's optionality actually lives — `Group.value: str | None` and the three-valued
`Freshness`. Over `boto3` response shapes it produces noise that gets silenced with `# type: ignore`, and a
checker people routinely silence is worse than no checker.

**Recorded as a boundary (NFR-M3)** so strict mode neither creeps outward unremarked nor gets quietly
dropped. Extending it to `collector/` and `api/` is U-02's decision at its own NFR pass.

**New dev dependency and a new `tools/check` step.** Both accepted.

### TSD-5 — ARN parsing by `str.split`, not regex

**From** Q7 = A. `str.split(":", 5)` with explicit arity and emptiness checks.

**Why**: an ARN is a fixed six-field colon-delimited grammar, so a regex buys nothing a split does not
already give, while adding a backtracking surface. A permissive pattern would also silently accept
malformed ARNs that a split-plus-check rejects — and rejecting them is what feeds `skipped_reasons`.

Not driven by current risk: ARNs come from AWS, not users. Driven by "the input is trusted" being a
property that erodes — the collector is one configuration change away from reading a file.

### TSD-6 — Hypothesis profile: `max_examples = 100`

**From** Q5 = A. Matches `packages/builder-mcp`, which notes the PBT rules cap at 200. Shrinking and seed
reporting stay at Hypothesis defaults (PBT-08 forbids disabling them).

**The 10,000-record size check is NOT a Hypothesis property.** It is a single example-based test with
deterministic input (NFR-P2, NFR-T4). Part A2 Interaction 5 records why: at `max_examples=100`, generating
10k-record snapshots a hundred times would dominate the pre-push gate for a check that needs no
randomness. The `_reference_group_by_tag` oracle is excluded from it — running a quadratic reference at 10k
would measure the test double, not the implementation.

### TSD-7 — `tools/check` hosts the gate

**From** Q3 = A.

**The pattern already exists.** `tools/check` runs:

```sh
cd packages/builder-mcp && uv run --quiet pytest -q
```

U-01's block mirrors it exactly, including the two non-obvious details the existing block's comments
record: run **from the package directory** (pytest resolves `testpaths` against its own rootdir, and
rootdir follows the invocation directory), and rely on `.python-version` so `uv` fetches a 64-bit CPython.

So Q3 = A adds a third block to a script that already does this — not a new capability. My Q3 preamble
said the script "currently lints CloudFormation and validates the registry," which was incomplete;
corrected in Part A2 Interaction 1.

**`tools/dev` was evaluated and rejected** as the host: it starts the builder-mcp server and its browser
console for interactive work. It is this repo's `npm run dev`, not a gate.

**Copying the known-green block rather than inventing an invocation shape matters more than usual here**,
because `tools/check` cannot run in the environment these decisions were made in.

---

## ⚠️ Specified but unexecuted

`tools/check` requires **`uv` and `terraform`**; neither is installed here (amendment §A1.6). So TSD-4's
mypy step, TSD-6's profile, TSD-7's test block, and NFR-M1/M2/T1/T6's automated checks are **written but
never run**. First real verification is CI or a machine with both installed.

Not a defect in the decisions — but it does mean "automated" in `nfr-requirements.md` currently describes
intent rather than observed behaviour, and the distinction should not be blurred at Build and Test.
