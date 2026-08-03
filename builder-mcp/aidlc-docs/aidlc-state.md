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
- [x] User Stories — SKIPPED by mob decision ("go", one-day deadline); requirements.md
      carries the acceptance criteria
- [x] Workflow Planning — compressed: single unit (builder-mcp server), Construction now,
      AgentCore deployment by end of day
- [x] Application Design — folded into requirements FR1–FR8 tool surface
- [x] Units Generation — single unit: `builder-mcp`

### 🟢 CONSTRUCTION PHASE
- [x] Code Generation — IN PROGRESS: FastMCP server, seven tools (six + export_spec),
      streamable HTTP, stateless
- [ ] Build and Test — pytest suite must pass; local HTTP verified
- [ ] Deploy — Bedrock AgentCore, verified live tool call (end of day)

## Intent Analysis
- **Request type**: New project (component) inside existing repo
- **Scope**: Multiple components — MCP server, GitHub integration, pipeline integration, catalog
- **Complexity**: Complex (auth chain, governance gate, demo deadline Tue 2:00 PM)
- **Requirements depth**: Standard (comprehensive on auth/repo questions, minimal on settled decisions)

## Decisions inherited from product proposal (not re-litigated here)
- D3: GitHub App holds git credentials; builders get no direct write access
- D4: Merge — and nothing else — triggers deployment
- D2: Whole catalog in model context for intent matching (fine below ~75 blueprints)
- Workshop simplification: one blueprint per request; composition is post-workshop
