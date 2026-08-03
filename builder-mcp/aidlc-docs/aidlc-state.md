# AI-DLC State — builder-mcp (Track A: Cornell Builder)

**Workspace**: brownfield repo (deploy path exists; builder-mcp/ is greenfield)
**Docs root**: `builder-mcp/aidlc-docs/` — scoped under the component because six tracks
share this repo and a root-level `aidlc-docs/` would collide across teams.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Reverse Engineering — SKIPPED (deploy path already documented in CLAUDE.md / pipeline/README.md)
- [x] Requirements Analysis — answers received 2026-08-03; `requirements.md` generated
      (Q4 answered by assumption ⭐A — mob to confirm)
- [x] User Stories — Part 1 answered by mob; Part 2 generated: 28 stories / 4 personas /
      18 Served, 8 Partial, 2 Not served. **Approved by delegation 2026-08-04** (mob moved
      to unit adoption on the story map)
- [x] Workflow Planning — reconstructed retroactively in `inception/plans/execution-plan.md`
- [x] Application Design — **CLOSED 2026-08-04 (Gate 3)**: five-unit decomposition
      verified by import analysis (side-chat), ratified by the mob;
      `inception/application-design/unit-of-work.md` + dependency matrix
- [x] Units Generation — **CLOSED 2026-08-04 (Gate 3)**: U1–U5 + shared kernel + UOW-0;
      story map complete (28/28 assigned); ownership contract SPEC C8.
      **Priority: U1 & U2 critical, U3 next.** UOW-0 (server.py split) lands before adoption

### 🟢 CONSTRUCTION PHASE
- [x] Code Generation — server (seven tools), infra/builder-mcp.yml (AgentCore stack),
      Dockerfile, deploy + verify scripts
- [x] Build and Test — 22 tests green; HTTP smoke test green stateful AND stateless;
      linux/arm64 image builds; template lints clean
- [x] Spec-driven docs — SPEC.md (contracts C1–C7), PROJECT-KNOWLEDGE.md, deploy/HANDOFF.md

### 🟡 OPERATIONS PHASE
- [ ] Deploy — **handed off**: Marty deploys from his account/system using
      deploy/HANDOFF.md; this machine's job ended at "verified locally + on GitHub".
      Inbound auth is **Entra ID client-credentials** (productionizing question P2
      answered 2026-08-03 by platform-lead directive; Cognito removed — DECISION-20).
      New hand-created pre-flight: Azure app registration + two SSM parameters
      (`/entra/builder-mcp/*`) + `entra-client-secret` in Secrets Manager (see HANDOFF)
- [ ] Post-deploy verify — deploy/verify.py against the live runtime (Entra token flow)

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
