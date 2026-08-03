# GATE 1 — Extension Opt-Ins (Requirements Analysis defect)

These three questions are **mandatory at AI-DLC workflow start** and were never put to the
mob. Each extension ships an opt-in prompt; opting in loads its full rule set and makes those
rules **blocking constraints** — non-compliance stops a stage from completing.

They are reproduced below verbatim from the vendored rules. Fill in the `[Answer]:` tags.

Answering these late has a consequence worth stating plainly: **if you opt in, the code that
already exists has never been checked against those rules.** Opting in means a compliance pass
over what we built, not just a rule for future work. That pass is the point — this component
holds a GitHub credential and an AWS role on behalf of users who have neither.

---

## Question: Security Extensions

Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> **Context for the mob:** this is the one I would push hardest on. The server custodies a
> GitHub credential and an AWS role, exposes a public tool surface, and its governance
> invariants (no deploy, no merge, no push) are currently enforced only by my own care and
> four tests. "It's a two-day workshop MVP" is a real argument for B; "it will be the front
> door to Cornell's platform" is the argument for A. Note that D3/D4 already assume a
> security posture nobody has audited.

---

## Question: Resiliency Extensions

Should the resiliency baseline be applied to this project?

**What this extension is.** Enabling it applies a set of **directional, design-time best
practices** for building resilient systems, derived from the **AWS Well-Architected Framework
(Reliability Pillar)** and resilience-review guidance. It steers requirements, design, and code
toward fault tolerance, high availability, observability, and recoverability — covering 15
practice areas across business goals, change management, observability, high availability,
disaster recovery, and continuous improvement.

**What this extension is NOT.** Enabling it does **not** make your workload production-ready,
nor does it certify or guarantee any availability, RTO, or RPO target. It is a **starting
point** that scaffolds good resiliency decisions early — it is not a substitute for a formal
**AWS Well-Architected Review** of the built system.

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance (recommended for business-critical workloads, as an informed starting point that you can validate and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental projects where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> **Context for the mob:** partially pre-empted. The versioning/recovery options doc already
> proposed a `state:` contract with stateless/derived/authoritative classes — that came from
> your "knowledge base data is gone forever" case, not from this extension. Opting in would
> systematize that rather than start from zero.

---

## Question: Property-Based Testing Extension

Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> **Context for the mob:** B is a genuine fit here. `patching.py` does text surgery on
> `pipeline.yml` — insert an action, never corrupt the file — which is exactly a
> property ("for any valid deployment name, the patched template still parses and contains
> exactly one more action"). That is the highest-value place in this codebase for PBT and it
> is currently covered by five example-based tests.

---

## After answering

Per the rules, each answer is recorded in `aidlc-state.md` under `## Extension Configuration`,
and for every extension opted **in**, its full rule file is loaded and applied from that point
on — including a compliance pass over existing code, with any non-compliance treated as a
blocking finding.
