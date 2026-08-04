# Units of Work — `dashboard` Blueprint

**Stage**: INCEPTION → Units Generation, Part 2 (artifact 1 of 3)
**Date**: 2026-08-03
**Decisions**: `inception/plans/unit-of-work-plan.md` Part A2 (Q1–Q9, all **A**)
**Baseline**: `inception/amendments/repo-baseline-2026-08-03.md` applies — the container build now
works on arm64, `blueprint.yaml` is a parsed contract, and there is no mandatory PR approver.

---

## Two units

| ID | Unit | Owns | Verifiable without AWS? |
|---|---|---|---|
| **U-01** | Domain Core | C-04 Inventory Model, C-05 Aggregation Core | **Yes — entirely** |
| **U-02** | Dashboard Platform | C-01, C-02, C-03, C-06, C-07, C-08, C-09, both templates, `blueprint.yaml`, and the `pipeline.yml` / `stacks.yml` edits | No |

The split is on that last column, and only that column. Every other boundary the design contains —
the S-01/S-02 failure-domain seam, the collector/API separation, the edge — is a **runtime** boundary
that does not change how the work gets done or checked. This one does: U-01 can be written and proven
on a laptop with no AWS account, no deployed stack, and no pipeline run. U-02 cannot.

Two units also means two CONSTRUCTION passes rather than four, which was the stated cost driver during
a live workshop.

---

## U-01 — Domain Core

**Purpose**: every decision the dashboard makes about its data, as pure functions.

**Owns**
- C-04 Inventory Model — `ResourceRecord`, `Snapshot`, `normalize_resource`, `build_snapshot`,
  `serialize_snapshot`, `deserialize_snapshot`
- C-05 Aggregation Core — `group_by_tag`, `classify_tag_gaps`, `evaluate_freshness`, and the
  test-only `_reference_group_by_tag` oracle

**Explicitly does not own**
- Any AWS call, client, credential, or ARN construction
- Any clock read — `now` is a parameter, never `datetime.now()`
- Any environment or config read — thresholds arrive as arguments
- Any HTTP concern, status code, or response shape
- Any file, socket, or subprocess

**Responsibility boundary a reviewer can check**: there is **no `import boto3`, no `import os`, and no
`datetime.now()` anywhere under `blueprints/dashboard/core/`.** That is grep-able, so the boundary is
enforceable rather than aspirational — which matters because ten blocking PBT rules depend on this
code being separable from AWS.

**Verification method**: property-based tests plus unit tests, run locally. No account, no stack, no
image, no pipeline. This is the entire reason U-01 exists as a unit.

**Properties it must satisfy** (from `component-methods.md`)
- Round-trip: `deserialize_snapshot(serialize_snapshot(s)) == s`
- Serialization determinism: equal snapshots produce identical bytes
- Grouping invariant: group sizes sum to the total; every resource in exactly one group
- Grouping oracle: matches `_reference_group_by_tag`
- Grouping idempotence: regrouping by the same key is a no-op
- Gap classification: a record is incomplete **iff** it lacks ≥1 of the four required tags

**Why it goes first** (Q5 = A, depth-first): U-02 imports it. Finishing U-01 with its properties
passing means the riskiest infrastructure work is built on logic already proven correct, rather than
proven concurrently with it.

---

## U-02 — Dashboard Platform

**Purpose**: everything that makes U-01's logic reachable, scheduled, protected, deployed, and
observable.

**Owns**

| Group | Contents |
|---|---|
| Compute | C-01 Tag Inventory Collector, C-03 Inventory Read API — both arm64 container images |
| Storage | C-02 Snapshot Store; the site bucket |
| Presentation | C-06 Web UI (React + Vite) |
| Edge | C-07 CloudFront distribution, WAF web ACL, response headers policy |
| Identity of the deployment | C-08 Deployment Marker (FR-6) |
| Observability | C-09 alarms, metrics, log groups, dashboard |
| Templates | `dashboard-storage.yml`, `dashboard.yml` |
| Contract | `blueprints/dashboard/blueprint.yaml` |
| Shared-file edits | `pipeline/stacks.yml` entries; `pipeline/pipeline.yml` Build action + BlueprintDeploy action(s); root `Dockerfile` targets |

