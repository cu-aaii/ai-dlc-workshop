# `dashboard` — Cornell cost & usage dashboard

An hourly collector snapshots every resource carrying `cornell:*` tags; a read-only web UI shows the
inventory, groupings, tag gaps and freshness — behind a WAF allowlist and a strict CSP. Serverless,
`us-east-1`: two arm64 Lambda container images, two S3 buckets, an HTTP API, and a CloudFront edge.

**Status: built (U-01 + U-02), not yet deployed to a shared account.** Everything is written and
passes `tools/check`; four requirements can only be confirmed against a running stack (see *Known
limits*).

| Path | What it is | Unit |
|---|---|---|
| `src/dashboard/core/` | Pure domain logic: entities, normalization, grouping, tag-gap classification, freshness, (de)serialization | **U-01** |
| `src/dashboard/collector/` | C-01: paginate the Tagging API, build + write one snapshot | **U-02** |
| `src/dashboard/api/` | C-03: load the snapshot, shape the six states, four read views | **U-02** |
| `src/dashboard/shared/` | stdlib JSON logging + EMF metrics (used by both handlers) | **U-02** |
| `ui/` | C-06: Vite + React static site (served from S3 via CloudFront) | **U-02** |
| `Dockerfile` | Two targets — `collector`, `api` — arm64 Lambda images | **U-02** |
| `infra/dashboard-storage.yml` | Stateful stack: snapshot + site buckets | **U-02** |
| `infra/dashboard.yml` | App stack: Lambdas, HTTP API, CloudFront, WAF, schedule, alarms | **U-02** |
| `infra/dashboard-marker.yml` | Deployment marker (tagged bucket + SSM commit) | U-01 (FR-6) |
| `blueprint.yaml` | Builder manifest → `dashboard.yml` | **U-02** |
| `tests/` | U-01 property suite + U-02 collector/API/template tests | U-01 + U-02 |

## How it works

The **collector** (C-01, EventBridge hourly) pages the Resource Groups Tagging API behind a
declarative `botocore.Config` (explicit timeouts + standard retries), stops at one of three *named*
bounds before the platform timeout can win (page limit / internal deadline / retry exhaustion), asks
U-01 to normalize the items, and writes **one** versioned snapshot with a single `PutObject` —
complete, or not at all. A failed run leaves the previous snapshot intact, alarms via the shared
`notify-topic`, and retries on the next tick (no DLQ). Every derivation — normalize, group, classify,
freshness — is U-01's; the collector never iterates records itself.

The **read API** (C-03, behind API Gateway + CloudFront `/api/*`) is *total*: it loads the snapshot,
classifies it into six states (fresh / stale / empty / no-data / unreadable / invalid), and wraps
everything in one error boundary that maps any escape to a generic 503 with no internals. Metrics are
EMF (a log line — no API call, no IAM, can't throttle the failure path). Logs never carry a tag value.

The **UI** (C-06) is four read-only views sharing one `StateBoundary` that renders the six states —
so "ran and found nothing" never looks like "never ran". Grouping identity is text + a single-accent
bar, never categorical colour (accessible, and it dissolves the palette-exhaustion problem). Strict
CSP, no inline scripts or styles.

## The boundary, enforced not documented

Nothing under `src/dashboard/core/` imports an AWS SDK, reads an environment variable or a clock,
logs, or uses `assert`; `tools/check` greps for all of it. The collector and API *may* do those
things — they are above the boundary — but they delegate every decision about the data back to
`core`. That split is why U-01 has property tests that need no AWS at all.

## Running the checks

```sh
tools/check          # cfn-lint, both test suites, the core boundary grep, mypy, terraform
```

Or directly: `cd blueprints/dashboard && uv run pytest -q` (Python), `cd ui && npm ci && npm test`
(UI). `uv.lock` and `ui/package-lock.json` are committed — reproducibility across laptop, PR checks
and CodeBuild depends on them.

## Operating notes

- **First load after idle is slow (1–3 s).** No provisioned concurrency (TSD-9) — deliberate for a
  dashboard opened a few times a day; a warmer would cost more than it saves and muddy the
  collector-failure signal. This is expected, not broken.
- **"The stack deployed" ≠ "the dashboard works."** Both Lambdas are `HasImage`-gated (TSD-14), so
  the stack comes up before any image exists — buckets, distribution, WAF and API all present, no
  compute. The UI then shows a generic error on every view.
- **The WAF fails closed.** `AllowedIpv4Cidrs` defaults to a documentation range that admits *no one*
  — set real Cornell campus CIDRs (pipeline parameter) or the dashboard is unreachable by design.
- **Runbook (R-10).** Every view shows a generic error right after a first deploy → check the images
  were built and their digests passed. A whole-view error later → check `notify-topic` for the
  collector alarm and the snapshot's age.

## UI conformance

Position against `contracts/ui-design-language.md` in [`docs/design-language.md`](docs/design-language.md):
§2 accessibility and §3 Cornell logo conform with **no exemption path**. **One divergence to relay:**
grouping uses text + a single-accent bar (no categorical colour), which is *more* conservative than
the addendum's two-accent + "Other" series — defensible under §2 (colour is never the sole carrier)
but not this blueprint's file to rewrite. The addendum's authors should decide.

## Design record

`aidlc-docs/` holds the full AI-DLC trail. Business rules: `BR-01`..`BR-08` (U-01) and the
`CR/SR/AR/ER/OR/DR` families (U-02); every public function's docstring names the rule it implements.
