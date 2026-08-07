# Code Generation Plan — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Code Generation, **Part 1 (Planning)**
**Date**: 2026-08-04
**Unit**: U-02 Dashboard Platform
**This plan is the single source of truth for Part 2.** Generation executes these steps in order and nothing else.

---

## Unit context

| | |
|---|---|
| **Owns** | C-01 collector, C-02 snapshot store (infra), C-03 read API, C-06 web UI, C-07 edge, C-08 marker (flip only), C-09 observability |
| **Depends on** | **U-01 `dashboard.core`** — in-process import into both images; nothing else |
| **Contract** | consumes U-01's `__all__`; produces the `/api/*` envelope (`frontend-components.md`) and the `contracts/ui-design-language.md` UI contract |
| **Runtime deps** | collector/api add **`boto3`**; UI adds React/Vite. **Core stays stdlib-only** — the `tools/check` boundary grep enforces it |
| **Verification** | table-driven state tests + two property tests + template-invariant tests (`business-logic-model.md` — deliberately **not** property tests over mocks) |

**Design inputs**: `functional-design/` (CR/SR/AR/ER/OR/DR rules, the six-state table, the UI component tree) ·
`nfr-requirements/` (49 requirements, TSD-8..TSD-15) · `nfr-design/` (the 6 patterns, 12 logical components) ·
`infrastructure-design/` (the two templates, the pipeline wiring, Q1–Q7).

**Project type**: brownfield repo, brownfield unit — `blueprints/dashboard/` already holds U-01's `src/dashboard/core/`,
`pyproject.toml`, `uv.lock`, tests, `docs/design-language.md`, and `infra/dashboard-marker.yml`. This stage **adds**
the collector/api/UI code and the two templates, **modifies** `pyproject.toml`, `uv.lock`, `README.md`,
`pipeline/pipeline.yml`, `pipeline/stacks.yml`, and `tools/check`, and **flips** the marker's `stacks.yml` entry.
No file is duplicated; every "modify" is in place (brownfield rule).

---

## Environment — materially different from U-01's generation

U-01 was generated with **no tools installed**; its plan's headline caveat was "nothing can be executed." That is no
longer true. Verified present: **`uv`, `terraform`, `node`, `npm`, `docker`**; `cfn-lint` arrives via `uv` inside
`tools/check`. So **Part 2 will actually run** `tools/check`, `npm run build`, and `docker build`, and report real
results — not "written, not verified." The honest residual is unchanged from `nfr-design-patterns.md` §9: the four
**`deployed`-only** requirements (SEC-7 WAF admits the right people, A-4 real degrade-to-stale, P-6 cache behaviour,
R-8 metrics arrive) cannot be confirmed without a merge to `main`, which deploys to the shared account. Build & Test
remains the formal gate.

---

## Code location (application code at the workspace root, never `aidlc-docs/`)

```
blueprints/dashboard/
  pyproject.toml                         MODIFY  (Step 1: boto3 optional dep + dev; mypy scope)
  uv.lock                                REGEN   (Step 1: uv add / uv lock)
  src/dashboard/
    shared/                              Step 3  logging_json.py, emf.py  (used by both handlers)
    collector/  __init__.py              Steps 2,4,5
       config.py errors.py tagging.py handler.py
    api/        __init__.py              Steps 7,8
       routing.py loading.py shaping.py handler.py
  tests/
    test_collector_*.py                  Step 6
    test_api_states.py test_api_*.py     Step 9
    test_template_invariants.py          Step 18  (CSP, /api/* no-cache — over the built template)
  ui/                                    Steps 11-13  (Vite + React + TS)
    package.json package-lock.json vite.config.ts tsconfig.json index.html
    src/{main.tsx,App.tsx,api.ts,types.ts,hooks/useView.ts,components/*}
    (vitest for StateBoundary six states + data-testid)
  Dockerfile                             Step 10  targets: collector, api  (arm64 python:3.13)
  infra/
    dashboard-storage.yml                Step 14  NEW
    dashboard.yml                        Step 15  NEW
    dashboard-marker.yml                 unchanged (only its stacks.yml entry flips, Step 17)
  blueprint.yaml                         Step 16  NEW  (manifest → dashboard.yml)
  README.md                              MODIFY  (Step 19)
pipeline/
  pipeline.yml                           MODIFY  (Step 17)  SHARED FILE
  stacks.yml                             MODIFY  (Step 17)
tools/check                              MODIFY  (Step 18)  SHARED FILE
```

