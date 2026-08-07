# NFR Requirements Plan — U-01 Domain Core

**Phase**: CONSTRUCTION → NFR Requirements
**Date**: 2026-08-03
**Unit**: U-01 Domain Core (C-04, C-05) — pure Python, no AWS, no I/O, no clock
**Inputs**: `construction/u-01-domain-core/functional-design/` (approved 2026-08-03) ·
`inception/requirements/requirements.md` §4.1–§4.5 · amendments A1/A2

---

## What NFR means for a unit with no infrastructure

Most of this stage's mandated categories assume a deployable. U-01 is a library called in-process: it
has no uptime, no scaling trigger, no endpoint, and no storage. Manufacturing scalability and
availability questions for it would produce answers that constrain nothing.

So the questions below cover the categories that **are** real here, and Part A1 records the ones that
are not, with the reason each is inapplicable rather than a silent omission.

Two categories that *are* unusually live for this unit:

- **Maintainability and testability**, because U-01's entire justification as a separate unit is that it
  can be verified with no AWS. If nothing actually runs its ten properties in CI, that justification
  evaporates and the properties become decoration. Q3 is the question that decides whether U-01 is real.
- **Privacy in error paths.** Tag values carry NetIDs. U-01 is where tag values are parsed and where
  exceptions are raised, so it is the one place a NetID could leak into a log or an HTTP body. Q6.

## Precedent found, so not asked

`packages/builder-mcp/` already settles several choices this stage would otherwise ask about. Following
existing precedent rather than re-deciding:

| Choice | Established value | Source |
|---|---|---|
| PBT framework | **Hypothesis** `>=6.100` | `pyproject.toml`; `test_properties.py` cites PBT-09 |
| Test runner | **pytest** `>=8`, `testpaths = ["tests"]` | same |
| Python floor | `requires-python = ">=3.11"` | same |
| Interpreter pin | **`.python-version` = `3.13`** | required by the `uv`-picks-32-bit gotcha in `CLAUDE.md` |
| Build backend | **hatchling**, `src/` layout | same |
| Dependency manager | **`uv`** with a committed lockfile | repo-wide |

These are recorded as decisions in `tech-stack-decisions.md` with the precedent cited, not re-opened.

---

## Part A — Questions

A recommended option is marked in each. **A recommendation is not a default and nothing is chosen for
you.** Answer `X` and describe if none fit.

---

### Question 1 — Layout: does the dashboard follow the `src/` convention the newer blueprints use?

Q3 = A of Units Generation put `core/`, `collector/`, `api/`, `ui/` as siblings of `infra/`. That
decision was made before the monorepo reorganization (amendment A2). The two blueprints written since
both use **`src/`**, and `CLAUDE.md` now documents the blueprint shape as
"`blueprint.yaml` + `infra/` (+ `src/`, `infra/azure/`)":

- `blueprints/tiny-chatbot/` → `blueprint.yaml`, `infra/`, `Dockerfile`, `src/app.py`, `README.md`
- `blueprints/aisei-site/` → `blueprint.yaml`, `infra/`, `Dockerfile`, `app/`, `README.md`

Both also put the **`Dockerfile` at the blueprint root**, which independently confirms the A2.2
correction rather than resting on my reading of `CLAUDE.md`.

**A) Adopt `src/`** ← *recommended*
```
blueprints/dashboard/
  blueprint.yaml
  README.md
  Dockerfile          targets: collector, api
  infra/              dashboard-storage.yml, dashboard.yml
  src/
    core/             U-01 — no boto3, no os, no datetime.now()
    collector/        U-02
    api/              U-02
  ui/                 U-02 — not Python, stays out of src/
  tests/
```
*Why*: conforms to the documented shape and to both real examples, so the next person reading this
blueprint finds what the others taught them to expect. `core/` keeps its grep-able boundary — it just
sits one level deeper (`src/core/`).
*Cost*: a minor amendment to the approved Q3 = A layout, recorded as such.

