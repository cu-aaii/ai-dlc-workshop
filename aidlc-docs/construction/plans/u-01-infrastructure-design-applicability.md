# Infrastructure Design — does it apply to U-01?

**Phase**: CONSTRUCTION → Infrastructure Design, Step 1
**Date**: 2026-08-03
**Status**: Two questions. Nothing else is blocked on them, but the next stage is.

---

## Why I am asking instead of running the stage

Infrastructure Design's stated purpose is *"Map logical software components to actual infrastructure
choices."* Step 1 is *"Identify logical components needing infrastructure."*

For U-01 the answer is already on record, from the artifact you approved twenty minutes ago:

> **U-01 contributes zero infrastructure components.** No queue, no cache, no circuit breaker, no load
> balancer, no database, no connection pool, no scheduler, no bucket, no function, no role.
> — `nfr-design/logical-components.md`

Running the stage anyway produces two artifacts whose every section reads "none — see U-02." That is not
documentation, it is filler, and it would make a future reader think U-01's infrastructure was considered
and found sufficient rather than that U-01 has none by design.

**Three further reasons this is not a formality:**

1. **U-01's infrastructure-adjacent decisions are already written.** `pyproject.toml` placement, the
   `uv.lock`, the `.python-version` pin, the `src/dashboard/` layout, and the Dockerfile targets and
   context are all in `nfr-requirements/tech-stack-decisions.md` TSD-1, TSD-2 and TSD-7. Re-documenting
   them under `infrastructure-design/` would duplicate, not add — and duplicated decisions drift.

2. **The execution plan's own justification for this stage is entirely U-02's.** It lists
   "SECURITY-01, -06, -14 SRI, RESILIENCY-08, container build." Encryption at rest, least-privilege IAM,
   subresource integrity, and the container build are all things U-01 has no part of.

3. **This is the first stage where the per-unit split genuinely does not fit.** Functional Design, NFR
   Requirements and NFR Design all divided cleanly. Infrastructure does not: the Dockerfile has two
   targets and **both images contain U-01's code**, and the two CloudFormation templates deploy resources
   that serve U-01's logic without U-01 owning any of them. The infrastructure is indivisible in a way the
   logic was not.

I am not treating that third point as licence to skip a stage the execution plan says to execute. It is
your call.

---

### Question 1 — What happens to U-01's Infrastructure Design?

**A) Skip it, with the justification recorded in `aidlc-state.md`** ← *recommended*
   Marked SKIPPED for U-01 specifically, citing the zero-component finding and the three reasons above.
   All infrastructure content lands in **U-02's** Infrastructure Design pass, which is where the
   components actually are.
   *Why*: it is the honest description of the situation, and the Adaptive Workflow Principle exists for
   exactly this — a conditional stage with nothing to decide for this unit. It also keeps U-01's
   packaging decisions in one place (TSD-1/2/7) rather than split across two documents.
   *Cost*: a stage the execution plan marked EXECUTE is skipped for one unit. Recorded as a deviation, and
   the plan's stated justification for the stage is preserved intact for U-02.

**B) Run a thin pass** — generate both artifacts, documenting the zero-infrastructure position formally.
   *Why*: no stage is skipped; the position is captured under the path the rules name, so anyone looking
   for `u-01-domain-core/infrastructure-design/` finds an answer rather than a missing directory.
   *Cost*: two artifacts whose content is "none, none, none, and the packaging decisions are in
   TSD-1/2/7." The duplication is the risk — a future edit to TSD-1 would leave these stale.

**C) Run ONE combined Infrastructure Design covering both units now**, on the grounds that the
   infrastructure cannot be split by unit anyway.
   *Why*: matches reality most closely. One Dockerfile, one template pair, one pipeline edit — designed
   once, not twice.
   *Cost*: it abandons depth-first for this stage (see Q2), and it means designing U-02's infrastructure
   **before** U-02's Functional Design, NFR Requirements and NFR Design have run — so its inputs would not
   exist yet. That is a real sequencing problem, not a stylistic one.

X) Other

[Answer]:A

---

### Question 2 — Does depth-first still hold for U-01?

Q5 = A of Units Generation chose **unit-by-unit, depth-first**: take U-01 through every stage, then start
U-02.

Under option A or B above, U-01's remaining stages are **Code Generation** (write `src/dashboard/core/`,
the ten properties, the generators, the example-based size test) and **Build and Test** (run them). Both
are meaningful for U-01 and neither needs infrastructure — which is precisely the payoff Q1 = A of Units
Generation promised: the pure core proven on a laptop before any pipeline machinery is trusted.

**A) Yes — continue depth-first. U-01 goes to Code Generation next** ← *recommended*
   *Why*: it delivers the thing the decomposition was chosen for. At the end of it, ten properties pass
   locally and the riskiest infrastructure work has a proven foundation underneath it.
   *Cost*: `tools/check` cannot run in this environment (needs `uv` and `terraform`), so "the properties
   pass" will be **written but unverified here**. Someone with those tools installed, or CI, is the first
   real check. Stated plainly because the value of this ordering is verification, and I cannot perform it.

**B) Switch to breadth-first now** — start U-02's Functional Design, and return to U-01's Code Generation
   later so both units' code is written together.
   *Why*: U-02's design would surface anything that changes U-01's interface before U-01's code is
   written, avoiding rework. The four outstanding cross-unit obligations all point from U-01 into U-02.
   *Cost*: nothing runs or is verifiable for considerably longer, in a two-day workshop. It also reverses
   an approved decision.

X) Other

[Answer]:A

---

## What is not in question

- **U-02 gets a full Infrastructure Design pass** under every option. That is where SECURITY-01, -06, -14,
  RESILIENCY-08, the container build, both templates, the `stacks.yml` entries, the `pipeline.yml` edit,
  and §6.4's unresolved site-sync ordering all get decided.
- **§6.4 stays open** and stays U-02's. Nothing here touches it.
- **No U-01 decision is reopened.** The ten properties, 26 NFR requirements, nine patterns, and eight
  business rules all stand.

---

## Resolved (2026-08-03)

**Q1 = A** — U-01's Infrastructure Design is **SKIPPED**, with the justification recorded in
`aidlc-state.md`. All infrastructure content lands in U-02's pass.

**Q2 = A** — depth-first holds. U-01 proceeds to **Code Generation**.

### Recorded as a deviation from the execution plan

The execution plan marked Infrastructure Design **EXECUTE**. It is skipped **for U-01 only**, on the
zero-component finding in `nfr-design/logical-components.md` and the three reasons above. The plan's
stated justification for the stage — SECURITY-01, -06, -14 SRI, RESILIENCY-08, container build — is
**preserved intact for U-02**, which is where every one of those lives.

This is the **second** stage skipped in the whole workflow. The first was Reverse Engineering, at
Workspace Detection. Recording the count for the same reason the RESILIENCY deferral count is recorded: a
third skip should be visible as a pattern rather than look like a first.

### Consequence for the artifact tree

`aidlc-docs/construction/u-01-domain-core/infrastructure-design/` **will not exist.** Anyone looking for
it should find this file. Noted because a missing directory is ambiguous between "skipped deliberately"
and "not done yet", and the two are very different.
