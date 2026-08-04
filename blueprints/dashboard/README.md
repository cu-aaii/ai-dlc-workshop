# `dashboard` — Cornell cost & usage dashboard

**Status: incomplete and not deployable.** The pure domain logic (U-01) is written and its test
suite exists. Everything that makes it reachable — the collector, the read API, the site, the edge,
the observability set, and both real CloudFormation templates — is **U-02 work and does not exist
yet**.

What is here today:

| Path | What it is | Unit |
|---|---|---|
| `src/dashboard/core/` | Pure domain logic: entities, normalization, grouping, tag-gap classification, freshness, (de)serialization | **U-01** ✅ |
| `tests/` | Ten property-based tests, generators, example-based tests | **U-01** ✅ |
| `infra/dashboard-marker.yml` | Deployment marker: a tagged bucket and an SSM parameter recording the deploying commit | U-01 (FR-6) ✅ |
| `docs/design-language.md` | UI conformance position against `contracts/ui-design-language.md` | U-02 |
| `blueprint.yaml` | **Absent on purpose** — see below | U-02 |
| `infra/dashboard-storage.yml`, `infra/dashboard.yml` | Snapshot + site buckets; compute, edge, observability | U-02 ❌ |
| `src/dashboard/collector/`, `src/dashboard/api/`, `ui/`, `Dockerfile` | The rest | U-02 ❌ |

## What the domain core does

A scheduled collector will page the Resource Groups Tagging API and write **one** versioned,
encrypted JSON snapshot to S3 — complete, or not at all. A read API will load that snapshot and
derive every view at request time. This package is all of the deciding:

- **Normalization** — raw Tagging API items to records. A malformed item is **skipped and counted**,
  never silently dropped and never fatal: nine usable resources plus one unparseable ARN gives a
  snapshot of nine and a visible count of one.
- **Grouping** by `cornell:deployment-id`, `cornell:owner`, `cornell:blueprint`. Resources lacking
  the key land in an explicit "missing" group, so counts always reconcile.
- **Tag-gap classification** — which of the four required tags each resource lacks. A tag that is
  present but empty, or present with the wrong capitalization, counts as **missing**: such a
  resource is exactly as unattributable as an untagged one, and is genuinely invisible to the
  case-sensitive tooling the convention exists to feed.
- **Freshness** — `FRESH`, `STALE`, or `INVALID`. A `collected_at` in the future is a fault, not an
  age; reporting it as fresh would be the most misleading thing this code could say.

## The boundary, and why it is enforced rather than documented

Nothing under `src/dashboard/core/` imports an AWS SDK, reads an environment variable, reads a
clock, opens a socket, logs, or uses `assert`. `now` and thresholds are always parameters.

`tools/check` greps for all of it. That is what makes ten property-based tests runnable with **no
AWS account, no deployed stack, and no pipeline run** — which is the entire reason this code is a
separate unit from the infrastructure that carries it.

`assert` is on the forbidden list for a specific reason: it is stripped under `python -O`, and the
snapshot accounting identity it would otherwise guard is checked on a production read path.
Invariants here raise `InvalidSnapshot` instead.

## Running the tests

```sh
tools/check          # runs these tests, the boundary grep, and mypy, alongside everything else
```

Or directly:

```sh
cd blueprints/dashboard && uv run pytest -q
```

`uv` fetches the interpreter pinned in `.python-version` and the dev dependencies. **`uv.lock` is
not committed yet** — nothing has run `uv` against this package. The first person to do so should
commit the lockfile, since reproducibility across laptop, PR checks and CodeBuild depends on it.

## UI conformance

The UI is U-02's and unbuilt. Its position against `contracts/ui-design-language.md` is recorded in
[`docs/design-language.md`](docs/design-language.md): §2 accessibility and §3 Cornell logo conform
with **no exemption path**, and the two-accent series ceiling is a live constraint on the grouping
views, since grouping by blueprint or owner will exceed two categories.

## Design record

`aidlc-docs/` holds the full AI-DLC trail — requirements, stories, application design, the unit
decomposition, and per-unit functional/NFR design. The business rules this code implements are
`BR-01`..`BR-08` in
`aidlc-docs/construction/u-01-domain-core/functional-design/business-rules.md`; every public
function's docstring names the rule it implements.