**B) Keep Q3 = A exactly as approved** — flat siblings, no `src/`.
*Why*: it is what you approved, and churn has a cost.
*Cost*: this blueprint becomes the odd one out among three, and `CLAUDE.md`'s documented shape says
otherwise. Future readers will assume `src/` and not find it.

**C) `src/` and also move `ui/` under it** — everything buildable in one tree.
*Cost*: `src/` reads as Python here; a Node project inside it is more surprising than helpful.

X) Other

[Answer]:A

---

### Question 2 — Does the dashboard's Python get a `pyproject.toml`?

`tiny-chatbot/src/app.py` has **no** package metadata — a blueprint's Python has so far just been source
copied into an image. U-01 needs more than that: pytest and Hypothesis as dev dependencies, a
`.python-version` pin (per the `uv` 32-bit gotcha), and somewhere to configure type checking.

**A) One `pyproject.toml` at `blueprints/dashboard/`, covering the whole blueprint's Python** ← *recommended*
   Both Lambdas and the tests share it. Gives the `.python-version` pin and the pytest/mypy config a
   home. `uv.lock` committed beside it.
   *Why*: it is the smallest thing that makes U-01's tests runnable and reproducible, and it mirrors
   `packages/builder-mcp/`'s shape without claiming U-01 is a standalone package.
   *Cost*: a second Python project in the repo, so a second lockfile to keep current.

**B) No package metadata** — deps installed in the Dockerfile, tests run with a repo-level pytest config.
   *Cost*: no lockfile means the laptop, CI and CodeBuild can resolve different Hypothesis versions, and
   `.python-version` has nowhere to live — which is precisely the failure `CLAUDE.md` documents.

**C) U-01 as its own package under `packages/dashboard-core/`**, separate from the blueprint.
   *Why*: strongest expression of U-01's independence; it genuinely has no blueprint-specific
   dependency.
   *Cost*: breaks the Dockerfile-context decision from `unit-of-work.md` — both images need `core/`, and
   a blueprint-root context cannot reach `packages/`. Also `packages/` is documented as "a component
   that **isn't** a blueprint," and this is part of one.

X) Other

[Answer]:A

---

### Question 3 — What actually runs U-01's ten properties?

**The question that decides whether U-01 is a real unit.** Its entire justification is being verifiable
without AWS. If no automated gate runs the properties, PBT-01..10 are satisfied on paper and nothing
enforces them.

`tools/check` is the sanctioned pre-push check and CI runs the same script. It currently lints
CloudFormation and validates the registry. `uv` is already a prerequisite, so adding Python tests adds
**no new prerequisite** for contributors. (`tools/dev` also now exists — worth checking whether it is the
better host.)

**A) Add the U-01 test suite to `tools/check`** ← *recommended*
   *Why*: one command, already the documented gate, already needs `uv`. A contributor who only touches
   templates pays a few seconds; a contributor who breaks a property finds out before pushing.
   *Cost*: `tools/check` gets slower for everyone, and it now fails for reasons unrelated to templates.
   With `max_examples=100` across ten properties this should be seconds, not minutes.

**B) A separate CI job, not in `tools/check`** — keeps the pre-push check fast.
   *Cost*: the properties stop being a pre-push gate, so they are found broken after a push. Given there
   is now **no required PR approver** (amendment §A1.1) and `validate` is the only automated gate, moving
   checks *out* of the gate is a bigger loss than it was a day ago.

**C) Tests exist but nothing gates them** — run them by hand.
   *Cost*: rejected in the analysis, not merely disfavoured. Ten unenforced properties are worse than
   none, because they imply coverage that does not exist.

X) Other

[Answer]:A

---

### Question 4 — Type checking, and how strictly?

U-01 is the ideal candidate: pure functions, frozen dataclasses, no dynamic dispatch, no AWS response
shapes to model. Nothing in the repo type-checks today.

