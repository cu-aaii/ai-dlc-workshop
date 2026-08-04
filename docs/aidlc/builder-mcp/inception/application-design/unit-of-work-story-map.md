# Unit ↔ Story Map — builder-mcp

Every story assigned to exactly one owning unit (secondary units in parentheses).
Stage 7 stories carry their post-MVP mark. Full story text: `../user-stories/stories.md`.

| Unit | Stories | Count |
|---|---|---|
| U1 Catalog & Search | ST-01, ST-02, ST-03, ST-04, ST-24 *(post-MVP)* | 5 |
| U2 Deployment Lifecycle | ST-05, ST-07, ST-08, ST-09, ST-11, ST-22 *(post-MVP)*, ST-28 | 7 |
| U3 Operations & Observation | ST-14, ST-15, ST-16, ST-17, ST-18, ST-19, ST-20, ST-21 | 8 |
| U4 Spec & Handoff | ST-12, ST-26, ST-27 | 3 |
| U5 Platform Shell | ST-06, ST-10, ST-13 (+ all NFRs) | 3 |
| Post-MVP, unassigned until picked up | ST-23, ST-25 *(Stage 7)* | 2 |

Coverage cross-check: 28 stories, 28 assigned (26 to units, 2 post-MVP parked). Every
unit owns at least one Not-served or Partial story — i.e., every unit has real work, not
just custody:

- U1: ST-04 partial (cost estimate)
- U2: ST-28 served but never exercised beyond dry-run
- U3: **ST-19 Not served** (`deployment_list`), **ST-20 Not served** (restart cap + time box)
- U4: ST-27 partial (offboarding content)
- U5: ST-06 partial (elicitation impossible on stateless; dry_run stand-in — UX backlog)
