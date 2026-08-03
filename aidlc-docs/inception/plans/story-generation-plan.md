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

[Answer]: D

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

[Answer]:A

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

[Answer]:A

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

[Answer]:A

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

[Answer]:A

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

[Answer]:B

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

[Answer]:A

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

[Answer]:A

---

## Part A2 — Resolved methodology (all 10 answers consolidated)

Answers to Q1–Q8 above; Q9–Q10 in
`aidlc-docs/inception/plans/story-generation-plan-clarification.md`. This is the methodology that
Part B executes.

| Decision | Answer | Effect on `stories.md` / `personas.md` |
|---|---|---|
| Personas | Q1 = **D** | **One** persona: "Dashboard viewer". No operator/builder split — everyone inside the WAF allowlist sees the same thing in v1. |
| Granularity | Q2 = **A** | Thin vertical slices; each v1 story delivers one user-visible capability end to end (collector → store → API → UI). |
| Format | Q3 = **A** | Classic "As a Dashboard viewer, I want …, so that …". **No** FR/NFR citation inside the story text. |
| Organization | Q4 = **A** | User Journey-Based. Journeys are distinguished by *goal*, not by role (only one persona exists). |
| Acceptance criteria | Q5 = **A** | Given/When/Then, 3–6 per story. **No** "Properties" sub-list. |
| Cost stretch goal | Q6 = **B** | v1 inventory stories, plus clearly-marked placeholder cost stories in a "Deferred / Stretch" section with criteria explicitly TBD. |
| Non-functional work | Q7 = **A**, amended by Q9 = **B** | Capability-specific NFRs → acceptance criteria on that capability's story. Cross-cutting NFRs with no user-visible slice → **explicitly-labelled enabler stories** (Q9 = B knowingly relaxes Q7 = A's "nothing is a story on its own"). |
| Platform plumbing | Q10 = **B** | FR-6 + FR-7 get **their own story** ("the dashboard stack deploys through the pipeline"). |
| Prioritization | Q8 = **A** | **No** priority or dependency markers. Sequencing is decided in Workflow Planning. |

### Enabler stories to be written (Q9 = B)
Exactly these, each labelled **[Enabler]** and citing its rule IDs — nothing else becomes an
enabler story:
1. Supply-chain integrity — SECURITY-10 (pinned deps, digest-pinned base image, vuln scanning, SBOM)
2. Property-based test suite — PBT-01..10 (Hypothesis; complements example-based tests per PBT-10)
3. Access logging — SECURITY-03 (CloudFront, S3, WAF logging so blocked requests are visible)
4. Application logging — SECURITY-04 (structured JSON from both Lambdas, no secrets or PII)
5. Resiliency alarms — RESILIENCY-07 (collector failure, snapshot staleness, Lambda errors/throttles)
6. Operational monitoring — RESILIENCY-05 (metrics + health dashboard; tracing marked N/A)
7. Pipeline deployment — FR-6 + FR-7 (Q10 = B; repurpose the stray template, register in
   `stacks.yml`, add the matching `pipeline.yml` action, explicit parameters, stack-naming
   conformance, `tools/check` green)

### Three judgment calls recorded rather than asked
1. **Deferred section is exempt from INVEST.** Q6 = B's placeholder cost stories carry TBD
   criteria, so they cannot satisfy INVEST "Testable". The Deferred / Stretch section is exempted
   from the B5 check and says so in the document; v1 stories are held to INVEST in full.
2. **Q5 = A leaves no PBT gap.** PBT-01 identifies properties at **Functional Design**, a later
   stage, and `requirements.md` §4.2 already carries the candidate property list. Properties get
   derived there from these criteria.
3. **Q10 = B's dependency stays in prose.** Q8 = A forbids dependency markers, so the fact that
   every slice needs the pipeline story is stated in that story's narrative text rather than as a
   structured marker field on the other stories.

---

## Part B — Execution checklist (runs after you approve)

These steps execute in order once the plan is approved. Checkboxes are marked `[x]` as each
completes.

### B1. Preparation
- [x] Re-read `aidlc-docs/inception/requirements/requirements.md` and extract every FR/NFR that
      needs story coverage