Markdown summaries only under `aidlc-docs/construction/u-02-dashboard-platform/code/`.

---

## Steps

### Step 1 — Packaging: add boto3, keep core clean
- [x] `pyproject.toml`: add `[project.optional-dependencies] aws = ["boto3"]` — **not** a top-level `dependencies`
      entry, so U-01's wheel stays dependency-free (NFR-M5). Add `boto3` to the `dev` group so the handler tests can
      run (botocore's `Stubber`, stdlib to botocore — no `moto`).
- [x] Extend `[tool.mypy] files` to include the new packages; keep **strict scoped to `dashboard.core.*` only** (the
      existing pyproject note: strict over boto3 shapes produces noise that gets `# type: ignore`d). Add a
      `dashboard.collector.*` / `dashboard.api.*` real-errors-not-completeness override, mirroring the tests override.
- [x] Regenerate `uv.lock` with `uv lock` / `uv sync` (available now), commit it (US-09 / TSD-2 reproducibility).

### Step 2 — collector `config.py` + `errors.py`
- [x] `errors.py`: `CollectorFailure(CoreError-independent Exception)` carrying a **closed `StrEnum` reason**:
      `PAGE_LIMIT_EXCEEDED`, `UPSTREAM_TOO_SLOW`, `UPSTREAM_THROTTLED` (NFR §3 — three named bounds, no two share a
      code). Like U-01's errors: the reason is an enum, the message carries **no ARN or tag value**.
- [x] `config.py`: parse env once — `SNAPSHOT_BUCKET`, `SNAPSHOT_KEY`, `PAGE_LIMIT` (default 50), `DEADLINE_SAFETY_MS`
      (~20 000), `LOG_LEVEL`. The declarative `botocore.config.Config` (connect/read timeouts + `retries={"mode":
      "standard","max_attempts":N}`) lives here (NFR §1).

### Step 3 — shared observability (`src/dashboard/shared/`)
- [x] `logging_json.py`: `logging.getLogger()` + JSON formatter, level from `os.environ["LOG_LEVEL"]` — mirrors
      `course-chatbot/src/handler.py` exactly (NFR §4). No `aws-lambda-powertools`.
- [x] `emf.py`: emit the `_aws` EMF envelope as a log line (NFR §5) — no API call, no IAM. **Dimensions are counts and
      outcomes only; never a tag value** (CR-04 extends to dimensions).

### Step 4 — collector `tagging.py` (CR-01, CR-02, CR-03)
- [x] `collect_all_resources(client, page_limit, deadline_fn)` — the loop from `business-logic-model.md`: page-count
      guard → `PAGE_LIMIT_EXCEEDED`; **deadline guard at the top of each iteration** reading the remaining-time
      function → `UPSTREAM_TOO_SLOW`; `get_resources` behind the standard-retry client, exhaustion → `UPSTREAM_THROTTLED`.
      Delegates all parsing to U-01 `normalize_all` (**never truncates**, CR-01).

### Step 5 — collector `handler.py` (C-01)
- [x] `handler(event, context)`: read clock **exactly twice** (both here), `collect_all_resources` →
      `build_snapshot` (U-01) → `serialize_snapshot` → **one `PutObject`** (complete-or-fail, CR-05, no
      read-modify-write) → `log_skipped` (reason + ARN, **no tag value**, CR-04) → `emit_metrics` on success **and**
      failure. Failure path: log with reason, emit failure metric, **raise** — the previous snapshot survives (A-4),
      OR-01 alarms, the next tick retries (Q6). Deadline derived from `context.get_remaining_time_in_millis()` (NFR §2).

### Step 6 — collector tests
- [x] `test_collector_pagination.py` — stubbed pager: normal termination, **page-limit breach raises** (not truncate),
      one-page, empty.
- [x] `test_collector_config.py` — assert the client's `.meta.config` timeouts + retry mode (NFR §1, review-visible).
- [x] `test_collector_deadline.py` — a slow stubbed pager + a shrinking remaining-time stub → `UPSTREAM_TOO_SLOW`.
- [x] `test_collector_logging.py` — **`log_skipped` never emits a tag value** (the privacy test, analogue of U-01's
      no-leak test).
- [x] `test_collector_metrics.py` — the `_aws` EMF envelope shape on success and failure.

### Step 7 — api `routing.py` + `loading.py` + `shaping.py`
- [x] `routing.py`: the **closed five-route table** (AR-01) — `/api/inventory`, `/api/groups/{tag_key}`,
      `/api/tag-gaps`, `/api/status`, `/api/health`; `{tag_key}` validated against `REQUIRED_TAGS`; everything else 404
      **before any S3 read**. The API owns the `/api` prefix (Infra Part A2 finding 4 — CloudFront forwards verbatim).
- [x] `loading.py`: `load_current_snapshot` — **total**, classifies into `PRESENT` / `ABSENT` / `UNREADABLE` by
      catching `NoSuchKey`, `ClientError`, and (**by type**, U-01 PAT-7) `IncompatibleSchema` / `InvalidSnapshot` (AR-02).
- [x] `shaping.py`: `shape` maps the **six states** (AR-03) in the order from `business-logic-model.md` — `ABSENT`→200
      `no_data`; `UNREADABLE`→503; **`INVALID` checked before the stale/ok split**; `counts_of` **unconditional** on
      every data response (AR-05). `respond`, `health` (AR-08, static, no S3).

### Step 8 — api `handler.py` (C-03) — total by structure
- [x] `handler(event, context)`: route → (404 or health, no S3) → `load_current_snapshot` → `shape`. **One outer
      `try/except`** wrapping everything after the closed route table maps any escape to a **generic 503, no internals**
      (NFR §6, AR-06). Event access is **inside** the guard (the seam named in NFR §6).

### Step 9 — api tests
- [x] `test_api_states.py` — **the six-state table, all six rows, table-driven** (the highest-value tests in the unit);
      rows 3/4 (`ok` zero-resources vs `no_data`) asserted distinct (US-06).
- [x] `test_api_loading.py` — three states from three stubbed S3 failures.
- [x] `test_api_routing.py` — **property**: no input outside the table reaches a handler (closed allowlist).
- [x] `test_api_counts.py` — **property**: `counts` present in every non-health response (guards obligation 2).
- [x] `test_api_boundary.py` — a handler that raises still yields a generic 503 with no internals (NFR §6).

### Step 10 — `Dockerfile` (two targets)
- [x] Base `public.ecr.aws/lambda/python:3.13`, **digest-pinned** (`@sha256:…`, per `builder-mcp`), arm64. Two named
      targets **`collector`** and **`api`**, each `pip install .[aws]` into `${LAMBDA_TASK_ROOT}` and `CMD` its handler.
      `CONTAINER_TARGET`/`CONTAINER_CONTEXT` in the pipeline must match these names + this location. Consider the
      `add-container-build` skill as the reference for wiring.

### Step 11 — UI scaffold (Vite + React + TS)
- [x] `package.json` + committed **`package-lock.json`** (US-09 pinning), `vite.config.ts` with
      **`build.modulePreload.polyfill = false`** (frontend-components.md — the CSP-breaking inline script), `tsconfig.json`,
      `index.html` with **no inline script/style**. Palette tokens from `aisei-site` / the contract (no custom colours).

### Step 12 — UI components (C-06)
- [x] `App`, `Masthead` (Cornell logo, contract §3), `StatusStrip` (does **not** fetch), `ViewTabs` (real `<button>`s in
      `role="tablist"`), **`StateBoundary`** (the six states, one implementation), `InventoryView` (+ copy-URL, Q6),
      `GroupingView` (four-option key selector; **grouping identity in text not colour**, Q5=A; ordering from U-01, not
      re-sorted), `TagGapView`, `StatusView`; `useView` hook (one fetch per view), `api.ts`, `types.ts` (the `Envelope`).
- [x] `data-testid` per the naming list, incl. **separate** `state-boundary-no-data` vs `state-boundary-no-resources`.
- [x] Accessibility §2 (non-waivable): live regions (`role="status"`/`alert`), visible focus, real table semantics.
- [x] **Invoke the `cornell-ui-compliance` skill** during generation (it blocks non-compliant output).
- [x] Relay to the user the **Q5=A divergence** from `blueprints/dashboard/docs/design-language.md` (the team addendum
      specifies two-accent + "Other"; Q5=A is more conservative, not a contract violation) — that file is not ours to
      rewrite; the authors decide.

### Step 13 — UI tests
- [x] Vitest over `StateBoundary`: all six states render, and `no_data` vs `no_resources` are distinguishable by
      testid (US-06 assertable, not resting on a human noticing).

### Step 14 — `infra/dashboard-storage.yml` (stateful)
- [x] Snapshot + site buckets per `infrastructure-design.md` §2 (versioning, SSE, BPA, lifecycle TSD-13); snapshot
      TLS-only bucket policy. Four `cornell:*` tags as a **list**. Plain outputs, **no `Export:`**.

### Step 15 — `infra/dashboard.yml` (app)
- [x] Every resource in `infrastructure-design.md` §3: two `HasImage`-gated Lambdas (`CollectorImageUri`/`ApiImageUri`,
      sizing TSD-8, API reserved concurrency 10), two least-privilege key-scoped roles, log groups (30 d), EventBridge
      schedule (`MaximumRetryAttempts: 0`), HTTP API (throttle 20/40), CloudFront + OAC + **the site `BucketPolicy`
      here** (Q2), ResponseHeadersPolicy (the **exact CSP string**, Q7), WAF WebACL + **two IPSets** (Q5), alarms →
      **reconstructed notify-topic ARN** (Q4). Four `cornell:*` tags on every taggable resource. Consider the
      `add-blueprint` skill as the reference.

### Step 16 — `blueprint.yaml` manifest
- [x] Manifest → **`dashboard.yml`** (a registered template, same PR). Inputs: `owner_netid`, the WAF CIDR lists;
      `pipeline_parameters` incl. `SourceCommitId` + the image digests; **`singleton: false`** (marker note);
      `state: [derived]` for the snapshot; `data_classification`. Version in lockstep with `BlueprintVersion`.

### Step 17 — pipeline wiring + registry (SHARED `pipeline.yml`, `stacks.yml`)
- [x] `pipeline.yml`: add a **`SiteBuildProject`** (`node:24-alpine`, non-privileged); two **Build** actions
      (`DashboardCollectorContainer`, `DashboardApiContainer` on `ArmContainerBuildProject`, targets from Step 10); three
      **BlueprintDeploy** CFN actions — `DashboardStorage` (RunOrder 1), `DashboardMarker` (RunOrder 1),
      `Dashboard` (RunOrder 2, digests + CIDRs + LogLevel overrides); one **`DashboardSiteSync`** action (RunOrder 2,
      `npm build` + `s3 sync` **without `--delete`**). Every parameter passed explicitly. **Preserve the pipeline's
      shape** — only additive actions (`CLAUDE.md`).
- [x] `stacks.yml`: add `dashboard-storage` + `dashboard` (`deployed_by: pipeline`); **flip `dashboard-marker`
      `manual`→`pipeline`** (DR-02) — legal only because its BlueprintDeploy action lands in the **same PR**.

### Step 18 — `tools/check` + template-invariant tests (SHARED `tools/check`)
- [x] The new pytest files run under the existing `dashboard tests` block already (testpaths). Add
      `test_template_invariants.py`: **CSP contains no `unsafe-inline`/`unsafe-eval`**, and **`/api/*` is no-cache while
      the site default is cached** (the two template assertions from `business-logic-model.md` — silent when wrong).
- [x] Add a UI build/compliance step only if it can be made CI-safe (npm available locally, but the org allowed-actions
      policy and CI image matter — decide in Part 2; if unsafe for CI, leave the UI build to the pipeline `SiteBuildProject`
      and say so). **Do not touch** the source stage / artifact handling / digest export.

### Step 19 — Documentation
- [x] `README.md`: U-02 is now built — architecture, the first-load-is-slow note (TSD-9), the partial-state note
      (TSD-14), the R-10 runbook entries.
- [x] `aidlc-docs/construction/u-02-dashboard-platform/code/implementation-summary.md` — modified-vs-created files,
      requirement/story traceability, every deviation.

### Step 20 — Validation and honest reporting (now actually runnable)
- [x] Run **`tools/check`** and report real pass/fail (uv + terraform + cfn-lint all present).
- [x] Run **`npm run build`** in `ui/` and confirm the bundle emits no inline script (the CSP precondition).
- [x] Run **`docker build`** for both targets if feasible; report.
- [x] Confirm no duplicate files, no app code under `aidlc-docs/`, core boundary grep still clean.
- [x] **State plainly which checks ran and which did not**, and restate the four `deployed`-only requirements as the
      residual Build & Test / deploy must close.

---

## Story & requirement traceability

| Surface | Component | Requirements | Stories |
|---|---|---|---|
| Collector | C-01 | CR-01..06, S-1, R-1, R-3 | US-07 (scheduled, read-never-writes) |
| Snapshot store | C-02 | SR-01/02, D-1/2/7 | — |
| Read API | C-03 | AR-01..08, P-2/4, R-2 | US-06 (no_data vs empty) |
| Web UI | C-06 | ER-04, contract §2/§3, FR-4 | US-01..US-06 rendered (US-03/04/05 logic is U-01's) |
| Edge | C-07 | ER-01..05, SEC-2/7/11 | US-11..US-13 (allowlist/CSP/edge) |
| Marker flip | C-08 | DR-01/02 | US-15 |
| Observability | C-09 | R-3..R-8, OR-01/05/06 | US-14 |
| Supply chain | packaging/UI | SECURITY-10, US-09 | US-09 |

Exact story IDs are taken from the functional-design references; where a component renders a U-01 story the logic is
**not** re-implemented here (it is imported and property-tested in U-01).

---

## Decisions taken in this plan (redirect if you disagree — otherwise they stand)

1. **`boto3` as an `optional-dependencies` extra**, not a top-level dependency — keeps U-01's wheel dep-free while the
   images install `.[aws]`. (Alternative: top-level dep, simpler but couples core's wheel to boto3.)
2. **Shared `logging_json.py`/`emf.py` under `src/dashboard/shared/`** — one logging convention for both handlers.
3. **Table-driven + two property tests + template-invariant tests**, per `business-logic-model.md` — deliberately **no**
   property tests over mocked AWS (they would test the mocks).
4. **Skills invoked in Part 2**: `cornell-ui-compliance` (UI), `add-blueprint` / `add-container-build` (as references).
5. **The Q5=A vs team-addendum divergence is relayed, not resolved here** — the addendum is another team's file.

## Known limitations, stated before you approve
- The four **`deployed`-only** requirements (SEC-7, A-4, P-6, R-8) cannot be verified in Part 2 — only a shared-account
  merge closes them (`nfr-design-patterns.md` §9).
- Steps 17–18 **modify shared files** (`pipeline.yml`, `tools/check`) every track depends on; changes are additive and
  preserve pipeline shape, but a mistake here affects everyone — the reason `tools/check` and `cfn-lint` are run in Step 20.
- Approving this plan approves generating **all** of the above and running the Step 20 checks.
