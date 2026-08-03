# Story Generation Plan — `dashboard` Blueprint (Cost & Usage Dashboard)

**Stage**: INCEPTION → User Stories, Part 1 (Planning)
**Date**: 2026-08-03
**Inputs**: `aidlc-docs/inception/requirements/requirements.md` (approved 2026-08-03),
`aidlc-docs/inception/plans/user-stories-assessment.md` (decision: Execute — Yes)

---

## How to use this document

Below are **8 questions** about *how* the stories should be written, followed by the execution
checklist that will run once you approve. Please fill in each `[Answer]:` tag directly in this
file — answers stay here as the audit trail for these decisions. Every question must be answered
before generation starts. If none of the options fit, choose **X) Other** and describe what you
want.

These questions are deliberately about **story methodology**, not about the product — the product
decisions were settled in `requirements.md`. If answering one of these makes you want to change a
requirement, say so and we'll amend requirements first.

---

## Part A — Questions

### Question 1 — User personas
`requirements.md` settled on a **network-level** access control (WAF IP allowlist) rather than an
identity system, which means "who is this for" is currently answered by a CIDR range rather than
by a role. Which personas should `personas.md` cover?

A) **Three personas** — Platform/AI Platform team engineer (owns the AWS account, cares about
   cost attribution and tag hygiene), Workshop organizer (needs live visibility during Aug 3–4),
   Campus builder (deploys blueprints via PR, has no AWS console; their resources are what gets
   reported)

B) **Two personas** — collapse Platform engineer and Workshop organizer into one "Platform
   operator" persona (they're largely the same people during the workshop), keeping Campus
   builder separate

C) **Four personas** — the three in option A, plus a non-human **Tooling/API consumer** persona
   for the JSON API (e.g. a future `builder-mcp` integration or a CI check that reads inventory)

D) **One persona** — a single "Dashboard viewer"; the distinctions don't matter for v1 given
   everyone inside the allowlist sees exactly the same thing

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 2 — Story granularity
How large should each story be?

A) **Thin vertical slices** — each story delivers one user-visible capability end to end
   (e.g. "see inventory grouped by deployment-id" spans collector → store → API → UI).
   More stories, each independently demonstrable. Best fit for INVEST's "Small" and "Valuable".

B) **Component-sized** — one story per architectural component (collector, snapshot store, API,
   UI, WAF/access control). Fewer, larger stories that map 1:1 to the things being built, but
   individual stories aren't independently valuable to a user.

C) **Mixed** — thin vertical slices for user-facing behaviour, plus explicit separate stories for
   the cross-cutting non-functional work (security headers, WAF, PBT test suite, alarms) that
   doesn't slot into any one user journey

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 3 — Story format
What format should each story use?

A) **Classic**: "As a `<persona>`, I want `<capability>`, so that `<benefit>`" — plus acceptance
   criteria

B) **Classic + explicit requirement traceability** — same as A, with each story citing the
   `FR-n` / NFR rule IDs from `requirements.md` that it satisfies, so coverage is checkable both
   directions

C) **Job story**: "When `<situation>`, I want to `<motivation>`, so I can `<expected outcome>`" —
   situation-first rather than role-first

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 4 — Breakdown / organization approach
How should `stories.md` be organized? (Trade-offs noted; hybrids are fine.)

A) **User Journey-Based** — stories follow workflows ("organizer checks workshop spend",
   "platform engineer hunts untagged resources"). *Benefit*: keeps user value front and centre,
   naturally surfaces gaps in the flow. *Cost*: cross-cutting technical work fits awkwardly.

B) **Feature-Based** — grouped by system capability (inventory collection, aggregation, API,
   UI, access control). *Benefit*: maps cleanly to what gets built and to `requirements.md`
   structure. *Cost*: less obvious what the user actually gains from each group.

C) **Persona-Based** — grouped by who benefits. *Benefit*: makes it obvious if a persona is
   underserved. *Cost*: duplication where personas want the same capability.

D) **Epic-Based** — hierarchical epics with sub-stories (e.g. Epic: Inventory Visibility →
   sub-stories). *Benefit*: scales to the deferred cost work and "other metrics later" without
   restructuring. *Cost*: more ceremony than a blueprint this size may need.

E) **Hybrid: Epic-Based outer structure, User Journey-Based within each epic** — epics separate
   v1 inventory from the deferred cost stretch goal and from cross-cutting NFR work; journeys
   organize the stories inside each. *Cost*: two organizing principles to keep straight.

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 5 — Acceptance criteria format and depth
Acceptance criteria here do double duty: they're the definition of done, and they're the source
for the property-based tests `requirements.md` §4.2 requires (PBT-01 needs identified properties).

A) **Given/When/Then (Gherkin-style)**, 3–6 criteria per story — structured, directly translatable
   into test names

B) **Given/When/Then, plus an explicit "Properties" sub-list** on stories that have testable
   invariants — naming the round-trip / invariant / idempotence / oracle property so PBT-01's
   property list falls out of the stories rather than being invented later

C) **Plain checklist bullets** — lighter weight, less ceremony, but a looser fit to the PBT
   requirement

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 6 — Scope boundary for the deferred cost work
`requirements.md` FR-8 makes cost figures a stretch goal with the data source deliberately
undecided. How should stories reflect that?

A) **Write v1 inventory stories only** — no cost stories at all until the data source is chosen;
   keeps the story set honest about what's actually specified

B) **Write v1 inventory stories, plus clearly-marked placeholder cost stories** in a separate
   "Deferred / Stretch" section, with acceptance criteria left explicitly TBD pending the data
   source decision — makes the intended shape visible without pretending it's ready to build

