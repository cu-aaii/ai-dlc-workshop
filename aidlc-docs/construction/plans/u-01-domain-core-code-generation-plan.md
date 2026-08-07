# Code Generation Plan — U-01 Domain Core

**Phase**: CONSTRUCTION → Code Generation, **Part 1 (Planning)**
**Date**: 2026-08-03
**Unit**: U-01 Domain Core
**Stories**: US-03, US-04, US-05, US-10
**This plan is the single source of truth for Part 2.** Generation executes these steps in order and
nothing else.

---

## Unit context

| | |
|---|---|
| **Owns** | C-04 Inventory Model, C-05 Aggregation Core |
| **Depends on** | nothing — empty dependency row |
| **Depended on by** | U-02 (in-process import only) |
| **Contract** | `__all__` in `src/dashboard/core/__init__.py` |
| **Runtime dependencies** | **none — standard library only** (NFR-M5) |
| **Verification** | ten Hypothesis properties + example tests, no AWS |

**Design inputs**: `functional-design/` (BR-01..BR-08, entities, algorithms, ten properties) ·
`nfr-requirements/` (26 requirements, TSD-1..TSD-7) · `nfr-design/` (PAT-1..PAT-9, error hierarchy,
`__all__` surface). Infrastructure Design **skipped** for this unit.

**Project type**: brownfield repo, greenfield unit. `blueprints/dashboard/` currently holds only
`docs/design-language.md` (written by another team) and the stray `infra/hello-world.yml`. **No file this
plan creates already exists**, so every step is a create — except Step 10, which modifies `tools/check`
in place, and Step 11, which modifies the stray template.

---

## Code location

**Application code at the workspace root. Never in `aidlc-docs/`.**

```
blueprints/dashboard/
  pyproject.toml            Step 1
  .python-version           Step 1
  src/dashboard/__init__.py Step 1
  src/dashboard/core/
    errors.py               Step 2
    model.py                Steps 3-4
    aggregation.py          Step 5
    __init__.py             Step 6
  tests/
    conftest.py             Step 7   generators
    test_properties.py      Step 8   the ten properties
    test_examples.py        Step 9   example-based, incl. the 10k size check
```

Markdown summaries only go to `aidlc-docs/construction/u-01-domain-core/code/`.

---

## Steps

### Step 1 — Project structure and packaging
- [x] `blueprints/dashboard/pyproject.toml` — hatchling, `packages = ["src/dashboard"]`,
      `requires-python = ">=3.11"`, dev group `pytest>=8`, `hypothesis>=6.100`, `mypy>=1.10`
- [x] `[tool.pytest.ini_options] testpaths = ["tests"]` — mirrors `packages/builder-mcp` so the
      `tools/check` invocation pattern transfers unchanged (TSD-7)
- [x] `[tool.hypothesis]` profile with `max_examples = 100` (TSD-6, NFR-T2); shrinking and seed reporting
      left at defaults (NFR-T3)
- [x] `[tool.mypy]` with an override making `dashboard.core.*` **strict** — and nothing else (TSD-4,
      NFR-M2, NFR-M3)
