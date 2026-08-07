# Build and Test Summary

**Phase**: CONSTRUCTION → Build and Test
**Date**: 2026-08-03 (U-01); **2026-08-04 (U-02 — see the U-02 section at the end)**
**Scope**: U-01 Domain Core **and** U-02 Dashboard Platform. The U-01 sections below stand as written;
U-02 is appended at the end (`## U-02 Dashboard Platform — Build and Test`).

---

## Headline: everything Code Generation could not verify has now been run

Code Generation closed with an explicit caveat — the ten properties were *written but never executed
as properties*, because `uv`, `pytest`, `mypy` and Hypothesis were absent. That caveat is now
**discharged for U-01**.

`pip` and `venv` were available, and U-01 has **no runtime dependencies**, so a throwaway virtualenv
was enough to install `pytest`, `hypothesis` and `mypy` and run the real suite. No repo file was
touched to make that work.

| Check | Result |
|---|---|
| **Property + example tests** | **60 passed** — 17 property, 43 example |
| **Hypothesis examples per property** | **100**, `deadline=None`, profile confirmed loaded |
| **mypy** (strict over `dashboard.core`) | **clean**, 8 source files, **zero `# type: ignore`** |
| **Domain-core boundary grep** | **clean** |
| **Registry consistency** | no orphans, none registered-but-missing |
| **NFR-P2 complexity ceiling** | 10,000 records grouped + classified in **~0.013 s** (bound: 10 s) |
| **Mutation testing** | **9 of 9 mutants killed** after one fix — see below |
| **`tools/check` end to end** | ✅ **PASSES** — `uv` and `terraform` installed 2026-08-03 |
| **`cfn-lint` on `dashboard-marker.yml`** | ✅ **clean** |
| **`uv.lock`** | ✅ generated and committed |

---

## Three defects found by running things

Each was invisible to inspection and would have shipped.

### 1. The Hypothesis configuration did nothing

`pyproject.toml` carried a `[tool.hypothesis]` table setting `max_examples = 100`. **Hypothesis has no
pyproject config source**, so it was read by nobody. Asked the library which profile it was actually
using and got `default`.

The *behaviour* was correct only because Hypothesis's own default happens to be 100. NFR-T2 was
satisfied by coincidence, and would have drifted silently if that default ever changed.

**Fixed**: profile registered in `tests/conftest.py` the way `packages/builder-mcp` does it, with
`deadline=None` added — a per-example wall-clock deadline flakes on shared CI, and a flaky gate teaches
people to retry rather than look. Verified the profile is now genuinely loaded.

### 2. `mypy>=1.10` resolved to 2.3, which changed what "unconfigured" means

mypy 2.0 turned `disallow_untyped_defs` **on by default**. So the floor `>=1.10` spanned a major
behavioural change, and 37 errors appeared in `tests/` — annotation-completeness checks over test
functions that NFR-M3 had explicitly scoped *out* of strict mode.

**Fixed**: pinned `mypy>=2,<3` with the reason recorded, and added an override relaxing annotation
completeness for the three test modules. `dashboard.core` stays strict and had **zero errors from the
first run** — NFR-M2 satisfied without a single `# type: ignore`.

Adding `-> None` to 37 test functions would have documented nothing and diluted the signal from the
package where strictness actually pays.

### 3. A missing annotation, and a `draw()` in the wrong place

mypy flagged a confusing `arg-type` error on a `draw(st.booleans())` several lines from its real cause.
Bisected with minimal reproductions:

- **Root cause**: `malformed_raw_items = st.one_of(st.just({}), ...)` was uninferrable — `{}` gives no
  key or value type — so the name was unsolved and the ambiguity propagated. Annotated it.
- **Second cause**: `if items and draw(st.booleans()):`. mypy cannot solve the generic protocol call
  in a short-circuiting `and`.

The fix for the second — hoisting both booleans into named locals — is right on an **independent and
more important ground**: under short-circuiting, `draw()` is *never called* when `items` is empty, so
the draw sequence's shape varied with earlier values. Hypothesis shrinks by simplifying the underlying
choice sequence, and a sequence whose shape moves gives the shrinker less to work with. **The type
error was a symptom of a real test-quality bug.**

---

## Mutation testing: 9 of 9

Properties that cannot fail are worse than no properties, so each business rule was deliberately broken
to confirm something catches it.

| Mutation | Caught by |
|---|---|
| BR-01 accept empty tag values | 3 tests |
| BR-05 invert group ordering | 2 tests |
| BR-05 drop the missing group entirely | 7 tests |
| BR-06 never report a gap | 3 tests |
| BR-07 check FRESH before INVALID | 3 tests |
| BR-04 stop counting duplicates | 3 tests |
| BR-03 reintroduce the log-group separator bug | 2 tests |
| BR-02 skip malformed items without counting | 3 tests |
| **BR-08 remove `sort_keys=True`** | **nothing — initially** |