**A) mypy in strict mode over `src/core/` only** ← *recommended*
   *Why*: highest value per unit of effort, and confined to the code where strictness is nearly free.
   Catches the `str | None` handling around `Group.value` and the three-valued `Freshness` — the two
   places the design's optionality actually lives.
   *Cost*: a tool and a config; strict mode on U-02's boto3-facing code later would be much more work,
   so this sets a precedent that needs a documented boundary.

**B) mypy strict over all the blueprint's Python** — U-01 and U-02 together.
   *Cost*: boto3 response types are loosely typed; strict mode there generates noise that gets silenced
   with `# type: ignore`, which teaches people to ignore the checker.

**C) No type checking** — rely on tests.
   *Cost*: the ten properties test behaviour, not the optional-handling the compiler would catch for
   free.

X) Other

[Answer]:A

---

### Question 5 — Property-test budget

Ten properties. `packages/builder-mcp/tests/test_properties.py` caps at `max_examples=100` and notes the
PBT rules allow up to 200.

**A) `max_examples=100`, matching the existing precedent** ← *recommended*
   *Why*: consistency with the only other PBT suite here, comfortably inside the rules' cap, and fast
   enough for Q3 = A's pre-push gate.

**B) `max_examples=200`** — the rules' ceiling; finds more.
   *Cost*: doubles the gate's runtime for a suite that runs on every push.

**C) Split** — 100 in the pre-push gate, a higher count nightly.
   *Why*: best of both.
   *Cost*: two configurations, and a nightly job nobody watches is a job that fails silently.

X) Other

[Answer]:A

---

### Question 6 — May an exception or a `skipped_reasons` key ever contain a tag value or an ARN?

Tag values carry **NetIDs** (`cornell:owner`). U-01 parses tag values and raises exceptions, so it is the
one place a NetID can escape into a log line or — via an unhandled error — an HTTP body. FR-3.4 and
SECURITY-09 already forbid internals in error responses; this decides U-01's side of that.

`skipped_reasons` is already a closed category set (`"arn"`, `"tags"`) per the functional design. This
question is about the general rule.

**A) Never. U-01 exceptions carry a category and nothing else** ← *recommended*
   No ARN, no tag key, no tag value, no positional index into the input. Debugging detail is U-02's to log
   at its own boundary, where it can decide what is safe.
   *Why*: makes the privacy property structural rather than dependent on every future exception message
   being written carefully. A pure library that cannot leak is easier to reason about than one that
   promises not to.
   *Cost*: debugging a malformed-ARN report means reproducing it, since the failing ARN is not in the
   error.

**B) Category plus the ARN** — ARNs are not secret and are the only useful debugging handle.
   *Cost*: ARNs can embed names, and this is the exact string that would then flow into logs and
   possibly a 500 body. Also weakens the "no internals in errors" line by making U-01 the exception.

**C) Category plus a redacted ARN** (service and type only, no account or resource name).
   *Why*: some debuggability, no identifiers.
   *Cost*: a redaction function is a thing that can be wrong, and its output is the thing you would then
   trust.

X) Other

[Answer]:A

---

### Question 7 — How is an ARN parsed?

**A) `str.split(":", 5)` with arity and emptiness checks** ← *recommended*
   *Why*: linear, no backtracking, no catastrophic-input class at all. ARNs are a fixed 6-field
   colon-delimited grammar, so a regex buys nothing a split does not already give. Input arrives from
   AWS rather than a user, but "the input is trusted" is a property that erodes — the collector is one
   config change from reading a file.
   *Cost*: slightly more explicit validation code than a single pattern match.

**B) A compiled regular expression** — one declarative grammar, arguably more readable.
   *Cost*: introduces a ReDoS surface for zero functional gain, and a permissive pattern silently accepts
   malformed ARNs that a split-plus-check would reject.

X) Other

[Answer]:A

---

### Question 8 — What snapshot size must U-01 hold up at?

