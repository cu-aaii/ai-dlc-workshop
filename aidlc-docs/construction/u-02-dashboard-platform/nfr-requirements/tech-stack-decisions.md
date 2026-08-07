# Tech Stack Decisions — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → NFR Requirements (artifact 2 of 2)
**Date**: 2026-08-03

Two sections, kept apart deliberately: what the repo already decided, cited rather than re-argued; and
what was decided here, with rationale and rejected alternatives.

---

## Part 1 — Established by precedent

Found by reading `tiny-chatbot`, `aisei-site` and `builder-mcp` before writing this stage's questions.
Re-deciding any of these would create a second convention for no benefit.

| Decision | Value | Source |
|---|---|---|
| Lambda base image | **`public.ecr.aws/lambda/python:3.13`** — supplies the runtime interface client; handler in `${LAMBDA_TASK_ROOT}`; `CMD` names it | `blueprints/tiny-chatbot/Dockerfile` |
| Base image pinning | **By digest** (`@sha256:…`) | `packages/builder-mcp/Dockerfile`. tiny-chatbot records it as owed "in the PR that wires the Build action" — this blueprint does it from the start |
| Lambda packaging | `PackageType: Image`, `ImageUri` as a parameter | both Lambda blueprints |
| Architecture | **arm64** | Units Generation Q8; both blueprints confirm |
| UI build image | **`node:24-alpine`**, multi-stage | `blueprints/aisei-site/Dockerfile` |
| Container build wiring | `CONTAINER_TARGET` + `CONTAINER_CONTEXT` | `pipeline/pipeline.yml` |
| Python toolchain | `uv`, `.python-version` = 3.13, hatchling, pytest, mypy | U-01's TSD-1/2 — **same `pyproject.toml`** |
| Alarm destination | the existing `notify-topic` SNS topic | OR-05 |

**One deliberate divergence from precedent**: `aisei-site` runs a Node server on Lambda via the AWS Lambda
Web Adapter. This blueprint does **not** — the UI is static files in S3 served by CloudFront, so there is
no server to adapt. Recorded because a reader seeing two Lambda blueprints with Node might expect the same
shape here.

---

## Part 2 — Decided at this stage

### TSD-8 — Function sizing

| | Memory | Timeout | Internal deadline |
|---|---|---|---|
| C-01 Collector | 512 MB | **120 s** | **≈100 s → `UPSTREAM_TOO_SLOW`** |
| C-03 Read API | 512 MB | 10 s | — |

From Q1 = A, plus the internal deadline from Part A2 Interaction 1.

> **⚠️ REFINED at NFR Design (Q2 = A, 2026-08-03).** The "≈100 s" internal deadline is a *guessed constant*
> here; NFR Design refined the **mechanism** to a value derived from `context.get_remaining_time_in_millis()`
> less a fixed safety margin, so the 120 s timeout becomes the single source of truth. The numeric intent is
> unchanged at the default timeout. Original wording preserved above; see
> `u-02-dashboard-platform/nfr-design/nfr-design-patterns.md` §2 and the plan's Part A2 Interaction 1.

**Why 512 MB for work that may need 256**: memory buys CPU, so a larger size can finish proportionally
faster and cost the same or less. At 24 collector invocations a day the absolute figure is cents either
way, and the risk being bought off — a timeout mid-pagination — is one the design specifically wanted to
avoid.

**The internal deadline is not redundant with the timeout.** 50 pages and 120 s are independent bounds, and
whichever fires first decides whether the failure has a name. Past ~2.4 s per page the platform timeout
wins and produces an unattributable failure. Raising `UPSTREAM_TOO_SLOW` at ~100 s guarantees the
collector always fails with a reason CR-04 can log and the runbook can act on.

**Rejected**: 256 MB / 60 s (a 60 s ceiling makes the timeout the *likely* bound rather than the unlikely
one); 1024 MB / 300 s (five minutes of runaway before the platform intervenes, when bounding runaway was
the point).

### TSD-9 — No provisioned concurrency

From Q2 = A. Cold starts of 1–3 s on the API are accepted.

Provisioned concurrency bills for warm capacity continuously. For a dashboard opened a few times a day it
would roughly rival the WAF web ACL charge that already dominates the ~$10–15/month estimate — **a poor
result for a blueprint whose entire purpose is cost visibility**.

**Rejected**: a scheduled warmer, which is a cron job whose only purpose is defeating a platform behaviour,
and which would add invocations that do no work and muddy the collector-failure signal.

**Consequence to write down**: the README should say the first load after idle is slow, so it reads as
expected rather than broken.

### TSD-10 — Throttling as a parameter, 20 rps / burst 40

From Q3 = A. The threat model is **not** an attacker — the WAF allowlist restricts origin — it is an
accidental refresh loop or a script from one workstation inside the allowlist.

**Being a parameter matters more than the number.** Twenty people opening the dashboard and clicking
through four views produces up to ~80 requests in a short window, which will clip the burst. The
mitigations only exist because the value is a parameter: warm the dashboard once before a demo, and raise
the limit temporarily if a large simultaneous audience is expected (Part A2 Interaction 5).

### TSD-11 — Cache strategy: hashed assets immutable, `index.html` short, no invalidation

From Q4 = A.

Vite emits content-hashed filenames, so those objects are immutable and safe to cache for a year.
`index.html` references them and gets 60 s.

**Chosen because it is self-correcting and has no step to forget.** An invalidation step can fail
independently, costs money beyond the free tier, and — worst — if someone omits it for a future asset path,
the failure mode is a **stale UI**: confusing rather than loud. The hashed-asset pattern cannot be
forgotten because it is structural.

