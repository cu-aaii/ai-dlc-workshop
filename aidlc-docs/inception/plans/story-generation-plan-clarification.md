# Story Generation Plan — Clarification (Round 2)

All eight answers were unambiguous on their own, and none contradict each other. But **three of
them interact in a way that leaves some required work with nowhere to live**, and the rules
forbid me choosing on your behalf. Two questions, then I generate.

## What the combination produces

- **Q2 = A** — thin vertical slices, each delivering one user-visible capability end to end
- **Q4 = A** — organized by user journey
- **Q7 = A** — non-functional work appears *only* as acceptance criteria on functional stories;
  "Nothing is a story on its own"

Each of those is reasonable. Together they mean **every** piece of work has to attach to a
user-visible slice inside a user journey. Some required work has no such slice.

### Work with no user-visible slice
From the approved `requirements.md`, these are blocking or mandatory, and a "Dashboard viewer"
(the single persona from Q1 = D) never sees any of them:

| Item | Why it has no slice |
|---|---|
| SECURITY-10 supply chain — pinned deps, base image pinned by digest, vuln scanning, SBOM | No user-visible behaviour whatsoever |
| PBT-01..10 — the property-based test suite itself | Tests aren't a capability a viewer uses |
| SECURITY-03 access logging (CloudFront, S3, WAF) | Logs are for operators, and Q1 = D dropped the operator persona |
| SECURITY-04 application logging — structured JSON from both Lambdas | Same |
| RESILIENCY-07 alarms — collector failure, snapshot staleness, Lambda errors/throttles | An alarm firing is not a viewer-facing capability |
| RESILIENCY-05 monitoring dashboard | Operator-facing |

### Question 9 — Where does that work go?

A) **Force-fit as acceptance criteria on the nearest slice**, even where the fit is loose — e.g.
   supply-chain pinning becomes a criterion on the inventory-collection story because that's the
   story whose Lambda gets built. Honours Q7 = A literally. *Cost*: some criteria will read as
   non-sequiturs against their story's Given/When/Then, and reviewers may not find them.

B) **Allow a small number of explicitly-labelled enabler stories** for exactly the items above —
   effectively Q2's option C after all. *Cost*: relaxes Q7 = A. *Benefit*: each blocking rule has
   one findable home, and nothing gets attached where it doesn't belong.

C) **Keep Q7 = A intact and add a non-story "Global Definition of Done"** appendix to
   `stories.md` — one checklist of cross-cutting obligations, with rule IDs, that applies to
   *every* story rather than being duplicated onto individual ones. Nothing becomes a story, so
   Q7 = A holds, and nothing gets force-fitted either. *Cost*: it's a fourth artifact shape
   alongside epics/journeys/stories.

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Platform plumbing

FR-6 (repurpose the stray `hello-world.yml` into the dashboard's deployment marker) and FR-7
(register in `pipeline/stacks.yml` **and** add the matching `pipeline/pipeline.yml` action, pass
parameters explicitly, conform to the stack-naming rule, pass `tools/check`) are *functional*
requirements — but a dashboard viewer never sees them either. FR-7 in particular is the item where
omission fails silently: green PR, all stages `Succeeded`, no stack deployed.

### Question 10 — Where does the platform plumbing go?

A) **A criterion on every slice** — each story is only done when its resources actually deploy
   through the pipeline. Puts the silent-failure risk in front of you on every story. *Cost*:
   heavy repetition across stories.

B) **Its own story** ("the dashboard stack deploys through the pipeline"), which every other slice
   depends on. *Cost*: it isn't user-value-shaped, and Q8 = A means no dependency markers, so the
   dependency stays implicit.

C) **Part of the Global Definition of Done** — pairs naturally with Q9 = C if you pick that.

D) **Treat FR-6 and FR-7 as out of story scope** — pure deploy mechanics, tracked in Workflow
   Planning and Construction instead of in `stories.md`. *Cost*: `stories.md` no longer covers
   every approved functional requirement, so the B6 traceability check will report FR-6 and FR-7
   as deliberately uncovered.

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

## Two things I'm handling without asking

Flagging these rather than burying them:

1. **Q6 = B vs. INVEST "Testable".** The placeholder cost stories you asked for have criteria
   marked TBD pending the data-source decision, so they can't satisfy INVEST's Testable
   criterion. I'll put them in a clearly-marked "Deferred / Stretch" section and exempt that
   section from the B5 INVEST verification, noting the exemption in the document. The v1 stories
   will be held to INVEST in full.

2. **Q5 = A and PBT-01.** You chose plain Given/When/Then without the Properties sub-list. That
   does *not* leave a gap: PBT-01 requires properties to be identified during **Functional
   Design**, a later stage, and `requirements.md` §4.2 already carries the candidate property
   list (snapshot round-trip, aggregation count invariants, collector idempotence, oracle
   comparison, tag-completeness classification). Properties will be derived there, from these
   acceptance criteria, rather than written into the stories now.

## One note on the assessment record

`user-stories-assessment.md` cited "Multi-Persona Systems" as one of four reasons to run this
stage, and argued personas would force the WAF-audience question to be answered explicitly.
Q1 = D (a single "Dashboard viewer") retires that reason. The decision to run the stage still
stands on the other three indicators — new user-facing feature, customer-facing API, and complex
business requirements needing acceptance criteria — and I've amended the assessment document to
say so rather than leaving a justification that no longer matches the plan. One consequence worth
knowing: with the operator personas collapsed, the operator-facing requirements listed under
Question 9 lost the persona they would otherwise have attached to, which is part of why that
question exists.
