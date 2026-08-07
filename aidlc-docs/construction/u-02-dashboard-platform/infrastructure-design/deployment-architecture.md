# Deployment Architecture — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Infrastructure Design (artifact 2 of 2)
**Date**: 2026-08-04

How the two templates reach the shared account through the existing pipeline. Every mechanism below matches
`pipeline/pipeline.yml` / `pipeline/codebuild.yml` precedent except the **static-site build+sync**, which is
net-new (there is no `s3 sync` anywhere in the repo today). This documents the intended wiring; the actual
`pipeline.yml` / `stacks.yml` edits are written in Code Generation.

---

## 1. The pipeline path for U-02

```
merge to main
  └─ Source
  └─ PipelineDeploy            (pipeline redeploys itself — unchanged)
  └─ Build stage
        ├─ DashboardCollectorContainer   ArmContainerBuildProject, CONTAINER_TARGET=collector
        ├─ DashboardApiContainer         ArmContainerBuildProject, CONTAINER_TARGET=api
        │     → each exports CONTAINER_DIGEST (pipeline/codebuild.yml)
  └─ BlueprintDeploy stage
        ├─ RunOrder 1: DashboardStorage        CFN  dashboard-storage.yml   (buckets exist first)
        ├─ RunOrder 1: DashboardMarker         CFN  dashboard-marker.yml    (independent; flip to pipeline)
        ├─ RunOrder 2: Dashboard               CFN  dashboard.yml           (needs buckets + both digests)
        └─ RunOrder 2: DashboardSiteSync       CodeBuild  build UI + s3 sync (needs site bucket)
  └─ Terraform                 (none for this blueprint)
```

### Why this ordering (Part A2 finding 1 — the correction to Q2)

Q2-A's phrasing said storage and app "deploy in parallel at `RunOrder: 1`." That is wrong in one respect: the site
`BucketPolicy` lives in the **app** stack and calls `PutBucketPolicy` against the named site bucket, which therefore
**must already exist**. So the honest ordering is:

- **`RunOrder 1` — `DashboardStorage`** creates both buckets.
- **`RunOrder 2` — `Dashboard`** (app) and **`DashboardSiteSync`** run *after* storage is `CREATE_COMPLETE`, in
  parallel with each other. The app stack now safely attaches the site bucket policy; the sync now finds the bucket.

The **decision** (policy in the app stack, no export, only data in storage) is unchanged — only the deploy step is
serialized by one `RunOrder`. All cross-stack references remain **by naming convention** (`!Sub`), never
`Fn::ImportValue` — the repo has no exports.

---

## 2. Build stage — two images (and the UI is *not* an image)

Two Build actions, mirroring the `BuilderMcpContainer` shape, both on **`ArmContainerBuildProject`** (the Lambdas are
`arm64`, so the arm project is mandatory — the x86 project would produce an image the functions cannot run):

| Action / Namespace | `CONTAINER_TARGET` | `CONTAINER_CONTEXT` | Exports |
|---|---|---|---|
| `DashboardCollectorContainer` | `collector` | `blueprints/dashboard` (or the src subdir the Dockerfile expects) | `CONTAINER_DIGEST` |
| `DashboardApiContainer` | `api` | same | `CONTAINER_DIGEST` |

`CONTAINER_CONTEXT` must equal where the component actually lives (a stale context fails with a missing-path error
that never mentions the move — a `CLAUDE.md` gotcha). The **UI is a static bundle, not an image** — it is built and
synced in the RunOrder-2 CodeBuild action (§3), not here.

---

## 3. The site build + sync action (§6.4 / Q3) — net-new

A new CodeBuild project (call it `SiteBuildProject`, `node:24-alpine`, no privileged mode — it builds static files,
not images) run by the **`DashboardSiteSync`** action at **`RunOrder: 2`** in `BlueprintDeploy`. Its buildspec:

```
npm ci
npm run build                       # Vite → dist/
aws s3 sync dist/ s3://${Application}-${Environment}-dashboard-site/   # NO --delete (TSD-11 / D-3 / D-4)
```

- **No `--delete`**: deleting at sync time would break a browser mid-rollout still holding a cached `index.html`
  (TSD-11); cleanup is the site bucket's 30-day lifecycle rule (D-4) instead.