**The survivor was a real gap in P2.** Its assertions serialized the *same object* twice, which a
Python dict satisfies without sorting. The property's actual claim is that **equal** snapshots produce
identical bytes. Added a second arm building an equal twin with tag insertion order reversed; the
mutation is now caught. Mutation score **9/9**.

Two side benefits worth recording:

- **P5's independence now has evidence, not just assurance.** Breaking `group_by_tag`'s ordering made
  P5 fail — which an oracle copied from the implementation could not do. NFR-T5 remains review-only in
  principle, but it is no longer unevidenced.
- **The BR-03 row is the bug found during Code Generation.** Re-breaking it confirms the regression
  test guards it.

### A harness failure worth recording

The first mutation run reported "NOTHING FAILED" for all nine. That was **my harness, not the tests**:
it used `timeout`, which macOS does not ship, so every command failed and produced no output to grep. A
green-looking sweep that had actually executed nothing.

Also, `cp` is aliased to prompt interactively here, so a restore step hung and left `aggregation.py`
mutated mid-run. Recovered with `git checkout --`, then verified the working tree matched HEAD before
continuing. Recorded because "the tests all passed" and "the test command never ran" look identical
from a distance, and the second was true twice in ten minutes.

---

## Mandated test types not applicable to U-01

| Instruction file | Status |
|---|---|
| `build-instructions.md` | ✅ written |
| `unit-test-instructions.md` | ✅ written |
| `integration-test-instructions.md` | **N/A** — U-01 integrates with nothing. Its dependency row is empty; it is called in-process and calls nothing. The U-01↔U-02 seam is a Python import with no transport, so there is nothing to stand up. |
| `performance-test-instructions.md` | **N/A as a load test** — U-01 has no endpoint, no concurrency, and no throughput dimension. Its only performance requirement (NFR-P1/P2, algorithmic complexity) is covered by an example-based test inside the unit suite. Response-time and virtual-user targets belong to U-02's C-03. |
| `contract-test-instructions.md` | **N/A for now** — the contract is `__all__`, and its only consumer is U-02, which does not exist. Becomes applicable at U-02's Build and Test, where the meaningful test is that U-02 imports nothing outside `__all__`. |
| `security-test-instructions.md` | **Covered, not separate** — U-01's security requirements are the boundary grep (NFR-M1, NFR-S4, NFR-S6, in `tools/check`) and the no-leak assertion (NFR-S1, in `test_examples.py`, checking no ARN or tag value appears in an exception). Both run in the normal gate. SECURITY-01/-02/-06/-07 are U-02's. |
| `e2e-task-instructions.md` | **N/A** — nothing is deployed. Requires U-02 and a stack. |

Recorded with reasons rather than emitted as templates full of `[X]` placeholders, which would imply
coverage that does not exist.

---

## Requirement verification status

| Requirement | Status |
|---|---|
| PBT-01..10 (all ten properties) | ✅ **executed**, 100 examples each |
| NFR-T1 properties implemented | ✅ |
| NFR-T2 `max_examples=100` | ✅ now genuinely applied (was decorative) |
| NFR-T3 shrinking/seed not disabled | ✅ |
| NFR-T4 example tests complement | ✅ 43 |
| NFR-T5 oracle independent | ⚠️ review-only — now **evidenced** by mutation testing |
| NFR-T6 runs in `tools/check` | ⚠️ block added, `tools/check` **not yet run end to end** |
| NFR-T7 eight generator shapes | ⚠️ review-only, all eight named in `conftest.py` |
| NFR-M1 boundary | ✅ grep clean |
| NFR-M2 mypy strict, no ignores | ✅ zero errors, zero ignores |
| NFR-M5 stdlib-only runtime | ✅ |
| NFR-P1/P2 complexity | ✅ 10k in ~0.013 s |
| NFR-R1/R2/R3 totality, P8 on read | ✅ |
| NFR-S1..S6 | ✅ |
| RESILIENCY-14 | ✅ satisfied by the executed suite |

---

## Update — the three outstanding items are closed

`uv` 0.12.1 and Terraform 1.15.8 were installed on 2026-08-03, and **`tools/check` ran end to end for
the first time in this blueprint's history. Every check passed:**

```
==> stack registry      9 template(s) registered and present
==> cfn-lint            clean          <- first lint of dashboard-marker.yml
==> builder-mcp tests   77 passed
==> dashboard tests     60 passed
==> dashboard core boundary  clean     <- the new grep, executed
==> dashboard types     clean          <- mypy via the real toolchain
==> terraform fmt       clean
==> terraform validate  clean
all checks passed
```

So the three additive blocks written blind against `tools/check` **work as written**, `dashboard-marker.yml`
**is valid CloudFormation**, and `uv.lock` now exists and is committed. Copying the known-green
`builder-mcp` invocation shape instead of inventing one is why the first execution passed rather than
needing debugging.

