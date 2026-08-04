# Story → Unit Map — `dashboard` Blueprint

**Stage**: INCEPTION → Units Generation, Part 2 (artifact 3 of 3)
**Date**: 2026-08-03
**Assignment rule**: Q2 = A — each story has exactly **one** owning unit, the one holding the most of
its work; where the work reaches into the other unit, that spillover is recorded rather than the story
being split or duplicated. Q7 = A — deferred stories are assigned to their eventual owner and marked.

---

## All 17 stories

| Story | Title | Owner | Spillover |
|---|---|---|---|
| US-01 | Open the dashboard from a Cornell network connection | **U-02** | — |
| US-02 | See every tagged resource the platform has deployed | **U-02** | U-01 (`normalize_resource`, `build_snapshot`) |
| US-03 | Group inventory by deployment, owner, or blueprint | **U-01** | U-02 (route + response shaping) |
| US-04 | Spot resources missing required tags | **U-01** | U-02 (route + response shaping) |
| US-05 | Know how fresh the data is | **U-01** | U-02 (surfacing it, and the `/api/*` no-cache policy) |
| US-06 | Get an honest answer when the data is unavailable | **U-02** | — |
| US-07 | Have the inventory refresh itself | **U-02** | — |
| US-08 | Pull the inventory as JSON | **U-02** | U-01 (`serialize_snapshot` determinism) |
| US-09 | [Enabler] Supply-chain integrity | **U-02** | — |
| US-10 | [Enabler] Property-based test suite | **U-01** | **U-02 — the one real split; see below** |
| US-11 | [Enabler] Access logging | **U-02** | — |
| US-12 | [Enabler] Application logging | **U-02** | — |
| US-13 | [Enabler] Resiliency alarms | **U-02** | — |
| US-14 | [Enabler] Operational monitoring | **U-02** | — |
| US-15 | [Enabler] Deploy through the pipeline | **U-02** | — |
| US-D1 | [Deferred] See cost alongside inventory | **U-02** | ⏸️ Not in v1 |
| US-D2 | [Deferred] See cost grouped by owner and blueprint | **U-02** | ⏸️ Not in v1 |

**Coverage: 17 assigned, 17 total, 0 unassigned, 0 owned twice.**

| Unit | Stories owned | Count |
|---|---|---|
| U-01 Domain Core | US-03, US-04, US-05, US-10 | 4 |
| U-02 Dashboard Platform | US-01, US-02, US-06, US-07, US-08, US-09, US-11, US-12, US-13, US-14, US-15, US-D1, US-D2 | 13 |

Reverse check — every story appears in exactly one row of the table above, and every unit's list is a
subset of the 17. Both directions hold.

---

## Why the four U-01 stories are U-01's

The assignment rule is "the unit holding the most of the work," and for these four the work *is* the
logic:

- **US-03** (grouping) — `group_by_tag`, including the `value=None` group that stops resources being
  silently dropped from a view. U-02 adds a route and a status code.
- **US-04** (tag gaps) — `classify_tag_gaps`, and specifically returning *which* tags are missing rather
  than a boolean, which is what makes the story actionable.
- **US-05** (freshness) — `evaluate_freshness` with an injected clock. Q8 = A of the Application Design
  made staleness a **server** judgement so two views agree; that judgement is a pure function.
- **US-10** (the PBT suite) — six named properties, all over U-01's two modules.

Each has a genuine U-02 spillover, because none of them reaches a user without a route, a response, and
an edge in front of it. That is recorded rather than resolved by splitting: a story whose acceptance
criteria describe user-visible behaviour cannot be wholly owned by a unit with no HTTP surface, and
pretending otherwise would make the map tidier and less true.

---

## The one real split: US-10

Q1 = A's two-unit shape means six of the seven enablers land wholly in U-02. US-10 is the exception, and
it is worth spelling out because it is the only place Q2 = A's spillover machinery does any work.

