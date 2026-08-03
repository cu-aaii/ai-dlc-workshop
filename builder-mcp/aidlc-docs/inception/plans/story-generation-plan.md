# GATE 2 — Story Generation Plan (User Stories, Part 1)

Assessment: [user-stories-assessment.md](user-stories-assessment.md) — **execute**, four High
Priority indicators met.

Fill in the `[Answer]:` tags below. ⭐ marks my recommendation with its reasoning; the mob
decides. Six questions, all A/B/C — this is deliberately answerable in one sitting.

---

## Part A — Questions

### Q-S1 · Story breakdown approach

The method offers five. What we have today maps to none of them — the tool list came from a
brainstorm.

- A) **User Journey-Based** — stories follow the builder's path: *discover → configure →
  create → review → watch it deploy → operate → hand off*. Surfaces gaps between steps.
- B) ⭐ **Persona-Based** — group by who needs what (builder / reviewer / operator). Best at
  catching the tools we're missing, because each persona's needs get enumerated independently
  and our surface today is almost entirely builder-shaped. Two of three personas currently
  have **no** dedicated tool.
- C) **Feature-Based** — one story per tool. Fastest, and the least useful: it assumes the
  seven tools are correct, which is the very thing that was never validated.
- D) **Hybrid** — personas first, journey within each.
- X) Other

[Answer]:

### Q-S2 · Personas to cover

- A) ⭐ **Three**: Builder (instructor/unit developer), Reviewer (approves the PR at the gate),
  Platform Operator (AI-SEI — inventory, cost, incident).
- B) **Four** — add Blueprint Author (contributes a blueprint to the catalog). The product
  proposal ranks catalog starvation as a HIGH risk and says contribution must be a P1
  requirement, so this persona has a real claim on being in scope.
- C) **Two** — Builder and Reviewer only; operators are out of scope this week.
- X) Other

[Answer]:

### Q-S3 · Acceptance-criteria format

There are no acceptance criteria anywhere today.

- A) ⭐ **Given/When/Then** — maps directly onto tests, and several map onto tests that already
  exist (e.g. *Given a singleton blueprint, When create_deployment is called with any
  deployment name, Then the stack name is `aidlc-main-hello-world`*).
- B) **Checklist** — faster to write, weaker to verify.
- C) **Both** — G/W/T for tool behaviour, checklist for demo readiness.
- X) Other

[Answer]:

### Q-S4 · Scope boundary for stories

- A) **Only what exists** — write stories for the seven tools we built, retroactively.
- B) ⭐ **What the product needs** — write stories for the builder's whole journey, then mark
  which are Served / Partially served / **Not served** by today's surface. The gap list is the
  deliverable. This is the only option that can tell you the seven tools are wrong.
- C) **Everything through P1** — include GitHub App, Entra ID, composition. Too wide for today.
- X) Other

[Answer]:

### Q-S5 · Demo status of unserved stories

If B above surfaces gaps (I expect it will — *list my deployments*, *delete a deployment*,
*see cost before I commit*, *review this safely* have no tool):

- A) ⭐ **Log to BACKLOG.md, do not build today.** The demo needs beats 2–4 to work, not
  completeness. Gaps become a credible roadmap slide rather than a discovered embarrassment.
- B) **Build any gap that blocks a demo beat**, log the rest.
- C) **Build them all** — not achievable before tomorrow.
- X) Other

[Answer]:

### Q-S6 · Who owns acceptance sign-off

The method wants stories to be testable by someone other than the author.

- A) ⭐ **The Requirements & Demand group** (Zach Jacques, Fermin Romero, Ernie Francis) — they
  are in the room specifically as the consuming side, and this is exactly the judgement the
  participant brief says they are there to make.
- B) **Track A team** signs off its own stories.
- C) **Whoever reviews the PR** at the gate.
- X) Other

[Answer]:

---

## Part B — Execution checklist (runs after approval)

Part 2 executes this exactly; nothing here runs before the gate clears.

- [ ] Load requirements, the answered Q1–Q9, SPEC contracts C1–C7, and the current tool surface
- [ ] Draft personas per **Q-S2**, each with role, motivation, what they fear, and what
      "success" means to them → `inception/user-stories/personas.md`
- [ ] Draft stories using the **Q-S1** breakdown, in the **Q-S3** acceptance-criteria format
- [ ] Verify every story against **INVEST** (Independent, Negotiable, Valuable, Estimable,
      Small, Testable); rewrite any that fail
- [ ] Attach acceptance criteria to every story — no exceptions
- [ ] Map every persona to its stories, and every story to the tool(s) that serve it
- [ ] Mark each story **Served / Partial / Not served** by today's surface (per **Q-S4**)
- [ ] Cross-check the reverse direction: every existing tool traces to at least one story —
      a tool with no story is a tool we should question
- [ ] File unserved stories per **Q-S5**
- [ ] Write `inception/user-stories/stories.md` and `personas.md`
- [ ] Update `aidlc-state.md`; log the gate in `audit.md`
- [ ] Present for approval, then open **Gate 3** (Application Design → Units Generation), which
      consumes this story map

## Part C — What this stage will *not* decide

Kept out deliberately, per the method's "avoid implementation details" rule:

- module boundaries and ownership → **Gate 3**
- performance/scale targets → **Gate 4**
- sprint order, estimates, who types what