- [x] `blueprints/dashboard/.python-version` = `3.13` (TSD-1; the `uv`-picks-32-bit gotcha)
- [x] `src/dashboard/__init__.py` — empty namespace anchor, no re-exports
- [x] **`uv.lock` CANNOT be generated here** — `uv` is not installed (§A1.6). Recorded as an explicit
      follow-up rather than silently omitted; the first `uv run` on a machine with `uv` creates it and it
      must be committed (TSD-2's reproducibility argument depends on it)

### Step 2 — `errors.py` (PAT-7, Q3 = A)
- [x] `CoreError(Exception)` base
- [x] `MalformedResource(CoreError)` carrying a `category` from a **closed** `StrEnum`
      (`ARN`, `TAGS`) — NFR-S2, an enum not free text
- [x] `IncompatibleSchema(CoreError)`, `InvalidSnapshot(CoreError)`
- [x] **NFR-S1**: no exception accepts or stores an ARN, tag key, tag value, or input index. `__str__`
      and `repr` expose the category only
- [x] Docstrings naming BR-02 / BR-08 and the U-02 HTTP outcome each maps to (NFR-M4)

### Step 3 — `model.py` entities (PAT-1, PAT-2)
- [x] `ResourceRecord` — `@dataclass(frozen=True)`, fields `arn`, `service`, `resource_type`, `region`,
      `tags`
- [x] `__post_init__` wrapping `tags` via `object.__setattr__(self, "tags", MappingProxyType(dict(tags)))`
      — **both** the `object.__setattr__` and the `dict()` copy are mandatory, per Part A2 Interaction 1
- [x] Explicit `__hash__` over `(arn, service, resource_type, region, frozenset(tags.items()))` —
      **required**, because the generated one would hash a `MappingProxyType` and raise `TypeError`
- [x] `Snapshot` — `@dataclass(frozen=True)`, fields `schema_version`, `collected_at`, `resources`,
      `raw_returned`, `skipped_count`, `skipped_reasons`, `duplicates_removed`
- [x] Same wrapping and hashing treatment for `Snapshot.skipped_reasons` (Part A2 Interaction 2)
- [x] `NormalizationResult` frozen dataclass
- [x] `REQUIRED_TAGS` — the four `cornell:*` keys, lowercase, ordered, a `tuple`
- [x] `SCHEMA_VERSION` constant, `MAJOR.MINOR`

### Step 4 — `model.py` operations
- [x] `normalize_resource(raw) -> ResourceRecord` — ARN via `str.split(":", 5)` with arity and emptiness
      checks, **no regex** (PAT-8, NFR-S3); empty region segment → `"global"` (BR-03); raises
      `MalformedResource` with a category
- [x] `normalize_all(raw_items) -> NormalizationResult` — **total** (PAT-3, NFR-R2): skips and counts
      malformed items (BR-02), dedupes by ARN with last-wins into an insertion-ordered dict and counts
      collisions (BR-04)
- [x] `build_snapshot(result, collected_at, schema_version)` — rejects naive `collected_at`, negative
      counts, and duplicate ARNs; enforces **P8** with an explicit `raise InvalidSnapshot`, **never
      `assert`** (PAT-4)
- [x] `serialize_snapshot(s) -> bytes` — JSON, `sort_keys=True`, ISO-8601 UTC with explicit offset, UTF-8.
      Deterministic (P2). No `pickle`, no `yaml` (NFR-S4)
- [x] `deserialize_snapshot(b) -> Snapshot` — rejects malformed JSON, major-version mismatch
      (`IncompatibleSchema`), naive datetime; **ignores unknown top-level keys** (Q9 = A of Functional
      Design); re-enforces P8 by explicit raise (NFR-R3)
- [x] Story: **US-05** (`collected_at` carried), **US-10**

### Step 5 — `aggregation.py` (C-05)
- [x] `has_required_tag(record, key) -> bool` — **the single presence predicate** (BR-01): exact key match,
      value non-empty after `strip()`. Nothing else may re-derive this
- [x] `Group`, `GroupingResult`, `TagGapReport`, `IncompleteRecord`, `Freshness` (three-valued:
      `FRESH`/`STALE`/`INVALID`, PAT-5)
- [x] `group_by_tag(snapshot, tag_key)` — rejects a `tag_key` outside `REQUIRED_TAGS` (PAT-8); missing →
      `value=None` group; empty groups omitted; order **count desc, value asc, `None` last** (BR-05, Q8).
      Story: **US-03**
- [x] `classify_tag_gaps(snapshot, required=REQUIRED_TAGS)` — `missing_tags` in `REQUIRED_TAGS` order;
      partitions the records (BR-06). Story: **US-04**
- [x] `evaluate_freshness(collected_at, now, stale_after)` — **total**; `INVALID` check **first**, because
      a future timestamp would otherwise satisfy the FRESH comparison (BR-07, Q6). Story: **US-05**
- [x] `_reference_group_by_tag` — the naive quadratic oracle. **Written from BR-05's prose, not by copying
      `group_by_tag`** (NFR-T5, PAT-9). This is the one step whose correctness no tool can check
- [x] No `boto3`, no `os`, no clock read, no logging, no `print`, no `assert` anywhere in this file

### Step 6 — `core/__init__.py`: the public surface (PAT / Q4 = A)
- [x] Re-export and declare `__all__` exactly as listed in `nfr-design/logical-components.md` — entities,
      constants, both operation sets, **and all four error types** (Part A2 Interaction 4)
- [x] `_reference_group_by_tag` **excluded** — in the surface, P5 could compare an implementation against
      itself
- [x] Module docstring stating the boundary: no AWS, no clock, no I/O beneath this package

### Step 7 — `tests/conftest.py`: generators (NFR-T7)
- [x] Hypothesis strategies covering **all eight shapes** from `business-logic-model.md`: ARNs with an
      empty region segment · tag values empty/whitespace/normal · keys differing from required only by
      case · duplicate ARNs within one input · non-normalizable items mixed with valid ones ·
      `collected_at` before/equal/after `now` · zero-resource snapshots · snapshots carrying an
      unrecognized top-level key
- [x] **NFR-T7 is review-only and carries disproportionate weight** — RESILIENCY-14's satisfaction rests
      on these generators being real rather than nominal. Each strategy gets a docstring naming the shape
      it covers so a reviewer can check coverage against the list

### Step 8 — `tests/test_properties.py`: the ten properties (NFR-T1, PBT-01..10)
- [x] P1 round-trip (scoped to the same major version) · P2 determinism · P3 sum · P4 partition ·
      P5 oracle · P6 idempotence **including order** · P7 gap-iff · **P8 accounting identity** ·
      **P9 grouping/classification agreement** · **P10 freshness monotonic in `now`**
- [x] Property tests **only** in this file, mirroring `packages/builder-mcp/tests/test_properties.py`
- [x] Each docstring names its PBT rule category and the BR it verifies
- [x] Story: **US-10**

### Step 9 — `tests/test_examples.py` (NFR-T4, PBT-10)
- [x] Example-based tests complementing the properties: each `Freshness` value, each error type, the
      `"global"` region case, `no_data` vs zero-resources distinction at the model level
- [x] **NFR-P2**: the 10,000-record size check — **one deterministic example-based test, NOT a Hypothesis
      property** (Part A2 Interaction 5 of NFR Requirements), with `_reference_group_by_tag` **excluded**
- [x] `__eq__`/`__hash__` agreement test — the contract three properties depend on

### Step 10 — `tools/check` integration (TSD-7, NFR-T6, NFR-M1) — **MODIFIES A SHARED FILE**
- [x] Add a `==> dashboard tests` block **mirroring the existing `builder-mcp` block exactly**: run from
      the package directory (pytest resolves `testpaths` against its own rootdir) and rely on
      `.python-version`. Copying the known-green shape matters more than usual, because this cannot be run
      here
- [x] Add a `==> dashboard core boundary` grep failing on any of `boto3`, `botocore`, `import os`,
      `os.environ`, `datetime.now(`, `utcnow(`, `time.time(`, `logging`, `print(`, `assert `, `pickle`,
      `yaml` under `src/dashboard/core/`
- [x] Add the mypy strict step scoped to `dashboard.core`
- [x] **Do not touch** the source stage, artifact handling, role assumptions, or the digest export
      (`CLAUDE.md`). Only additive blocks
- [x] Preserve the LF-not-CRLF behaviour of `validate_stacks.py --list` — do not restructure that branch

### Step 11 — Repurpose the stray template (FR-6, C-08)
- [x] `blueprints/dashboard/infra/hello-world.yml` → renamed and rewritten as the deployment marker:
      `cornell:blueprint` corrected from `hello-world` to `dashboard`, description rewritten,
      `cornell:blueprint-version` reset, resources renamed out of the `hello-world` namespace
- [x] **Modify in place / `git mv`; never leave a copy alongside** (brownfield rule, Step 12 verification)
- [x] **Not registered in `pipeline/stacks.yml` in this step.** Registration requires a matching
      `pipeline.yml` action or the stack deploys nothing while reporting success — and that action is
      **U-02's** Infrastructure Design work. Registering now would make `validate_stacks.py` fail in the
      direction it is designed to catch
- [x] `AWS::SSM::Parameter` takes `Tags` as a **map**, not a list (`CLAUDE.md` gotcha)

### Step 12 — Documentation
- [x] `aidlc-docs/construction/u-01-domain-core/code/implementation-summary.md` — what was generated,
      requirement/story traceability, and every deviation
- [x] `blueprints/dashboard/README.md` — what the blueprint is, that it is **incomplete** (U-02 unbuilt),
      and its UI-contract conformance position pointing at `docs/design-language.md`

### Step 13 — Validation and honest reporting
- [x] Confirm no file was created under `aidlc-docs/` that should be application code, and vice versa
- [x] Confirm no duplicate files (`*_new.py`, `*_modified.py`) — brownfield rule
- [x] Confirm the boundary greps would pass by reading the code, since they cannot be run
- [x] **State plainly which checks ran and which did not.** `uv`, `terraform`, `pytest`, `mypy` and
      `cfn-lint` are all unavailable here, so **no test, type check, or lint will have been executed**.
      The ten properties will be *written*, not *passing*
- [x] Report every deviation from this plan

---

## Story traceability

| Story | Steps | Verified by |
|---|---|---|
| **US-03** group by deployment / owner / blueprint | 5 | P3, P4, P5, P6, P9 |
| **US-04** spot resources missing required tags | 5 | P7, P9 |
| **US-05** know how fresh the data is | 4, 5 | P10, examples |
| **US-10** property-based test suite | 7, 8, 9 | the suite itself |

US-01, US-02, US-06..US-09, US-11..US-15 are **U-02's** and are not touched here. FR-6's marker (Step 11)
is U-02's story US-15, done here only because the stray file sits in this blueprint and leaving it
mislabelled is worse than repurposing it early.

---

## Mandated plan sections that do not apply

The rules list a fixed set of generation activities. Recording the inapplicable ones with reasons, rather
than emitting empty steps:

| Mandated activity | Why not |
|---|---|
| API Layer Generation / Testing / Summary | U-01 has no API. C-03 is U-02's. |
| Repository Layer Generation / Testing / Summary | U-01 persists nothing; it returns bytes. C-02 is U-02's. |
| Frontend Components Generation / Testing | C-06 is U-02's — and now also bound by `contracts/ui-design-language.md`, whose §2 accessibility rules have no exemption path. |
| Database Migration Scripts | No database anywhere in the design. |
| Deployment Artifacts Generation | U-01 has no deployable footprint (the reason Infrastructure Design was skipped). The Dockerfile and templates are U-02's. |
| `data-testid` automation attributes | No UI in this unit. Applies to U-02's C-06. |

---

## Known limitation, stated before you approve

**Nothing generated in Part 2 can be executed in this environment.** `uv`, `pytest`, `mypy`, `terraform`
and `cfn-lint` are all absent (§A1.6), so:

- `uv.lock` will not exist until someone runs `uv` (Step 1)
- the ten properties will be **written, not verified**
- the mypy strict config will be **unchecked**
- the `tools/check` blocks will be **untested additions to a shared file every contributor runs**

That last one is the real risk, and it is why Step 10 copies the known-green `builder-mcp` block shape
rather than inventing an invocation. **Build and Test is the stage where this actually gets verified**, and
it will need a machine with those tools.

Approving this plan approves generating code under those conditions.