- Bucket by **convention name** — `RunOrder: 2` guarantees storage is complete, so the bucket exists; no export.
- The project's role needs `s3:PutObject`/`s3:GetObject`/`s3:ListBucket` on **that one bucket** only, plus its own
  logs — a small addition to the pipeline's IAM, scoped by the `${Application}-${Environment}` convention.
- Alternative B (build in the Build stage as a CodePipeline artifact, sync in a separate action) was rejected for
  the artifact plumbing; the single build+sync action is simpler and the bundle never needs to outlive the sync.

---

## 4. `stacks.yml` registry and the marker flip (DR-02)

Three entries after this stage:

| name | template | deployed_by | note |
|---|---|---|---|
| `dashboard-storage` | `blueprints/dashboard/infra/dashboard-storage.yml` | `pipeline` | **new** — stateful buckets |
| `dashboard` | `blueprints/dashboard/infra/dashboard.yml` | `pipeline` | **new** — app stack |
| `dashboard-marker` | `blueprints/dashboard/infra/dashboard-marker.yml` | **`pipeline`** | **flipped** from `manual` (DR-02) |

The marker flip and each new `pipeline` entry are only legal **because they arrive in the same PR as a matching
BlueprintDeploy action** — `validate_stacks.py` fails a `deployed_by: pipeline` entry with no action (a green PR that
deploys nothing), and `TSD-14`'s `HasImage` is what makes a real, deployable action possible before images exist
(the chain the marker was parked waiting for). `blueprint.yaml` must name a **registered** template (`dashboard.yml`),
written in the same PR.

---

## 5. BlueprintDeploy actions (ParameterOverrides shape)

All four actions use `RoleArn: .../cloudformation-deploy-role`, `ActionMode: CREATE_UPDATE`,
`Capabilities: CAPABILITY_NAMED_IAM`, `StackName: !Sub '${Application}-${Environment}-<name>'`,
`TemplatePath: GitRepositoryArtifact::blueprints/dashboard/infra/<template>`. The load-bearing overrides:

- **`DashboardStorage`** (RunOrder 1): `Application`, `Environment`, `Owner`, `BlueprintVersion`, `SourceCommitId`.
- **`Dashboard`** (RunOrder 2): the above **plus** `CollectorImageUri: "#{DashboardCollectorContainer.CONTAINER_DIGEST}"`,
  `ApiImageUri: "#{DashboardApiContainer.CONTAINER_DIGEST}"`, `AllowedIpv4Cidrs`, `AllowedIpv6Cidrs`, `LogLevel`.
- **`DashboardMarker`** (RunOrder 1): the standard set + `SourceCommitId`.

Every parameter is passed **explicitly** from the pipeline (a `CLAUDE.md` rule) — template defaults exist only so a
stack deploys by hand for debugging. The WAF CIDR lists are the one set of values an operator supplies per
environment; they are pipeline parameters, not template constants.

---

## 6. Partial-state and hand-deploy behaviour (TSD-14 restated for deploy)

Because both Lambdas are `HasImage`-gated, the stacks deploy **before any image exists**: the buckets, the
distribution, the WAF and the API all come up; the two functions and the API integration do not. Consequences,
already anticipated:

- **"The stack deployed" ≠ "the dashboard works."** The UI's network-error row and the R-10 runbook entry
  ("generic error immediately after a first deploy → check the images were built and digests passed") cover it.
- The blueprint **deploys identically by hand and by pipeline** — the notify-topic ARN, both bucket names, and the
  WAF scope are all convention/`!Sub`, so a hand `aws cloudformation deploy` needs no export and no lookup.

---

## 7. Shared infrastructure — none created

`shared-infrastructure.md` is **not** warranted. U-02 **consumes** shared infrastructure — the `notify-topic` SNS
topic (ARN reconstructed, Q4), the shared ECR repo `${Application}-${Environment}`, `ArmContainerBuildProject`, and
`cloudformation-deploy-role` — but **creates none of it**. The one net-new pipeline-level resource, `SiteBuildProject`
(§3), is specific to this blueprint's static-site sync, not shared across blueprints, so it belongs with the pipeline
wiring, not in a shared-infra artifact. Recorded here rather than in a separate file so the absence is a decision, not
an omission.