**Explicitly does not own**
- Any grouping, classification, freshness, or serialization logic — all of it is U-01's, imported
- A write path from the UI (FR-4.5)
- An on-demand collection trigger (FR-2.1, US-07)
- Cost computation (FR-8, deferred)

**Responsibility boundary a reviewer can check**: no function in U-02 reimplements anything U-01
exports. If a grouping loop appears in the API handler, the boundary has been crossed.

**Verification method**: deployed stack plus pipeline run. Its two silent-failure modes — a partial
snapshot written as if complete, and an inverted cache policy serving stale JSON — are not detectable
by lint, which is the substance of Q6 = A's answer.

**Why it is one large unit rather than three**: the alternatives split it along runtime seams
(collector vs. API) or along a risk seam (platform wiring) that the 2026-08-03 amendment substantially
retired. Neither would change how any of the work is verified, and each would add a full CONSTRUCTION
pass mid-workshop.

**Acknowledged cost**: U-02's Functional Design and Infrastructure Design documents will be long, and
one Code Generation pass covers two Lambdas, a React app, an edge configuration, two templates, and a
pipeline edit. This was stated as the price of Q1 = A and is accepted, not discovered.

---

## Code organization (Q3 = A)

```
blueprints/dashboard/
  blueprint.yaml      manifest parsed by builder_mcp/catalog.py — required, or the
                      blueprint is invisible to the Cornell Builder
  infra/
    dashboard-storage.yml   snapshot bucket, site bucket        (Q4 = A)
    dashboard.yml           compute, edge, observability, marker
  core/               U-01. No boto3, no os, no datetime.now() beneath here.
  collector/          U-02. C-01 handler. No Dockerfile here — see below.
  api/                U-02. C-03 handler. Likewise.
  ui/                 U-02. package.json, package-lock.json, vite config, src/
  tests/              properties for U-01; integration for U-02
```

**Dockerfiles live at the repo root, not here.** The established pattern (`Dockerfile` on `main`) is
one `FROM ... AS <target>` per component with the repo root as build context, selected by
`CONTAINER_TARGET` in the Build stage action. This blueprint adds two targets —
`dashboard-collector` and `dashboard-api` — rather than two Dockerfiles.

**`core/` is the enforceable boundary.** A single grep in `tools/check` or CI keeps §4.5 true as the
code grows. Recorded as a concrete suggestion for Infrastructure Design, not as an existing check.

---

## `blueprint.yaml` values (Q9)

| Field | Value | Basis |
|---|---|---|
| `data_classification` | `[internal]` | The dashboard exposes resource ARNs, owner NetIDs, and deployment ids. `[public]` — hello-world's value — is not defensible for that content. `[internal]` is consistent with the only access control the design has: a WAF allowlist of Cornell IP ranges. |
| `singleton` | `false`, with a `DeploymentName` parameter | Follows hello-world's own comment that "Real blueprints should take a `DeploymentName` parameter instead." Propagates into both templates' resource and stack names; both must still match `aidlc-<env>-*`. |
| `state` | snapshot = `derived` | The snapshot is fully rebuildable by re-running the collector. This makes the manifest agree with RESILIENCY-02's RTO/RPO N/A, which already rests on exactly that reasoning. Nothing here is `authoritative`; nothing needs backing up. |
| `cost` | see below | Q9d = A — a real estimate, recorded as an estimate |
| `matches` | intent phrases | e.g. "see what's deployed", "cost and usage dashboard", "find untagged resources", "who owns this resource" |
| `inputs` | `owner_netid`, `deployment_name` | The builder-facing contract. Both are required; neither is a credential. |

