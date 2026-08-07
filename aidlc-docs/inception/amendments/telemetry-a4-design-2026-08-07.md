# Amendment A4 — two FR-9 clauses corrected by Application Design

**Date**: 2026-08-07
**Stage**: INCEPTION → Application Design (FR-9/FR-10 pass)
**Amends**: A2 (`telemetry-fr9-2026-08-07.md`), already corrected once by A3
**Cause**: not new information — **two clauses in A2 could not be built as written**, and design is
where that surfaced.

## A4.1 — FR-9.5.3: "additive sibling section" → three per-section objects

**A2 said** (FR-9.5.3): *"Telemetry MUST land in the snapshot as an **additive sibling section**, under
the existing `schema_version` scheme, not as a parallel versioning string and not as a migration."*

**Why it cannot be built that way.** FR-10.4 puts cost collection on a **daily** schedule while
inventory and telemetry are **hourly**. Three sections in one S3 object therefore means the daily
writer must read the current object, splice in its section, and write the whole thing back — a
**read-modify-write**. Two problems:

1. C-01's design forbids it in terms — `components.md` C-01, and the shipped code comment: *"single
   `put_object` (complete-or-fail, CR-05, **no read-modify-write**)"*.
2. Two writers on one object lose updates when they overlap, and S3 offers no compare-and-swap here.
   The window is small and the failure is silent, which is the worst combination.

**Now**: `C-02` holds **three objects, one owner each** — `inventory/current.json` (C-01, hourly),
`telemetry/current.json` (C-11, hourly), `cost/current.json` (C-10, daily). Every write stays a single
complete-or-fail `PutObject`; no writer reads another's data; isolation is enforced by per-role IAM
scoped to one key.

**What A2 got right and this keeps**: telemetry is still *additive* — no existing consumer changes, and
nothing migrates. The `schema_version` headroom C-02 reserved is simply spent per-object rather than
inside one.

**Consequence, and it is an improvement**: `collected_at` becomes **per section**. There is no single
snapshot age, because there genuinely isn't one — cost is 24–48h stale (A3), inventory an hour. One
timestamp over all three would have misstated two of them. The UI must show three ages; US-16's
"as of the last finalized day" criterion already anticipated this for cost.

## A4.2 — FR-9.4 / FR-9.5.2: the declaration had no path to the reader

**A2 said**: a blueprint declares its counters in **`blueprint.yaml`** (FR-9.4), and the reader MUST
read **only** declared counters — a closed allowlist (FR-9.5.2, NFR-T5).

**The gap**: `blueprint.yaml` lives in **git**; the reader is a **Lambda**. It cannot read the repo,
this repo has no runtime config distribution, and `validate_stacks.py` is a PR-time check rather than a
deploy-time publisher. A2 specified both ends of the contract and no middle — a real omission, not a
detail, because FR-9.5.2 is unimplementable without it.

**Now** (plan Q2 = A), the contract gains **C-14 Declared-Counter Catalog**, and the allowlist is
honoured differently for each of the two metric sources:

| Source | Allowlist mechanism |
|---|---|
| `Cornell/Blueprints/*` (blueprint-emitted) | A **pipeline build step** walks `blueprints/*/blueprint.yaml`, extracts each `telemetry:` block into one catalog JSON, and bakes it into the image. A pure parser reads it. Missing block ⇒ `emits: false` (FR-9.4.2). |
| `AWS/Bedrock`, `AWS/Bedrock-AgentCore` (AWS-emitted, per A3.1/A3.2) | A **fixed, module-level constant** in code. AWS's metrics are declared in no manifest, so a catalog cannot cover them; closing the set in code is what makes NFR-T5 true here. Only `ModelId` **dimension values** are discovered — never which metrics to read. |

**Accepted tradeoff**: a blueprint that starts emitting is invisible until the dashboard is next
deployed. Acceptable because a merge to `main` redeploys everything, so the lag is one pipeline run.
The rejected alternative (each blueprint publishing to SSM at deploy time) is better on freshness but
requires editing **every other blueprint's template** — the cross-track work T6 explicitly declined.

## Unchanged

Every T1–T8 decision; FR-9.1–9.3, 9.6, 9.7; all of FR-10 including FR-10.3.6 (A3's unattributed-group
trap); NFR-T1–T8. A3's corrections all stand.

## Story impact

None. No US-16…US-25 criterion is invalidated: they were written against observable behaviour rather
than storage layout, which is why a change of this size touches no story. US-16's per-section age and
US-17's unattributed-group criteria happen to fit A4.1 and A3.3 without edits.