## Carried forward

1. **The test venv was `/tmp`-only.** Superseded — `uv` is now the real path.
2. **U-02 is entirely unbuilt** — and carries four cross-unit obligations, §6.4's site-sync ordering,
   RESILIENCY-04/-15, and the flip of `dashboard-marker` to `deployed_by: pipeline`.

*(All of item 2 is now done — see below.)*

---

# U-02 Dashboard Platform — Build and Test

**Date**: 2026-08-04. **Build: success. Tests: pass.** Every check the environment can run is green;
the residual is the four `deployed`-only requirements, unchanged.

## Build status

| Artifact | Tool | Status |
|---|---|---|
| Python package (`.[aws]`) | `uv` / hatchling | ✅ wheel builds; `uv.lock` regenerated with boto3, committed |
| Collector image (arm64) | `docker build --target collector` | ✅ builds; handler imports inside the image |
| API image (arm64) | `docker build --target api` | ✅ builds; handler imports inside the image |
| UI bundle | `npm run build` (tsc + vite) | ✅ builds; `dist/index.html` has **no inline script** (CSP precondition) |

## Test execution summary

| Category | Result |
|---|---|
| **Unit — Python** | **101 passed** in the `dashboard tests` block (60 U-01 + 41 U-02); 0 failures |
| **Unit — UI (vitest)** | **8 passed** — `StateBoundary` six states, incl. no_data vs no-resources distinct (US-06) |
| **Types — mypy** | **clean**, 33 source files; strict over `dashboard.core` only |
| **Core boundary grep** | **clean** — collector/api/shared may touch AWS; core still cannot |
| **Contract (U-01 ↔ U-02)** | **clean** — U-02 imports only `dashboard.core`'s `__all__`, no submodule imports |
| **Template invariants** | ✅ CSP no `unsafe-inline`/`eval`; `/api/*` no-cache + site cached; schedule `MaximumRetryAttempts: 0` |
| **cfn-lint** (all 11 templates) | **clean** — incl. the net-new CloudFront / WAFv2 / ApiGatewayV2 |
| **Stack registry + pipeline cross-check** | ✅ `dashboard-storage`, `dashboard`, `dashboard-marker` all registered `pipeline` with matching actions |
| **terraform fmt / validate** | clean |
| **`tools/check` end to end** | ✅ **exit 0 — all checks passed** |

## Mutation spot-check (U-02)

U-01 earned a full 9/9 sweep because it is pure. U-02 is mostly I/O orchestration, so the table-driven
tests are the primary control and mutation is a **spot-check that they bite**, not an exhaustive sweep.
Three of the highest-value invariants broken, each caught, files restored:

| Mutation | Caught by |
|---|---|
| Remove `INVALID`-before-stale early return (future timestamp → 200 ok) | `test_invalid_future_timestamp_is_503_not_ok` |
| Collapse `no_data` into `ok` (US-06 distinction lost) | `test_api_states` |
| Page-limit `break` instead of `raise` (CR-01 silent truncation) | `test_page_limit_breach_raises_not_truncates` |

## Mandated test types — dispositions for U-02

| File | Status |
|---|---|
| `build-instructions.md` | ✅ updated with the two image builds + UI build |
| `unit-test-instructions.md` | ✅ updated with the U-02 suite + mutation evidence |
| `integration-test-instructions.md` | ✅ **written** — seam tests (stubbed AWS) run now; the real CloudFront→API→S3 chain is deployed-only |
| `contract-test-instructions.md` | ✅ **written and run** — the `__all__` import boundary is clean |
| `security-test-instructions.md` | ✅ **written** — no-leak, generic-503, closed routes, CSP, TLS-only, pinning all in the gate; SEC-7 WAF-admits is deployed-only |
| `performance-test-instructions.md` | **N/A as a load test** — no load harness without a deploy. P-1/P-3 (collector bounds) are unit-tested; P-2/P-4 (API latency, cold start) and P-6 (cache) are deployed-only |
| `e2e-test-instructions.md` | **N/A** — requires a deployed stack behind CloudFront/WAF |

## Overall status

- **Build**: success
- **All runnable tests**: pass
- **Ready for Operations**: **conditionally** — everything verifiable without AWS is green; the four
  `deployed`-only requirements (SEC-7, A-4, P-6, R-8) close only on a merge to `main`, which deploys to
  the shared account. That asymmetry is a property of the unit (most of it is CloudFormation), stated
  at NFR Design §9 and not smoothed over here.

## The honest gap, restated

U-01 finished with 60 executed tests and 9/9 mutation with no deploy, because it is pure. U-02 cannot
reach that bar without a running stack: `cfn-lint` proves a template is *valid*, not that a WAF admits
the right people or a cache policy is the right way round. The first `Environment=test` deploy — reading
CloudWatch logs, the snapshot object, and the dashboard from an allowlisted IP — is what closes it.