### Cost estimate

**Estimate: roughly $10–15/month baseline, at this design's scale, dominated by a single fixed charge.**

| Component | Basis |
|---|---|
| AWS WAF web ACL | **The dominant cost.** A fixed monthly charge per web ACL plus a smaller one per rule, incurred whether or not anyone visits. |
| CloudFront | Effectively free at workshop traffic; the free tier covers it. |
| Lambda ×2 | One scheduled invocation per interval plus a handful of reads. Rounds to nothing. |
| S3 | One JSON object of tens of KB, plus a small static bundle. Cents. |
| API Gateway HTTP API | Per-request; rounds to nothing. |
| EventBridge | Scheduled rules are free. |
| CloudWatch | A few alarms and two log groups with retention set — low single-digit dollars. |

`scales_with`: `[resource_count, refresh_interval, page_views]` — though none of the three moves the
total much, because the total is a fixed charge.

**Stated as an estimate, not a measurement.** It has not been billed. The honest headline is that the
figure is *fixed-cost dominated*, so it barely varies with use — and that it is emphatically **not
`$0`**, which is what copying hello-world would have declared for a blueprint whose purpose is cost
visibility.

---

## Carried forward, unresolved

**§6.4 — the site bundle reaches a bucket that does not exist yet.** Still open. Q4 = A does **not**
resolve it: the pipeline order is `Source → PipelineDeploy → Build → BlueprintDeploy`, and
`PipelineDeploy` deploys only the pipeline's own stack, so a storage stack registered as a
`BlueprintDeploy` action still comes after the Build stage. My Q4 text claimed otherwise and was wrong;
the correction and the three-option table are in `unit-of-work-plan.md` Part A2, Interaction 1. **Owner:
U-02, decided at Infrastructure Design.** Likely resolution (b): Build emits the bundle as a
CodePipeline artifact, and a `SiteSync` action runs at `RunOrder: 2` inside `BlueprintDeploy`.

**US-15 story-coverage gap.** US-15 does not mention the Build stage action, the `Dockerfile` targets,
or `blueprint.yaml`. Unchanged since Workflow Planning, and cheaper to close now that the Build stage
exists. **Owner: U-02**, carried by Infrastructure Design and Code Generation. No story amendment
proposed; the user may request one.

**Q12/Q13** (`application-design-plan-clarification-2.md`) — whether `requirements.md` §4.6 gains a
fifth accepted exception for the npm scanning decision, and whether US-09's fourth acceptance criterion
is narrowed. Open, non-blocking, independent of decomposition. **Owner: U-02** if answered.

**RESILIENCY-04, -14, -15** — rollback mechanism and deployment style, resiliency testing approach,
incident response. Deferred to NFR Design by the extension's own scoping. Now interacts with amendment
§A1.1: RESILIENCY-04's change-management context lost its human approval gate.

**`tools/check` cannot run in the current environment** — it needs both `uv` and `terraform`, neither
installed. Blocking for U-02's Build and Test, not for U-01's.

---

## Ownership and review (Q6 = A)

One PR per unit. **A human review is requested even though branch protection no longer requires one** —
per amendment §A1.1, zero approving reviews are needed and a team member may merge their own PR.

The reason this is a choice worth making rather than ceremony: `validate` runs `cfn-lint` and
`validate_stacks.py`. It will catch an unregistered template, a registry entry with no action, and a
malformed template. It cannot see

- a WAF allowlist that excludes the people who need access (looks like an outage),
- a cache policy inverted so `/api/*` is cached (serves stale JSON under a fresh timestamp),
- an IAM policy scoped to `*` instead of one object key,
- a collector that writes a partial snapshot and reports success.

Those four are the failures this design spent the most effort guarding against, and not one of them
fails a lint. `validate` being the only automated gate is precisely why a human should look.
