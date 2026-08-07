# Unit Test Execution — U-01 Domain Core

**Phase**: CONSTRUCTION → Build and Test
**Date**: 2026-08-03
**Result on 2026-08-03: 60 passed** (17 property tests, 43 example-based), mypy clean, boundary clean.

## Run

```sh
tools/check                                   # everything, the way CI runs it
cd blueprints/dashboard && uv run pytest -q   # just this unit
```

Targeted:

```sh
uv run pytest tests/test_properties.py -q                        # the ten properties
uv run pytest tests/test_examples.py -q                          # example-based
uv run pytest tests/test_properties.py -q --hypothesis-show-statistics
uv run mypy                                                      # strict over dashboard.core
```

## What the suite is made of

| File | Tests | Purpose |
|---|---|---|
| `tests/conftest.py` | — | Hypothesis profile + generators for the eight adversarial shapes |
| `tests/test_properties.py` | **17** | The ten properties P1–P10, some with multiple arms |
| `tests/test_examples.py` | **43** | Concrete cases, the hash/eq contract, and the 10k complexity check |

Hypothesis runs **100 examples per property** with `deadline=None`, registered as a profile in
`conftest.py`. **Not** in `pyproject.toml` — Hypothesis has no pyproject config source, so a
`[tool.hypothesis]` table there is read by nobody. The first draft had one, and the cap it claimed to
set was being honoured only because it happens to equal Hypothesis's default.

Shrinking and seed reporting are left at Hypothesis defaults (PBT-08). A shrunk minimal
counterexample is most of the value; do not disable them.

## Property → rule map

| # | Property | Verifies |
|---|---|---|
| P1 | round-trip, incl. unknown-key tolerance | BR-08 |
| P2 | determinism — **two arms**, see below | BR-08 |
| P3 | group sizes sum to total | BR-05 |
| P4 | records partition; no empty group | BR-05 |
| P5 | matches the independent oracle | BR-05 |
| P6 | idempotent incl. order; ordering contract | BR-05 |
| P7 | gap flagged **iff** a required tag is absent | BR-06 |
| P8 | accounting identity; totality; survives serialization | BR-02, BR-04 |
| P9 | grouping and classification agree | BR-01 |
| P10 | three states correct; monotonic in `now` | BR-07 |

**P2 has two arms deliberately.** The first serializes one snapshot twice. That arm is *insufficient*:
mutation testing showed it passes even with `sort_keys=True` removed, because a Python dict already
iterates deterministically. The second arm builds an **equal but differently-constructed** twin, with
tag insertion order reversed, and only key-sorted output makes their bytes match. Keep both.

## Reading a failure

Hypothesis prints the **shrunk minimal** input plus a seed. Reproduce with:

```sh
uv run pytest tests/test_properties.py -q -p no:randomly --hypothesis-seed=<seed>
```

The two failures worth recognising on sight:

- **P5 fails** → `group_by_tag` and `_reference_group_by_tag` disagree. One is wrong; the oracle is
  the naive quadratic version, so it is usually the faster one at fault.
- **P9 fails** → grouping and gap classification have stopped agreeing, which means something
  re-derived tag presence instead of calling `has_required_tag`. That is the drift P9 exists to catch.

## The two checks no tool performs

Recorded because a reader should know exactly which lines rest on human attention.

**NFR-T5 — the oracle must stay independent.** `_reference_group_by_tag` was written from BR-05's
prose. If anyone rewrites it by copying `group_by_tag`, P5 becomes a tautology that passes forever
while asserting nothing, and **nothing will report it**. Mutation testing gives indirect evidence it
is currently independent: breaking `group_by_tag`'s ordering made P5 fail, which a copied oracle could
not do.

**NFR-T7 — the generators must cover the eight shapes.** RESILIENCY-14 is discharged by this suite, so
thin generators make a blocking rule hollow. `conftest.py` lists all eight and names which strategy
covers each, so the check is comparison against a list rather than trust.

---

# Unit Test Execution — U-02 Dashboard Platform

**Date**: 2026-08-04. **Result: 41 U-02 Python tests pass** (part of the 101 the `dashboard tests`
block reports: 60 U-01 + 41 U-02) **+ 8 UI vitest**; mypy clean over 33 files; core boundary clean.

## Run

```sh
tools/check                                        # everything, the way CI runs it
cd blueprints/dashboard && uv run pytest -q        # U-01 + U-02 Python
cd blueprints/dashboard/ui && npm ci && npm test   # UI (vitest)
```

Targeted:

```sh
uv run pytest tests/test_collector_*.py -q         # collector (C-01)
uv run pytest tests/test_api_*.py -q               # read API (C-03)
uv run pytest tests/test_template_invariants.py -q # CSP / cache / no-retry, over the template
```

## What the U-02 suite is made of

**Deliberately not property tests over mocks** (`business-logic-model.md`): U-02 is mostly I/O, so the
honest tests are table-driven state mappings, two genuine properties, and template assertions.

| File | Focus |
|---|---|
| `test_collector_pagination.py` | termination, one-page, empty, **page-limit breach raises (never truncate)** |
| `test_collector_config.py` | env parse; the `botocore.Config` timeouts + standard retries (CR-02) |
| `test_collector_deadline.py` | internal deadline → `UPSTREAM_TOO_SLOW`; ClientError/connection → `UPSTREAM_THROTTLED` |
| `test_collector_logging.py` | **no tag value ever reaches a log line** (CR-04, the no-leak test) |
| `test_collector_metrics.py` | the `_aws` EMF envelope shape on success and failure |
| `test_api_states.py` | **the six-state table, all rows**; rows 3/4 (empty vs no_data) asserted distinct; `counts` on every data view |
| `test_api_loading.py` | three load states from three stubbed S3 outcomes |
| `test_api_routing.py` | **property**: no input outside the five-route table resolves; invalid tag_key → 404 |
| `test_api_boundary.py` | a raising view still yields a generic 503; unknown route 404s without touching S3 |
| `test_template_invariants.py` | CSP has no `unsafe-inline`/`eval`; `/api/*` no-cache + site cached; schedule `MaximumRetryAttempts: 0` |

## The two genuine properties (not over mocks)

- **`route` is a closed allowlist** — `test_api_routing` drives arbitrary Hypothesis strings and asserts
  none outside the table reaches a view. A real property over a real closed set.
- **`counts` on every non-health response** — guards obligation 2 against a future slimming.

## Mutation evidence (U-02)

Three of U-02's highest-value invariants were deliberately broken to confirm a test catches each
(files restored after):

| Mutation | Caught by |
|---|---|
| Remove the `INVALID`-before-stale early return (a future timestamp would read 200 ok) | `test_invalid_future_timestamp_is_503_not_ok` |
| Collapse `no_data` into `ok` (US-06: "never ran" would look like "found nothing") | `test_api_states` (rows 4 + distinctness) |
| Page-limit `break` instead of `raise` (CR-01: silent truncation) | `test_page_limit_breach_raises_not_truncates` |

All three caught. Not the exhaustive 9/9 sweep U-01 got — U-02's logic is mostly I/O orchestration, so
the table-driven tests are the primary control and these mutations spot-check that they bite.