| Part of US-10 | Unit | Note |
|---|---|---|
| The six properties over C-04 and C-05 | **U-01** | Runnable with no AWS. This is the bulk of the story and why U-01 owns it. |
| Generators producing realistic raw Tagging API payloads | **U-02** | The *shape* being generated is C-04's input, which U-02 knows because C-01 consumes the real API |
| PBT-01's "identify properties at Functional Design" | Both | U-01 at its Functional Design pass; U-02 at its own, for anything U-02-side worth a property |
| Shrinking / minimal counterexample reporting | **U-01** | A property of the test harness, which lives with the properties |

**Sequencing consequence**: U-01's properties do not wait for U-02. The generators can start from C-04's
declared input type — the Tagging API's response shape is a documented contract, not a discovery — so
U-01 is not blocked on U-02 existing. That is the point of Q5 = A's depth-first order.

---

## Requirement → story → unit traceability

Preserved from `stories.md` so the chain is followable end to end.

| Requirement | Stories | Unit(s) |
|---|---|---|
| FR-1.1 complete inventory | US-02 | U-02 (+U-01) |
| FR-1.2 tag values captured | US-02 | U-02 (+U-01) |
| FR-1.3 group by three tags | US-03 | **U-01** |
| FR-1.4 tag-gap identification | US-04 | **U-01** |
| FR-2.1 read never triggers collection | US-07 | U-02 |
| FR-2.2 `collected_at` exposed | US-05 | **U-01** (+U-02) |
| FR-2.3 interval is a parameter | US-07 | U-02 |
| FR-2.4 schema extensible | US-08 | U-02 (+U-01) |
| FR-3.1–3.3 views and states | US-02, US-03, US-04, US-06 | U-01 + U-02 |
| FR-3.4 no internals in errors | US-06 | U-02 |
| FR-3.5 rate limiting | US-01 | U-02 |
| FR-4.1–4.2 private bucket, OAC | US-01 | U-02 |
| FR-4.5 read-only, no credentials | US-01, US-08 | U-02 |
| FR-5.1–5.2 deny-by-default allowlist | US-01 | U-02 |
| FR-5.4 block is diagnosable | US-01, US-11 | U-02 |
| FR-5.5 no identity system | US-01 | U-02 |
| FR-6 repurpose `hello-world.yml` | US-15 | U-02 |
| FR-7.1–7.2 registry + action | US-15 | U-02 |
| FR-8 cost figures | US-D1, US-D2 | ⏸️ U-02, deferred |
| §4.1 SECURITY-01..15 | US-01, US-09, US-11, US-12 | U-02 |
| §4.2 PBT-01..10 | US-10 | **U-01** (+U-02 generators) |
| §4.3 RESILIENCY-01..15 | US-13, US-14 | U-02 |
| §4.5 AWS-free logic | US-03, US-04, US-05, US-10 | **U-01** |

**No v1 functional requirement is unassigned.** FR-8 is deferred by prior decision, not omission.

---

## Known gaps, unchanged by this mapping

**US-15 does not cover the Build stage action, the `Dockerfile` targets, or `blueprint.yaml`.** First
raised at Workflow Planning; still true. Assigned to **U-02** and carried by Infrastructure Design and
Code Generation. Cheaper to close than when raised — the Build stage now exists (amendment §A1.2) — but
still not in any story's acceptance criteria. No amendment proposed; the user may request one.

**US-09's fourth acceptance criterion reads more broadly than Q11 = B delivers.** Open as Q13 in
`application-design-plan-clarification-2.md`, non-blocking. Owner **U-02**.

**US-D1/US-D2 are assigned but have no data source.** FR-8's Cost Explorer vs. CUR decision is
deliberately undecided, so these two are placeholders with an owner rather than plans. Assigning them
satisfies this stage's completion criterion without implying they are ready to build.

**The queued telemetry amendment has no stories yet.** Routed to a second Requirements → Stories pass by
Q3 = B of the telemetry questions. When it lands, its stories are expected to be **U-02**-owned on the
reader side — but the emitting side is a cross-blueprint contract that belongs to no unit here.
Two design drafts on this branch (`aidlc-docs/design/composable-dashboards.md`,
`observability-contract.md`) exist to be ratified before that pass, and they report repo changes beyond
those in amendment A1 — including a `team-d` track the `cornell:deployment-id`-under-composition
decision needs to be made with. Flagged here so that pass is not started as a dashboard-local decision.