`requirements.md` §4.4 states the expected volume as **tens to low hundreds** of resources.
`unit-of-work.md` records that C-02's read-the-whole-object design would be wrong at ten thousand, and
that the threshold is written down so a future reader knows when to revisit rather than discovering it as
a surprise. This sets U-01's side of that.

**A) Linear algorithms; verified to 10,000 records in a property test; no optimization beyond that** ← *recommended*
   *Why*: two orders of magnitude of headroom over the stated volume, at no design cost — the grouping
   and classification algorithms are already single-pass. The property test at 10k is what turns
   "should be linear" into something checked.
   *Cost*: one slower property test. (The `_reference_group_by_tag` oracle is quadratic, so it runs at
   small sizes only — worth stating so nobody runs the oracle comparison at 10k and concludes U-01 is
   slow.)

**B) Correctness only; no performance assertion** — §4.4's volume makes it moot.
   *Cost*: an accidental O(n²) in grouping would pass every existing property and only show up in
   production, where the fix is not a U-01 change but a data-model change.

**C) A specific latency budget** (e.g. grouping under 50 ms at 1,000 records).
   *Cost*: wall-clock assertions in a property suite are flaky on shared CI, and would produce failures
   that teach people to retry rather than to look.

X) Other

[Answer]:A

---

## Part A1 — Categories evaluated and NOT asked about

Each with the reason it does not apply to **this unit**. Several apply squarely to U-02 and will be asked
at its NFR pass.

| Category | Why not asked for U-01 |
|---|---|
| **Availability, uptime, DR, failover** | A library has no uptime. RESILIENCY-02 already records RTO/RPO as N/A because the snapshot is rebuildable, and U-01 holds no state to recover. |
| **Scalability triggers, capacity planning, autoscaling** | U-01 runs in-process inside whatever calls it. It has no scaling dimension of its own; Q8 covers the only real question (input size). |
| **Throughput, concurrency, rate limiting** | No endpoint, no shared mutable state. Every function is pure, so it is trivially safe under concurrency and there is nothing to throttle. |
| **Authentication, authorization, threat model** | No identity system exists anywhere in the design (FR-5.5). U-01 has no caller identity to check. |
| **Encryption at rest / in transit** | U-01 touches no storage and no network. SECURITY-01 and -02 are U-02's, on C-02 and C-07. |
| **Monitoring, alerting, tracing** | U-01 emits nothing. C-09 is U-02's; distributed tracing is already recorded as N/A for the whole design. |
| **Usability, accessibility, i18n** | No interface. C-06 is U-02's, and its accessibility questions belong to U-02's NFR pass. |
| **Data retention, backup** | U-01 persists nothing. `state: derived` was already decided at Q9c. |
| **RESILIENCY-04 / -14 / -15** | Rollback and deployment style, resiliency testing, incident response — already deferred to **NFR Design**, one stage later. Asking here would move a gate already placed. |
| **Cost / capacity budget** | Estimated at Units Generation (~$10–15/mo, WAF-dominated). U-01 adds no runtime cost; it is code inside a Lambda that would run anyway. |

---

## Part B — Execution checklist (runs after the answers are analyzed)

### B1. Preconditions
- [x] Confirm all eight `[Answer]:` tags are filled
- [x] Run the mandatory Step 5 analysis — vagueness, undefined terms, contradiction, missing detail,
      option-merging, and the rules' specific watch-list ("standard", "typical") — raise a clarification
      file rather than proceeding if any is found
- [x] Record resolved decisions and answer interactions in a `Part A2` section
- [x] If Q1 ≠ B, record the layout change as an amendment to the approved Q3 = A rather than an edit

### B2. `nfr-requirements.md`
- [x] Requirements with IDs, each traced to a source (§4.1–§4.5, an extension rule, or an answer above)
- [x] Performance: the Q8 size ceiling, complexity bounds per function, and the oracle's exclusion
- [x] Maintainability: type checking scope (Q4), the `core/` boundary check, docstring expectations
- [x] Testability: what gates the properties (Q3), the example budget (Q5), and how a failure surfaces
- [x] Security/privacy: the Q6 error-content rule, Q7 parsing choice, SECURITY-14 (JSON only)
- [x] Explicitly mark every Part A1 category **N/A for this unit**, with its reason, so the artifact does
      not read as though the categories were forgotten