C) **Write full cost stories now**, choosing a data source as part of story-writing — note this
   would contradict FR-8 and reopen a decision you deliberately deferred, so it would need a
   requirements amendment first

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 7 — Non-functional work in stories
The three opted-in extensions produce a lot of blocking non-functional requirements (SECURITY-01..15,
PBT-01..10, RESILIENCY-01..15). How should those appear?

A) **As acceptance criteria on the relevant functional stories** — e.g. "HTTPS only" and "security
   headers present" become criteria on the UI story. Nothing is a story on its own.

B) **As dedicated NFR stories** in their own section, each citing its rule IDs — e.g. "Harden the
   dashboard's public edge (SECURITY-02, -07, -11)". Visible and trackable, at the cost of stories
   that aren't user-value-shaped.

C) **Both** — cross-cutting concerns get dedicated stories; concerns specific to one capability
   become acceptance criteria on that capability's story

X) Other (please describe after [Answer]: tag below)

[Answer]:

### Question 8 — Prioritization signal
Should stories carry a priority/sequencing marker? (Note: `user-stories.md` Step 11 says to avoid
development timelines and sprint planning at this stage, so this is a coarse marker at most, not
a schedule.)

A) **No markers** — stories are unordered; sequencing is decided in Workflow Planning where it
   belongs

B) **MoSCoW markers** (Must / Should / Could / Won't-in-v1) on each story — coarse, no dates,
   makes the v1 boundary explicit inside the story list

C) **A simple dependency note per story** ("depends on: story-3") without any priority label —
   captures the ordering that's genuinely forced by the architecture without implying a schedule

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Part B — Execution checklist (runs after you approve)

These steps execute in order once the questions above are answered and the plan is approved.
Checkboxes are marked `[x]` as each completes.

### B1. Preparation
- [ ] Re-read `aidlc-docs/inception/requirements/requirements.md` and extract every FR/NFR that
      needs story coverage
- [ ] Confirm the answers above contain no vague, contradictory, or option-merging responses
      (mandatory Step 9 analysis); raise a clarification file if any do
- [ ] Fix the story ID scheme (e.g. `US-01`…) and the persona ID scheme (e.g. `P-01`…)

### B2. Personas
- [ ] Generate `aidlc-docs/inception/user-stories/personas.md` with the persona set chosen in Q1
- [ ] For each persona capture: name/label, role, goals, motivations, characteristics, technical
      access level (AWS console? PR-only? neither?), and how they reach the dashboard
- [ ] State explicitly, per persona, whether the v1 WAF IP allowlist admits them — and record any
      audience knowingly excluded in v1
- [ ] Note each persona's relationship to the deferred identity/auth work

### B3. Stories
- [ ] Generate `aidlc-docs/inception/user-stories/stories.md` using the format from Q3 and the
      organization from Q4, at the granularity from Q2
- [ ] Cover all v1 functional requirements: FR-1 (tag inventory), FR-2 (periodic snapshot),
      FR-3 (read API), FR-4 (web UI), FR-5 (network access control), FR-6 (repurpose the stray
      `hello-world.yml`), FR-7 (platform wiring: template + `stacks.yml` + `pipeline.yml`)
- [ ] Handle FR-8 (cost stretch goal) per the boundary chosen in Q6
- [ ] Handle non-functional requirements per the placement chosen in Q7
- [ ] Include explicit stories or criteria for the behaviours that fail silently if unspecified:
      Tagging API **pagination** (truncation under-reports inventory), **snapshot staleness**
      display, **fail-closed** error handling, and the `pipeline.yml` action whose absence
      deploys nothing while reporting success
- [ ] Apply the prioritization/dependency convention from Q8

### B4. Acceptance criteria
- [ ] Write acceptance criteria for **every** story in the format from Q5
- [ ] Ensure criteria are observable and testable — no "works correctly" or "is performant"
- [ ] Where Q5 = B, name the PBT property category (round-trip / invariant / idempotence /
      oracle / easy-verification) for each story that has one, and cross-check against the
      candidate property list in `requirements.md` §4.2
- [ ] Verify the exceptions in `requirements.md` §4.6 are reflected honestly in criteria — in
      particular, no story may imply per-user authentication exists in v1

### B5. INVEST verification (mandatory artifact requirement)
- [ ] **Independent** — each story deliverable without requiring another story's completion,
      except where Q8's dependency notes make an ordering explicit
- [ ] **Negotiable** — stories state the need, not the implementation
- [ ] **Valuable** — each story names a persona who gains something (or is explicitly flagged as
      cross-cutting NFR work per Q7)
- [ ] **Estimable** — scope clear enough to size
- [ ] **Small** — consistent with the granularity from Q2
- [ ] **Testable** — every story has criteria that can pass or fail unambiguously

### B6. Traceability and coverage
- [ ] Map personas → stories (every persona appears in at least one story; every story names a
      persona or is marked cross-cutting)
- [ ] Map stories → requirements (every v1 FR is covered by at least one story; every story
      traces to at least one requirement — no orphan stories inventing new scope)
- [ ] Report any requirement left uncovered, rather than quietly padding the story list

### B7. Completion
- [ ] Mark every step above `[x]`
- [ ] Update `aidlc-docs/aidlc-state.md` current status
- [ ] Log the approval prompt in `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present the `# 📚 User Stories Complete` message and wait for explicit approval

---

## Notes on what this plan deliberately excludes
Per `user-stories.md` Step 11: no development timelines, no sprint planning, no technical design
decisions (component boundaries, table schemas, Lambda layout). Those belong to Workflow Planning
and Application Design. Resiliency decision points RESILIENCY-04 (CI/CD, rollback, deployment
style), RESILIENCY-14 (resiliency testing), and RESILIENCY-15 (incident response) also remain
deferred to NFR Design and are not asked here.
