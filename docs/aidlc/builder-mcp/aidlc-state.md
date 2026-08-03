# AI-DLC State — builder-mcp (Track A: Cornell Builder)

**Workspace**: brownfield repo (deploy path exists; the builder-mcp package is greenfield)
**Docs root**: `docs/aidlc/builder-mcp/`. Originally `builder-mcp/aidlc-docs/`, scoped under
the component to keep six tracks from colliding; the monorepo restructure resolved that
differently — one `docs/aidlc/` with a subdirectory per track. The collision worry recorded
in [STAGE-GATES.md](STAGE-GATES.md) under Workspace Detection is settled.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Reverse Engineering — SKIPPED (deploy path already documented in CLAUDE.md / pipeline/README.md)
- [x] Requirements Analysis — answers received 2026-08-03; `requirements.md` generated
      (Q4 answered by assumption ⭐A — mob to confirm)
- [x] User Stories — Part 1 answered by mob (journey-based, 4 personas, G/W/T + checklist,
      whole-journey coverage, build demo-blocking gaps, PR-reviewer sign-off); Part 2
      generated: 28 stories / 4 personas / 18 Served, 8 Partial, 2 Not served.
      **Awaiting mob approval of generated stories** — approval opens GATE 3
- [x] Workflow Planning — reconstructed retroactively in `inception/plans/execution-plan.md`
- [ ] Application Design — **REOPENED.** Was never ratified; five modules were designed
      unilaterally → **GATE 3** (opens after Gate 2)
- [ ] Units Generation — **REOPENED.** "One unit" was walked into, not chosen; it is why no
      parallel work was possible → **GATE 3**

### 🟢 CONSTRUCTION PHASE
- [x] Code Generation — server (seven tools), infra/builder-mcp.yml (AgentCore stack),
      Dockerfile, deploy + verify scripts
- [x] Build and Test — 22 tests green; HTTP smoke test green stateful AND stateless;
      linux/arm64 image builds; template lints clean
- [x] Spec-driven docs — SPEC.md (contracts C1–C7), PROJECT-KNOWLEDGE.md, deploy/HANDOFF.md

### 🟡 OPERATIONS PHASE
- [ ] Deploy — **handed off**: Marty deploys from his account/system using
      deploy/HANDOFF.md; this machine's job ended at "verified locally + on GitHub"
- [ ] Post-deploy verify — deploy/verify.py against the live runtime

## Intent Analysis
- **Request type**: New project (component) inside existing repo
- **Scope**: Multiple components — MCP server, GitHub integration, pipeline integration, catalog
- **Complexity**: Complex (auth chain, governance gate, demo deadline Tue 2:00 PM)
- **Requirements depth**: Standard (comprehensive on auth/repo questions, minimal on settled decisions)

## Extension Configuration

| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | **Yes** | Gate 1, mob 2026-08-03 (late — compliance pass over existing code commissioned) |
| Resiliency Baseline | **Yes** | Gate 1, mob 2026-08-03 |
| Property-Based Testing | **Yes (full)** | Gate 1, mob 2026-08-03 |

All three enforced from 2026-08-03 onward as blocking constraints. Answered late — the
extensions were missed at workflow start; see
`inception/requirements/extension-opt-in-questions.md`.

## Open gates

See [STAGE-GATES.md](STAGE-GATES.md) for the full what-we-chose vs what-we-walked-into map.

| Gate | Stage | Status |
|---|---|---|
| 1 | Requirements Analysis — extension opt-ins | **OPEN** — awaiting answers |
| 2 | User Stories — Part 1 plan | **OPEN** — awaiting answers |
| 3 | Application Design → Units Generation | blocked on Gate 2 |
| 4 | NFR Requirements | blocked on Gate 3 |

## Decisions inherited from product proposal (not re-litigated here)
- D3: GitHub App holds git credentials; builders get no direct write access
- D4: Merge — and nothing else — triggers deployment
- D2: Whole catalog in model context for intent matching (fine below ~75 blueprints)
- Workshop simplification: one blueprint per request; composition is post-workshop
