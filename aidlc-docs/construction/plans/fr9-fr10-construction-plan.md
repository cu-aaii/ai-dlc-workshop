# CONSTRUCTION Plan — FR-9 / FR-10 increment

**Date**: 2026-08-07
**Scope**: C-10…C-14 plus the C-02/C-03/C-06/C-09 extensions, across the two existing units.
**Inputs**: A2 (approved) → A3 (measured) → A4 (design); FR-9/FR-10 section of
`inception/application-design/`; stories US-16…US-25.

## Stage selection — what runs, what is collapsed, and why

Four of the seven CONSTRUCTION stages ran for U-01/U-02. Running all of them again for an increment
into existing units would re-derive artifacts that already exist and still bind. Collapsed stages are
recorded here so the decision is visible rather than silent (methodology: `workflow-changes.md` §2
requires stating impact; nothing below is skipped without a reason).

| Stage | Decision | Rationale |
|---|---|---|
| **Units Generation** | **COLLAPSED** | Application Design Q4 already assigned every new component to a unit (C-12/C-13/C-14-parser → U-01; C-10/C-11 → U-02). No new unit exists and no new dependency edge needs deriving — `component-dependency.md` already carries the matrix. Re-running it would produce a `unit-of-work.md` identical to the existing one plus five rows. |
| **Functional Design** | **RUNS** | The new business rules have **no home**: money arithmetic, rate derivation from two counters, the unattributed-group predicate, and the two opposite collector failure policies. This is the stage that stops them being invented during coding. |
| **NFR Requirements** | **COLLAPSED** | NFR-T1…T8 were written at requirements level in A2/A3 with the same specificity U-02's 49 NFRs had, and each is already traced in the Application Design coverage table. Re-deriving would duplicate, and duplication is where two versions drift. |
| **NFR Design** | **FOLDED** into Functional + Infrastructure Design | U-02's six NFR patterns (declarative `botocore` retry/timeout, deadline from `get_remaining_time_in_millis()`, stdlib JSON logging, EMF metrics, one outer error boundary, `MaximumRetryAttempts: 0`) are **inherited unchanged** by C-10/C-11 — they are the same shape of component. The genuinely new decisions are few (CE call budget, `Decimal` money, per-section degradation) and are recorded in the two design docs rather than a third. |
| **Infrastructure Design** | **RUNS** | Genuinely new: two Lambdas, two roles, two schedules, three S3 keys with per-key IAM, the SSM rate parameter, C-14's build step, pipeline actions, and which template they land in. |
| **Code Generation** | **RUNS** | The first stage in this whole pass that writes code. |
| **Build and Test** | **RUNS** | The formal gate. `tools/check` plus the U-01 property/mutation discipline over C-12/C-13. |

## Steps

### Functional Design
- [x] F1 — `functional-design/business-rules.md`: COST-*, TEL-*, CAT-* rules
- [x] F2 — `functional-design/business-logic-model.md`: the algorithms + property targets
- [x] F3 — Confirm every rule traces to an FR-9/FR-10 clause or a US-16…US-25 criterion

### Infrastructure Design
- [x] I1 — `infrastructure-design/infrastructure-design.md`: resources, roles, schedules, template placement
- [x] I2 — Pipeline wiring: C-14 build step + the one new parameter (**no new image targets or Build actions** — see the Q3 refinement)
- [x] I3 — NFR-T8 cost budget: enumerate the increment's own recurring cost against the measured $9.02/mo

### Code Generation
- [ ] G1 — U-01 pure: `core/money.py` (C-12), `core/telemetry.py` (C-13), `core/catalog.py` (C-14 parser)
- [ ] G2 — U-01 tests: property tests for the money arithmetic and rate derivation
- [ ] G3 — U-02: `cost/` collector (C-10), `telemetry/` collector (C-11)
- [ ] G4 — U-02: C-03 routes, loading, shaping, views
- [ ] G5 — U-02 tests: collector + API + template invariants
- [ ] G6 — UI: Financial + Adoption tabs reusing `StateBoundary`
- [ ] G7 — Templates (2 Lambdas via `ImageConfig.Command`, 2 roles, 2 schedules, SSM param); `pipeline.yml` (C-14 build step + 1 parameter) + comment condensation for headroom; `stacks.yml` unchanged (no new template)
- [ ] G8 — `pyproject.toml` scope updates; mypy overrides for new test files

