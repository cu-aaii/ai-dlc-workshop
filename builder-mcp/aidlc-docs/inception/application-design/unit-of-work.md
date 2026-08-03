# Units of Work — builder-mcp (Gate 3: Application Design + Units Generation)

Closed 2026-08-04. Decomposition **verified by import analysis** (side-chat session, pasted
into the main session by Tim): no unit module imports another unit module — `catalog`,
`github_ops`, `aws_ops`, `patching`, `spec_export` are mutually invisible and meet only in
`server.py`. Empirical confirmation: six subagents edited this codebase concurrently with
zero cross-unit conflicts. Ownership contract: SPEC C8.

**Priority (mob):** U1 and U2 are **critical**; U3 is next. U4/U5 follow.

## ⚠️ UOW-0 — land FIRST, before anyone adopts a unit

Split `server.py` (519 lines, all eight `@mcp.tool()` functions) into per-unit tool
modules: `tools/catalog_tools.py`, `tools/deployment_write_tools.py`,
`tools/deployment_read_tools.py`, `tools/spec_tools.py`, each registering against the
shared `mcp` instance; `server.py` keeps construction, `_guarded`, and `main()`.
Mechanical, ~1 hour, no behavior change, tests unchanged. **Owner: U5. Without this, five
owners conflict in one file forever.**

## The five units

### U1 · Catalog & Search — **CRITICAL**
`catalog.py` + the C1 manifest contract · tool `blueprint_search` · ST-01–04, ST-24
**Next steps:** private-repo catalog (unauthenticated GitHub API breaks at 60 req/hr and
dies entirely once the catalog goes private) · parameter-aware cost estimate (GAP-02) ·
fix empty-query ranking (scores by phrase count, not relevance — PBT finding) · fix
`validate_inputs` crash on scalar input specs (PBT finding; matters once authors
contribute manifests).
**Fit:** anyone comfortable with YAML contracts — cross-team-facing.

### U2 · Deployment Lifecycle — **CRITICAL · highest risk**
`github_ops.py` + `patching.py` · tools `deployment_create/update/delete` ·
ST-05, 07–09, 11, 22, 28
**Next steps:** GitHub App replacing the org PAT (D3 — biggest single piece of work) ·
security F2 (no object-level authz; any token holder can act as any NetID — entangled
with Entra being app identity) · automate orphaned-repo cleanup (currently reported, not
fixed) · exercise the deregistration path beyond dry-run.
**Fit:** most senior available — this unit holds the write credential; the governance
invariants live or die here.

### U3 · Operations & Observation — top priority after U1/U2
`aws_ops.py` · tools `deployment_read/health/restart` · ST-14–21
**Next steps:** `deployment_list` (GAP-01 — the only Not-served story with no workaround;
inventory is impossible today) · restart cap of 3 + 30-min time box (needs state the
stateless server doesn't keep — this unit's design question) · observability: metrics,
one alarm, a synthetic canary · in-memory AWS fakes for property testing (least-covered
unit).
**Fit:** someone with AWS access (**Jai**) — needs live AWS to progress.

### U4 · Spec & Handoff
`spec_export.py` · tool `spec_export` · ST-12, 26, 27
**Next steps:** real offboarding-audience content (GAP-07 — renders the common body only)
· have an actual reviewer confirm the security audience is usable at the gate.
**Fit:** newcomer — pure functions, no external systems, fast feedback.

### U5 · Platform Shell
`server.py`, `infra/`, `Dockerfile`, `deploy/`, pipeline wiring · composes everything ·
ST-06, 10, 13 + all NFRs
**Next steps:** **UOW-0 first** · verify the Entra cutover on the live runtime · deferred
security items (rate limiting, alarms, SBOM) · owns C3/C4, so every new tool from U1–U4
lands through here.
**Fit:** whoever owns the deploy path; overlaps Track 0.

## Shared kernel — not a unit
`config.py`, `validation.py` (both stdlib-only): every unit imports them; `validation`
holds the path denylist and security invariants. **No single owner; change by agreement**
— treat like the frozen `blueprint.yaml`: name affected units in the PR description.

## Deliberately unassigned — assign explicitly, not by default
The demo (time-critical) · the cost spec · the end-to-end reliability test.

## Code organization (greenfield rule, this repo)
Units stay inside `builder-mcp/src/builder_mcp/` — one package, module-per-unit, tool
modules under `tools/` after UOW-0. No per-unit repos: the deploy path is a monorepo by
design.