- [x] Confirm the answers above contain no vague, contradictory, or option-merging responses
      (mandatory Step 9 analysis); raise a clarification file if any do — **done: Round 2
      clarification raised and answered (Q9 = B, Q10 = B)**
- [x] Fix the story ID scheme and the persona ID scheme — **`US-nn` for stories (`US-nn [Enabler]`
      for enabler stories), `P-01` for the single persona**

### B2. Personas
- [ ] Generate `aidlc-docs/inception/user-stories/personas.md` with the **single** persona `P-01`
      "Dashboard viewer" (Q1 = D)
- [ ] Capture: label, role, goals, motivations, characteristics, technical access level (AWS
      console? PR-only? neither?), and how they reach the dashboard
- [ ] State explicitly that admission is by **network position**, not identity — inside the WAF
      allowlist or not — and record which audiences that knowingly excludes in v1 (anyone
      off-network, including a legitimate Cornell user on a non-allowlisted connection)
- [ ] Note the persona's relationship to the deferred identity/auth work, and that collapsing to
      one persona means v1 draws no distinction between platform operators, workshop organizers,
      and campus builders

### B3. Stories
- [ ] Generate `aidlc-docs/inception/user-stories/stories.md`: classic format (Q3 = A), organized
      by **user journey** (Q4 = A), as **thin vertical slices** (Q2 = A), IDs `US-nn`
- [ ] Cover the viewer-facing v1 functional requirements as journey slices: FR-1 (tag inventory),
      FR-2 (periodic snapshot + freshness), FR-3 (read API), FR-4 (web UI), FR-5 (network access
      control)
- [ ] Write the **7 enabler stories** listed in Part A2, each labelled `[Enabler]` and citing its
      rule IDs (Q9 = B) — including the FR-6 + FR-7 pipeline-deployment story (Q10 = B)
- [ ] Handle FR-8 in a clearly-marked **Deferred / Stretch** section with criteria explicitly TBD
      pending the data-source decision (Q6 = B)
- [ ] Cover the behaviours that fail silently if unspecified: Tagging API **pagination**
      (truncation under-reports inventory), **snapshot staleness** display, **fail-closed** error
      handling, and the `pipeline.yml` action whose absence deploys nothing while reporting success
- [ ] Add **no** priority or dependency markers (Q8 = A); state the pipeline-story dependency in
      prose only

### B4. Acceptance criteria
- [ ] Write Given/When/Then criteria, 3–6 per story, for every v1 and enabler story (Q5 = A)
- [ ] Ensure criteria are observable and testable — no "works correctly" or "is performant"
- [ ] Attach capability-specific NFRs as criteria on their capability's story (Q7 = A) — e.g.
      HTTPS-only and security headers on the UI story, input validation and rate limiting on the
      API story
- [ ] Add **no** "Properties" sub-list (Q5 = A); properties are identified at Functional Design
      from `requirements.md` §4.2
- [ ] Verify the exceptions in `requirements.md` §4.6 are reflected honestly — in particular, no
      story may imply per-user authentication exists in v1

### B5. INVEST verification (mandatory artifact requirement)
- [ ] **Independent** — each story deliverable without requiring another's completion
- [ ] **Negotiable** — stories state the need, not the implementation
- [ ] **Valuable** — each v1 story names the gain for `P-01`; enabler stories are explicitly
      labelled as cross-cutting instead
- [ ] **Estimable** — scope clear enough to size
- [ ] **Small** — consistent with thin vertical slices
- [ ] **Testable** — every story has criteria that can pass or fail unambiguously
- [ ] Apply the above to v1 and enabler stories only; **exempt the Deferred / Stretch section**
      (TBD criteria cannot be Testable) and state that exemption in the document

### B6. Traceability and coverage
- [ ] Map `P-01` → stories (the persona appears in every non-enabler story; every enabler story is
      marked cross-cutting rather than naming a persona)
- [ ] Map stories → requirements in a coverage table (Q3 = A keeps citations out of story *text*,
      so traceability lives in this table instead): every v1 FR covered by at least one story,
      every story tracing to at least one requirement — no orphan stories inventing new scope
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