### Build and Test
- [ ] T1 — `tools/check` green (incl. the core-boundary grep over the new pure modules)
- [ ] T2 — UI build + vitest; no inline script
- [ ] T3 — Targeted mutation spot-check on the money arithmetic and the unattributed predicate
- [ ] T4 — Update build-and-test artifacts; present at the gate

## Constraints that bind this increment

- **`tools/check`'s core-boundary grep** forbids in `dashboard/core`: `os`, `logging`, `boto3`,
  `botocore`, `pickle`, `yaml`, `os.environ`, `datetime.now(`, `.utcnow(`, `time.time(`, bare `assert`,
  `print(`. C-12/C-13/C-14-parser must be clean against it. `decimal` is stdlib and permitted.
- **`pipeline/pipeline.yml` is at 50,966 bytes against a 51,200-byte hard limit** — **234 bytes of
  headroom** (measured, not estimated). This constraint changed the design; see the Q3 refinement below.
  Any comment prose that must go should be **condensed, never deleted with its rationale** — the
  check's own guidance.
- **U-01's wheel stays dependency-free.** New pure code adds no dependency; `boto3` remains the `aws`
  extra only.
- **No merge to `main`.** CONSTRUCTION ends at Build and Test, as it did for U-01/U-02.

---

## Q3 refinement, found by checking the size constraint (2026-08-07)

Application Design Q3 = B said *"reuse the collector image: a **new Dockerfile target** plus handler."*
Measuring `pipeline.yml`'s headroom (234 bytes) forced a closer look, and there is a strictly better way
to honour the same intent.

**The existing Lambdas bake their entrypoint into the image**: `Dockerfile` has `FROM base AS collector`
/ `CMD ["dashboard.collector.handler.handler"]`, and `dashboard.yml` supplies only
`Code.ImageUri: !Ref CollectorImageUri`. But the `base` stage runs `pip install .[aws]`, so **every
module in the package is already in the image** — the two targets differ *only* by `CMD`.

**Refinement: no new Dockerfile targets and no new Build actions.** Add the two Lambda resources
pointing at the **same** `CollectorImageUri`, overriding the entrypoint per function:

```yaml
Code:
  ImageUri: !Ref 'CollectorImageUri'
ImageConfig:
  Command: ['dashboard.cost.handler.handler']      # and .telemetry.handler.handler
```

Why this is better, not merely smaller:

| | Q3 = B as written | Refined |
|---|---|---|
| Dockerfile targets | 4 | **2, unchanged** |
| `pipeline.yml` Build actions | +2 | **0** |
| Image digest parameters to thread | +2 | **0** |
| Images built per pipeline run | 4 | **2** — less build time, less ECR storage |
| Versions of the same code in flight | 4 images to keep in step | **1 image, 4 entrypoints** |

That last row is the real argument: four images built from one source tree can drift if a build is
retried, whereas one digest deployed to four functions **cannot**. `ImageConfig.Command` is AWS's
intended mechanism for exactly this.

**Remaining `pipeline.yml` change** is therefore one parameter (the cost cadence, which FR-10.4.3
requires be a parameter) rather than two Build actions plus two digests. The SSM rate-table path is
derived with `!Sub` from `Application`/`Environment`, so it needs no parameter at all; the telemetry
collector reuses the existing hourly schedule parameter.

Still planned: condense some comment prose anyway. Shipping 40 bytes under a hard limit is fragile,
and the next person to add a line would hit it.

**Does not change**: Q3's intent (one image, separate functions, separate roles, separate schedules,
independent failure domains) or any least-privilege property — each function still gets its own role.