- [x] State which requirements are verifiable by an automated check and which are review-only — an NFR
      nothing checks is an aspiration

### B3. `tech-stack-decisions.md`
- [x] The six precedent-established choices, each with its source cited rather than re-argued
- [x] Decisions from Q1, Q2, Q4, Q5, Q7 with rationale and rejected alternatives
- [x] Dependency inventory for U-01 — expected to be **standard library only** at runtime, with pytest,
      Hypothesis and mypy as dev-only. Record that, because a runtime dependency appearing in `core/`
      later is a signal the boundary has been crossed.
- [x] Supply-chain position: U-01's runtime dependency count and how it interacts with US-09 and Q11 = B
- [x] Note the arm64 consequence (Q8 of Units Generation): a pure-stdlib unit has no wheel-availability
      risk, which is the one arm64 concern previously flagged

### B4. Validation and honest reporting
- [x] Every requirement traceable; no requirement without a source
- [x] No requirement contradicts an approved decision, or the contradiction is recorded as an amendment
- [x] Confirm nothing here requires AWS, a clock, an environment read, or I/O in `core/`
- [x] Report anything that cannot be settled here with the stage that carries it

### B5. Completion
- [x] Mark every step `[x]`
- [x] Update `aidlc-docs/aidlc-state.md`
- [x] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present `# 📊 NFR Requirements Complete - U-01 Domain Core` and wait for explicit approval

---

## Part A2 — Resolved decisions (Q1–Q8)

Step 5 analysis. All eight tags filled, all **A**, all clean single selections. Checked specifically
against this stage's watch-list ("standard", "typical", "depends", "mix of") — none appears. No blocking
follow-up raised. Six interactions recorded, **three of which correct something I got wrong or imprecise**.

| # | Decision | Answer |
|---|---|---|
| Q1 | Layout | Adopt `src/` |
| Q2 | Package metadata | One `pyproject.toml` at `blueprints/dashboard/` |
| Q3 | Property gate | Add the suite to `tools/check` |
| Q4 | Type checking | mypy **strict**, scoped to the core package |
| Q5 | Example budget | `max_examples=100` |
| Q6 | Error content | Category only — never a tag value or ARN |
| Q7 | ARN parsing | `str.split(":", 5)` with checks |
| Q8 | Size ceiling | Linear, verified at 10,000 records |

### Interaction 1 — CORRECTION: `tools/check` already runs pytest. My Q3 preamble understated it.

Q3's preamble said `tools/check` "currently lints CloudFormation and validates the registry." That is
incomplete. It already has a `==> builder-mcp tests` block:

```sh
cd packages/builder-mcp && uv run --quiet pytest -q
```

with a comment explaining why it runs *from the package directory* rather than via `uv run --project`:
pytest resolves `testpaths` against its own rootdir, and rootdir follows the invocation directory. The
same comment records that the package's `.python-version` is what makes `uv` fetch a 64-bit CPython.

**This makes Q3 = A materially cheaper than the option text implied.** It is not "add Python testing to a
script that has none" — it is **add a third block mirroring one that already exists and is already
green**. The pattern, including the two non-obvious details above, is there to copy verbatim. The stated
cost ("`tools/check` gets slower for everyone, and it now fails for reasons unrelated to templates") was
already true of this script before U-01 existed.

I should have read the whole script before characterising it. Recorded because the option was chosen
partly on my description of its cost.

### Interaction 2 — `tools/dev` is not a candidate, as promised I would check

Q3 noted `tools/dev` existed and said it was "worth checking whether it is the better host." Checked: it
starts the builder-mcp server and its local browser console for interactive development. It is this
repo's `npm run dev`, not a gate. Wrong host. `tools/check` stands.

