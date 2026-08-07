# Code Generation — U-02 Dashboard Platform — implementation summary

**Phase**: CONSTRUCTION → Code Generation, **Part 2 (Generation)**
**Date**: 2026-08-04
**Plan**: `construction/plans/u-02-dashboard-platform-code-generation-plan.md` (20 steps, all executed)

## Files created / modified (all application code at the workspace root, never `aidlc-docs/`)

**Created — Python (collector C-01, read API C-03, shared)**
- `src/dashboard/collector/{__init__,errors,config,tagging,handler}.py`
- `src/dashboard/api/{__init__,routing,loading,shaping,views,config,handler}.py`
- `src/dashboard/shared/{__init__,logging_json,emf}.py`
- `tests/test_collector_{pagination,config,deadline,logging,metrics}.py`
- `tests/test_api_{states,loading,routing,boundary}.py`, `tests/test_template_invariants.py`

**Created — UI (C-06)**
- `ui/{package.json,package-lock.json,vite.config.ts,tsconfig.json,index.html,.gitignore}`
- `ui/src/{main.tsx,App.tsx,api.ts,types.ts,format.ts,styles.css,test-setup.ts,vite-env.d.ts}`
- `ui/src/hooks/useView.ts`
- `ui/src/components/{Masthead,StatusStrip,ViewTabs,StateBoundary,ViewShell,InventoryView,GroupingView,TagGapView,StatusView}.tsx`
- `ui/src/components/__tests__/StateBoundary.test.tsx`
- `ui/src/assets/cornell-reduced-white.svg` (official asset, copied from `aisei-site` — never redrawn)

**Created — deployment artifacts**
- `Dockerfile` (targets `collector`, `api`; base pinned by digest)
- `infra/dashboard-storage.yml`, `infra/dashboard.yml`, `blueprint.yaml`

**Modified**
- `pyproject.toml` — `boto3` as an `[aws]` optional extra + dev; mypy overrides for boto3 (ignore
  missing stubs) and the U-02 test modules; `uv.lock` regenerated.
- `pipeline/pipeline.yml` — `SiteBuildProject` + role + log group; two arm64 Build actions
  (`DashboardCollectorContainer`, `DashboardApiContainer`); four BlueprintDeploy actions
  (`DashboardStorage`+`DashboardMarker` at RunOrder 1, `Dashboard`+`DashboardSiteSync` at RunOrder 2).
- `pipeline/stacks.yml` — added `dashboard-storage`, `dashboard` (`pipeline`); **flipped
  `dashboard-marker` `manual`→`pipeline`** (DR-02) in the same PR as its action.
- `README.md` — U-02 now built; operating notes (first-load-slow, partial-state, WAF-fails-closed, R-10 runbook).

`infra/dashboard-marker.yml` content is **unchanged** — only its registry entry flipped. No file was
duplicated; every "modified" is in place.

## Requirement / story traceability

| Surface | Requirements | Stories | Verified by |
|---|---|---|---|
| Collector C-01 | CR-01..06, S-1, R-1/R-3 | US-07 | `test_collector_*` (pagination breach, config, deadline, no-leak, EMF) |
| Read API C-03 | AR-01..08, P-2/P-4, R-2 | US-06 | `test_api_*` (six states, loading, route property, boundary) |
| Web UI C-06 | ER-04, contract §2/§3, FR-4 | US-01..06 | `StateBoundary.test.tsx` (six states, no-data vs no-resources distinct) |
| Edge C-07 | ER-01..05, SEC-2/7/11 | US-11..13 | `test_template_invariants` (CSP, /api/* no-cache) + cfn-lint |
| Marker C-08 | DR-01/02 | US-15 | registry flip + validate_stacks |
| Observability C-09 | R-3..R-8, OR-01/05/06 | US-14 | EMF test + template alarms |
| Supply chain | SECURITY-10, US-09 | US-09 | committed `uv.lock` + `package-lock.json` |

## Verification actually run (Step 20) — this environment HAD the tools

- **`tools/check` → exit 0, all checks passed**: cfn-lint clean on all 11 templates (incl. the
  net-new CloudFront/WAFv2/ApiGatewayV2 resources); **101 dashboard pytest** pass; core boundary grep
  clean; **mypy clean** (33 files); terraform fmt/validate clean; stack registry + pipeline-action
  cross-check pass (dashboard-storage/dashboard/dashboard-marker all wired).
- **UI**: `tsc --noEmit` clean; **8 vitest** pass; `npm run build` succeeds and the built
  `dist/index.html` contains **no inline `<script>`** (the CSP precondition — `modulePreload.polyfill=false` did its job).
- **Colour contrast**: every UI colour pair measured against its surface with the WCAG formula; all
  pass their threshold (text ≥4.5, graphics/borders/focus ≥3).

## Deviations and honest gaps

1. ~~**`docker build` NOT run**~~ — **RESOLVED 2026-08-04** once the Docker daemon came up. Both
   targets build for `linux/arm64`; `pip install .[aws]` resolves (boto3 1.43.63 pulled), the wheel
   builds, each image's `CMD` is the correct handler path (`dashboard.collector.handler.handler` /
   `dashboard.api.handler.handler`), and both handler modules **import cleanly inside the arm64
   image** with boto3 present. The pipeline's `ArmContainerBuildProject` still owns the real build at
   deploy; this confirms the Dockerfile before then.
2. **`log_skipped` logs reason codes + counts, not per-ARN** — the functional-design pseudocode showed
   `arn=<arn>` per skipped item, but U-01's `normalize_all` deliberately *discards* skipped ARNs (its
   no-leak design), so they are not available. Logged by reason code and count instead — the safe
   direction, and reason codes are enum values (`arn`/`tags`), never tag values.
3. **Bucket names carry a `-${AWS::AccountId}` suffix** for global uniqueness (matching the marker
   precedent), so the convention name is `${Application}-${Environment}-${DeploymentName}-{snapshot,site}-${AccountId}`.
   Both stacks and the site-sync reconstruct it identically.
4. **Grouping-vs-addendum divergence** — relayed in the README and `docs/design-language.md`, not
   resolved (another team's file). Q5 = A (text + single-accent bar) is more conservative than the
   addendum's two-accent + "Other".
5. **`tools/check` NOT extended with a UI build step** — the org allowed-actions policy and CI image
   make a node build in `tools/check` fragile; the UI build is exercised by the pipeline's
   `SiteBuildProject` instead. `tools/check` stays uv + terraform, as documented.

## The residual — `deployed`-only requirements (unchanged from NFR Design §9)

**SEC-7** (WAF admits the right people), **A-4** (real degrade-to-stale), **P-6** (cache behaviour),
**R-8** (metrics actually arrive) cannot be confirmed without a merge to `main`, which deploys to the
shared account. U-02 structurally cannot reach U-01's 60-tests / 9-of-9-mutation bar without a
deploy — most of it is CloudFormation, and cfn-lint checks a template is *valid*, not that a cache
policy is the right way round. Build & Test and the first deploy close this.
