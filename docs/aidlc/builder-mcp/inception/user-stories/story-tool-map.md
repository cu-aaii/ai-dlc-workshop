# Story ↔ Tool Map — builder-mcp (Gate 2, Part 2)

Cross-check in both directions per the plan's Part B: every story maps to the tool(s)
that serve it, and **every tool must trace to at least one story** — a tool with no
story is a tool we should question. Stories in [stories.md](stories.md); personas in
[personas.md](personas.md).

Tool names use the noun_verb surface (C3 rename in flight). Legend: **S** = story
Served by this tool, **P** = tool partially serves the story, blank = no relation.

## Matrix (story × tool)

| Story | Persona(s) | blueprint_search | deployment_create | deployment_read | deployment_update | deployment_delete | deployment_restart | deployment_health | spec_export | Coverage |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| ST-01 Find a blueprint | Builder | S | | | | | | | | Served |
| ST-02 See blueprint details | Builder, Reviewer | S | | | | | | | | Served |
| ST-03 Be findable | Author | S | | | | | | | | Served |
| ST-04 Cost before commit | Builder, Operator | P | | | | | | | | Partial |
| ST-05 Validate first (dry run) | Builder | | S | | | | | | | Served |
| ST-06 Guided inputs | Builder | P | P | | | | | | | Partial |
| ST-07 No unowned deployment | Builder, Operator | | S | | | | | | | Served |
| ST-08 Create = repo + PR, never deploy | Builder | | S | | | | | | | Served |
| ST-09 Singleton protection | Builder, Reviewer | | S | | | | | | | Served |
| ST-10 Failures as narratives | Builder | S | S | S | S | S | S | S | S | Served |
| ST-11 Reviewable diff | Reviewer | | S | | | | | | | Served |
| ST-12 Security spec at the gate | Reviewer | | | | | | | | S | Served |
| ST-13 Tool can't skip the gate | Reviewer, Operator | S | S | S | S | S | S | S | S | Served |
| ST-14 Chain status view | Builder, Operator | | | S | | | | | | Served |
| ST-15 Know when it's green | Builder | | | P | | | | | | Partial |
| ST-16 Real health check | Builder, Operator | | | | | | | S | | Served |
| ST-17 Retry at current version | Builder | | | | | | S | | | Served |
| ST-18 Tags visible to inventory | Operator | | P | | | | | P | | Partial |
| ST-19 List all deployments | Operator, Builder | | | | | | | | | **Not served** |
| ST-20 Restart cap | Operator | | | | | | P | | | **Not served** |
| ST-21 Incident triage | Operator | | | S | | | | S | | Served |
| ST-22 Change via PR | Builder | | | | S | | | | | Served |
| ST-23 Release without breaking | Author | | P | | | | | | | Partial |
| ST-24 Contribute a blueprint | Author | P | | | | | | | | Partial |
| ST-25 Deliberate upgrade | Builder | | | | P | | | | | Partial |
| ST-26 Audience-rendered spec | Builder, Reviewer | | | | | | | | S | Served |
| ST-27 Offboarding package | Builder, Operator | | | | | | | | P | Partial |
| ST-28 Governed teardown | Builder, Operator | | | | | S | | | | Served |

Notes on the two surface-wide rows: ST-10 (error contract, NFR7) and ST-13 (governance
invariants, C3/C5) are properties every tool must hold, so they map to all eight — they
are the stories the invariant tests trace to.

## Reverse check — every tool traces to ≥ 1 story

| Tool | Serving stories (beyond the surface-wide ST-10/ST-13) | Verdict |
|---|---|---|
| `blueprint_search` | ST-01, ST-02, ST-03, ST-04, ST-06, ST-24 | Traced |
| `deployment_create` | ST-05, ST-07, ST-08, ST-09, ST-11, ST-18, ST-23 | Traced |
| `deployment_read` | ST-14, ST-15, ST-21 | Traced |
| `deployment_update` | ST-22, ST-25 | Traced |
| `deployment_delete` | ST-28 | Traced (new tool; one story today — watch that it grows a Reviewer story for the deregistration-PR shape, mirroring ST-11) |
| `deployment_restart` | ST-17, ST-20 | Traced |
| `deployment_health` | ST-16, ST-18, ST-21 | Traced |
| `spec_export` | ST-12, ST-26, ST-27 | Traced |

**Tools with no story: none.** The reverse check passes — no tool on the surface is
unjustified by a persona need.

## Unserved list

Stories no tool serves today (full gap detail + demo-blocking flags in the
[gap table](stories.md#gap-table-per-q-s4--b--q-s5--b)):

- **ST-19 — List all deployments** (Platform Operator; also Builders asking "what do I
  have?"). Would be a new `deployment_list` tool — a C3 contract change. Not
  demo-blocking → logged.
- **ST-20 — Restart cap** (Platform Operator). Agreed future guardrail on
  `deployment_restart` — cap of 3 per window plus a 30-minute time box per restart
  (mob, 2026-08-03); needs state the stateless server doesn't keep. Not
  demo-blocking → logged.

Demo-blocking gaps are operational, not tool gaps: GAP-D1 (org-scoped GitHub
credential — beats 3–4) and GAP-D2 (live AgentCore endpoint + OAuth, with the recording
as fallback — beat 1). Both must be resolved before the demo per Q-S5 = B.