**Paired requirement**: the site sync runs **without `--delete`**, and cleanup is a 30-day lifecycle rule
instead (D-3, D-4). Deleting old assets at sync time would break any browser mid-rollout still holding a
cached `index.html` — the exact failure this strategy avoids.

### TSD-12 — Retention: 30 days, everywhere

From Q5 = A. Lambda log groups, CloudFront access logs, WAF logs.

Two different justifications behind one number, worth separating:

- **Lambda logs** — a cost-and-forensics trade. By CR-04's design they hold ARNs and reason codes but **no
  tag values, so no NetIDs**.
- **Access and WAF logs** — a **personal-data** decision. These contain source IPs. Shorter retention is a
  feature, not a saving, and extending it would need a reason beyond convenience.

### TSD-13 — Lifecycle on both buckets

From Q6 = A, extended by Part A2 Interaction 2.

| Bucket | Rule |
|---|---|
| Snapshot | **Non-current** versions expire after 30 days. The current version is never expired. |
| Site | Objects not modified for 30 days expire. |

Version history exists so a bad snapshot can be inspected or rolled back, and that need is measured in
hours. The snapshot is `state: derived` and fully rebuildable by re-running the collector, so there is
little to archive. Without these rules, hourly writes give ~8,760 versions a year growing without bound —
which is awkward to explain on a dashboard whose purpose is cost visibility.

### TSD-14 — `Condition: HasImage` on both Lambdas

From Q7 = A, following `tiny-chatbot`.

Both functions are declared conditionally on an `ImageUri` parameter being supplied, so **the stack deploys
successfully before any image has ever been built**.

**Three things this buys:**

1. The **first** deployment works. Without it, day one fails on an unresolvable `ImageUri`.
2. The stack deploys by hand for template debugging, which `CLAUDE.md` explicitly wants ("a blueprint
   should deploy identically by hand and by pipeline").
3. **It unblocks `blueprint.yaml`.** Code Generation recorded the manifest as stuck: a manifest must name a
   registered template, a `deployed_by: pipeline` entry needs a matching action, and without a deployable
   stack there was no legal chain. `HasImage` breaks the first link, so `dashboard.yml` can be registered
   `pipeline` with a real action from the first PR (Part A2 Interaction 3).

**The cost, stated plainly**: a stack can exist with **no compute at all** — no collector, no API — with
the `/api/*` CloudFront origin pointing at an API Gateway that has no integration. So **"the stack
deployed" stops implying "the dashboard works."**

Two mitigations, both already in place: the UI's row 6 (network failure / non-JSON) renders this as a
generic error rather than something incoherent; and R-10's runbook gains an entry — *"every view shows a
generic error immediately after a first deployment → check whether the images have been built and their
digests passed."*

### TSD-15 — Availability recorded, not engineered

From Q8 = A. Best-effort, single region, no SLA, no multi-AZ work, no canary.

Every component is multi-AZ without configuration, so there is nothing to build. Recorded so a later
reader does not assume an SLA exists. The design's real availability property is A-4: a collector failure
leaves the previous snapshot intact and the UI degrades to *labelled stale*.

**Rejected**: a measured objective, because measuring it needs a synthetic canary and RESILIENCY-06 already
recorded that as N/A — the endpoint is WAF-restricted and not publicly reachable. An objective nobody
measures is worse than none.

---

## Dependency inventory

| Scope | Dependencies |
|---|---|
| **U-01 (imported)** | **none — standard library only** |
| C-01 Collector | `boto3` |
| C-03 Read API | `boto3` |
| C-06 Web UI | React, Vite, and their transitive tree |
| Dev / test | `pytest`, `hypothesis`, `mypy` (shared with U-01) |
| Base images | `public.ecr.aws/lambda/python:3.13` (digest-pinned), `node:24-alpine` (build only) |

U-01's runtime dependency row stays **empty**, and `tools/check`'s boundary grep enforces it. A dependency
appearing under `src/dashboard/core/` is a boundary violation, not a dependency decision.

## Supply-chain position (US-09, SECURITY-10, Q11 = B)

| Ecosystem | Pinned | Scanned | SBOM |
|---|---|---|---|
| Python (`uv.lock`) | ✅ with hashes | ✅ | ✅ |
| Base images | ✅ by digest | ✅ | ✅ |
| **npm** | ✅ `package-lock.json` | ❌ | ❌ |

The asymmetry is Q11 = B, chosen deliberately, and its exposure was recorded at Application Design §6.2:
React + Vite is the **largest** dependency tree in the blueprint and receives the **least** scrutiny.
Defensible — npm here is build-time only and invisible to a runtime image scan, and exact pinning is the
main lever against a *changed* dependency. The residual risk is a build-time dependency compromised at a
pinned version, which can inject into the delivered bundle.

**Live context**: the repo's default branch currently reports **51 Dependabot findings (20 high)**. Not
this blueprint's, but it is what the existing dependency posture looks like, and it is the concrete
argument behind the still-open **Q13** (whether US-09's fourth acceptance criterion narrows to match
Q11 = B).

---

## Carried to Infrastructure Design

| Item | Why not settled here |
|---|---|
| **§6.4** site-sync ordering | Pipeline topology. Likely: emit the bundle as a CodePipeline artifact, sync at `RunOrder: 2` inside `BlueprintDeploy` |
| **WAF IPv6** | IPSets are per-address-family; an IPv4-only allowlist silently locks out IPv6-only clients. Two IPSets, or a documented IPv4-only scope |
| **notify-topic ARN mechanism** | Its outputs carry no `Export:`, so parameter or naming convention |
| API reserved concurrency (S-2) | A number, alongside the rest of the sizing |
| Resource-by-resource template shape | Infrastructure Design's whole job |
| Exact CSP directive string | Belongs with the response-headers policy |