### Interaction 3 — Q1 = A amends the approved Units Generation layout

Q3 = A of `unit-of-work-plan.md` is approved and specified flat siblings. Q1 = A supersedes the layout
portion of it. Recorded as **amendment A3**, with a pointer added to `unit-of-work.md` rather than a
silent rewrite — the same discipline applied to A1 and A2.

Checked for knock-on effects: the Dockerfile decision survives unchanged. Context remains
`blueprints/dashboard/`, and only the `COPY` paths move from `core/` to `src/core/`. The grep-able
boundary moves with it and stays a one-line check.

### Interaction 4 — REFINEMENT: a top-level importable named `core` is a bad idea

Q1 = A's tree implies `src/core/`, `src/collector/`, `src/api/` as **three top-level importable
packages**, so U-02's code would `import core`. `core` is about as generic as a distribution name gets,
and a top-level module by that name is a collision risk and gives a reader no clue which project it
belongs to. `builder-mcp` has one package (`src/builder_mcp/`), which is also what hatchling's
`packages = ["src/..."]` config expects.

**Refined to a single package with subpackages:**

```
blueprints/dashboard/src/dashboard/
  core/        U-01
  collector/   U-02
  api/         U-02
```

Imports become `from dashboard.core import group_by_tag`. One installable package, one hatchling target,
no generic top-level name, and the boundary check becomes "no `boto3`, no `os`, no `datetime.now()` under
`src/dashboard/core/`".

This is a naming refinement **within** Q1 = A, not a reversal of it — `src/` is still adopted. Recorded
as a decision I made rather than asked, because the argument is one-sided and it is a detail inside the
answer's own shape. Say so if you would rather have three separate packages.

### Interaction 5 — Q5 = A and Q8 = A collide, and my Q8 wording caused it

Q8 = A says linear behaviour is "verified to 10,000 records **in a property test**." Q5 = A sets
`max_examples=100`. Those do not compose: a Hypothesis property generating 10,000-record snapshots a
hundred times over would dominate the runtime of the gate Q3 = A just added, for a check that does not
need randomness.

**Resolved:** the 10k check is a **single example-based test**, not one of the ten properties and not
Hypothesis-generated. Deterministic input, asserts completion within a generous bound, runs once.

Two consequences worth stating:
- The property set stays at **ten**. The size check is an example-based test alongside them (PBT-10
  already expects example-based tests to complement the properties).
- The quadratic `_reference_group_by_tag` oracle is **excluded** from it. Running the oracle comparison at
  10k would take quadratic time and would measure the test double, not the implementation.

My Q8 text said "property test" where it should have said "test." Recorded rather than quietly fixed,
since the phrase is what you agreed to.

### Interaction 6 — Q6 = A pushes a debugging obligation onto U-02

If U-01 exceptions carry only a category, then when a malformed ARN appears in production, **nothing in
U-01 can tell anyone which resource it was.** That information exists only in the collector, at the
moment it reads the upstream item.

**Cross-unit obligation for U-02**: C-01 must log enough at its own boundary to identify a skipped item —
and it is the right place, because it can decide what is safe to emit into a log group whose retention
and access are U-02's to configure. If U-02 does not do this, Q6 = A's privacy guarantee is intact and
malformed ARNs become undebuggable.

Added to the cross-unit list alongside the two from Functional Design.

### Disclosure — I cannot run the gate I am specifying

Q3 = A and Q4 = A both add steps to `tools/check`, and `tools/check` cannot run in this environment: it
requires `uv` **and** `terraform`, neither of which is installed here (amendment §A1.6). So the test and
type-check steps are specified but **unexecuted**. The first real verification will be whoever runs
`tools/check` on a machine with both, or CI.

Stated plainly rather than left for someone to discover. It is also an argument for keeping the added
blocks structurally identical to the builder-mcp block, which is known-green, instead of inventing a new
invocation shape that has never run.
