# Infrastructure Design Plan — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Infrastructure Design (plan)
**Date**: 2026-08-04
**Prereqs**: Functional Design ✅, NFR Requirements ✅, NFR Design ✅ (all U-02 approved)

This stage maps the 12 logical components (`nfr-design/logical-components.md`) to concrete `us-east-1`
CloudFormation, and resolves the six items NFR Design routed here. It stops at the template *shape* and the
pipeline wiring — the actual handler/UI/Dockerfile code is Code Generation.

## What the precedent survey found (grounding for the questions below)

Read `tiny-chatbot/infra/tiny-chatbot.yml`, `aisei-site`, `notify-topic/infra/notify-topic.yml`,
`pipeline/pipeline.yml`, `pipeline/codebuild.yml`, `pipeline/stacks.yml`, `blueprints/dashboard/infra/dashboard-marker.yml`.

- **A Lambda-container skeleton to mirror exists** (`tiny-chatbot.yml`): param **`ContainerImageUri`** (not
  `ImageUri`), `Conditions: HasImage: !Not [!Equals [!Ref ContainerImageUri, '']]` applied to every resource,
  four `cornell:*` tags as a **list** of `Key`/`Value`, an explicit `AWS::Logs::LogGroup` (`RetentionInDays: 30`),
  an exec role scoped to that log group ARN, and `deployment-id` **derived** as `!Sub '${Application}-${Environment}-${DeploymentName}'` (no `deployment-id` parameter). Params: `Application` (`[a-z0-9-]{1,10}`), `Environment` (`[a-z0-9]{1,4}`), `Owner`, `BlueprintVersion`, `DeploymentName`, `ContainerImageUri`.
- **The entire serving layer is net-new.** No `CloudFront`, no `WAFv2`, no `ApiGatewayV2`, no `OriginAccessControl`,
  no `ResponseHeadersPolicy` exists anywhere in the repo. `aisei-site` is a Lambda **Web Adapter** blueprint (public
  Function URL), *not* a static S3 site — so only the skeleton transfers, not the serving shape.
- **No CloudFormation exports anywhere** (`Export:`/`Fn::ImportValue` return nothing). `notify-topic` publishes
  `TopicArn`/`TopicName` as plain Outputs, **not exported**; its name is the fixed convention
  `${Application}-${Environment}-notify-topic`.
- **Pipeline**: container Build actions use `ArmContainerBuildProject` + `CONTAINER_TARGET`/`CONTAINER_CONTEXT`;
  the buildspec exports `CONTAINER_DIGEST`, referenced downstream as `#{Namespace.CONTAINER_DIGEST}`. BlueprintDeploy
  CloudFormation actions all run at `RunOrder: 1` (parallel), `StackName: ${Application}-${Environment}-<name>`,
  `RoleArn: .../cloudformation-deploy-role`, `CREATE_UPDATE`, `CAPABILITY_NAMED_IAM`. **No `aws s3 sync` and no
  static-bundle build action exist** — site sync is net-new.
- **`dashboard-marker.yml` already documents the split**: the snapshot and site buckets belong in a separate
  `dashboard-storage.yml` "so an application update cannot replace the stack that owns the data." `stacks.yml`
  carries `dashboard-marker` as `deployed_by: manual` on purpose (no action yet).

---

## Questions (answer each `[Answer]:` line; "A" is the recommended option)

### Q1 — Template split
How many CloudFormation templates does U-02 ship?

- **A. (Recommended)** Two: **`dashboard-storage.yml`** (the two S3 buckets only — the stateful data) and
  **`dashboard.yml`** (everything else: both Lambdas, HTTP API, CloudFront, WAF, schedule, alarms, log groups).
  Each gets its own `stacks.yml` entry and its own BlueprintDeploy action. Cross-references are by **naming
  convention** (`!Sub`), never `Fn::ImportValue` (there are no exports). This is exactly what `dashboard-marker.yml`
  already says the design is.
- **B.** One `dashboard.yml` with all resources. Simpler wiring, but a stack *update* that replaces a resource
  could threaten the buckets — the risk the split exists to remove.

`[Answer]`: A

### Q2 — Breaking the OAC cross-stack cycle
CloudFront Origin Access Control needs the **site bucket** to grant the **distribution** read access via a
bucket policy — but the bucket is in `dashboard-storage.yml` and the distribution is in `dashboard.yml`, and there
are no exports. Where does the `AWS::S3::BucketPolicy` live?

- **A. (Recommended)** In **`dashboard.yml`** (the app stack), alongside CloudFront + the OAC. It references the
  **convention-named** bucket (`!Sub '${Application}-${Environment}-dashboard-site'`) and the **local** distribution
  ARN in the `AWS:SourceArn` condition. A bucket *policy* is not stateful data, so it belongs with the distribution
  that shapes it; the storage stack keeps only the bucket itself. This breaks the cycle with no export and lets both
  stacks deploy **in parallel at `RunOrder: 1`** (the repo's BlueprintDeploy default).
- **B.** Keep the policy in `dashboard-storage.yml` and pass the distribution ARN in as a parameter — forces
  app-before-storage ordering and a param wire the convention-name approach avoids.

`[Answer]`: A

### Q3 — Static site build + sync (the §6.4 item)
The UI is a Vite/React static bundle; there is no build-artifact or `s3 sync` precedent. How does the bundle reach
the site bucket, and when?

- **A. (Recommended)** One net-new CodeBuild action (`node:24-alpine`) in the **BlueprintDeploy stage at
  `RunOrder: 2`**: it runs `npm ci && npm run build` then `aws s3 sync dist/ s3://${Application}-${Environment}-dashboard-site/`
  **without `--delete`** (TSD-11 / D-3 / D-4). `RunOrder: 2` guarantees every stack (incl. storage) is `CREATE_COMPLETE`
  first, so the bucket exists; the convention name means no export. Cleanup is the 30-day lifecycle rule, not `--delete`.
- **B.** Build the bundle in the **Build stage** as a CodePipeline output artifact, then a separate `RunOrder: 2`
  sync action consumes the artifact. (The shape NFR Design anticipated — more plumbing, same result.)
- **C.** A Lambda-backed custom resource inside the stack populates the bucket. Rejected: most complex, ships code
  to do a copy.

`[Answer]`: A

### Q4 — notify-topic ARN mechanism (the alarm destination)
The CloudWatch alarms publish to the shared `notify-topic`, which exports nothing. How does U-02 obtain its ARN?

- **A. (Recommended)** Reconstruct it in-template with `!Sub 'arn:${AWS::Partition}:sns:${AWS::Region}:${AWS::AccountId}:${Application}-${Environment}-notify-topic'`.
  The name is a deterministic convention (singleton blueprint), so no parameter and no export are needed, and the
  stack **deploys identically by hand and by pipeline** (a `CLAUDE.md` requirement).
- **B.** Pass the topic ARN as an explicit pipeline `ParameterOverride`. Works, but adds a wire for a value the
  convention already fixes, and a hand deploy then needs the ARN supplied.

`[Answer]`: A

### Q5 — WAF IPv6 (the allowlist address-family gap)
WAFv2 IPSets are per-address-family; an IPv4-only allowlist silently locks out IPv6-only campus clients.

- **A. (Recommended)** **Two IPSets** — one `IPV4`, one `IPV6` — both fed by parameters (CIDR lists), referenced by
  an OR of two statements in the deny-by-default WebACL (`Scope: CLOUDFRONT`, us-east-1). The IPv6 list may start
  **empty**; the IPSet still exists, so adding CIDRs later is a parameter change, not a template change.
- **B.** One IPv4-only IPSet, with the IPv6-only-lockout documented as accepted scope. Simpler, but a silent
  denial for anyone on IPv6-only — the exact trap NFR Design flagged.

`[Answer]`: A

### Q6 — API reserved concurrency (the S-2 number)
The collector is settled at reserved concurrency **1** (S-1). What cap does the read API get?

- **A. (Recommended)** **Reserved concurrency 10.** The API Gateway throttle (P-5: 20 rps / burst 40) is the primary
  limiter; 10 sits comfortably above steady-state for a sub-second handler, caps the **shared-account** concurrency
  pool, and if exceeded fails as a clean 503 (AR-06) — degrade, not crash.
- **B.** **20**, matching the rps ceiling for more burst headroom, at the cost of a larger claim on the shared pool.
- **C.** No reservation — rely solely on the API Gateway throttle. Simplest; no account-pool protection.

`[Answer]`: A

### Q7 — Content-Security-Policy + security headers (the exact string)
The constraint (SEC-2: no `unsafe-inline`, no `unsafe-eval`) is fixed; the directive string is not. Applied via a
CloudFront `ResponseHeadersPolicy`.

- **A. (Recommended)** Strict, and impose the matching UI constraint on Code Generation:
  `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'`
  plus HSTS (`max-age=63072000; includeSubDomains; preload`), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`. Code Generation must then emit **no inline `<script>`/`<style>` and no inline
  `style=` attributes** (classes + hashed CSS files only). Whether the built bundle actually complies is a
  **`deployed`-only** check — consistent with §9's honesty about P-6/SEC-2.
- **B.** Same headers but `style-src 'self' 'unsafe-inline'`, to tolerate React inline style attributes — relaxes
  SEC-2. Choose only if the UI genuinely needs runtime inline styles.

`[Answer]`: A

---

## Part A1 — Mandatory category dispositions

Every category the vendored rule requires, with where it is decided. "Settled" = fixed at an earlier approved
stage; "here" = this stage; "routed" = deferred with owner.

| Category | Disposition |
|---|---|
| **Deployment Environment** | **Settled**: `us-east-1`, CloudFormation via CodePipeline `BlueprintDeploy`, `Environment=main`, stack names `${Application}-${Environment}-<name>`, `cloudformation-deploy-role`. Nothing to decide. |
| **Compute** | **Settled**: two arm64 container Lambdas, `ContainerImageUri` + `Condition: HasImage` (TSD-14), sizing collector 512 MB/120 s & API 512 MB/10 s (TSD-8), collector reserved concurrency 1 (S-1), no provisioned concurrency (TSD-9). **Here**: API reserved concurrency (**Q6**). |
| **Storage** | **Settled**: two S3 buckets, versioning + BPA + encryption, lifecycle/retention (TSD-12/-13, D-1..D-7), single snapshot key. **Here**: two-template split & OAC policy placement (**Q1**, **Q2**). |
| **Messaging** | **Settled**: EventBridge hourly schedule → collector, `MaximumRetryAttempts: 0`, no DLQ (Q6/NFR). **Here**: notify-topic ARN mechanism (**Q4**). No queue by decision. |
| **Networking** | **Here (net-new)**: CloudFront (two origins, `/api/*` no-cache per ER-03), API Gateway HTTP API (throttle 20 rps / burst 40, TSD-10), WAFv2 deny-by-default (**Q5**), OAC (**Q2**), CSP/headers (**Q7**). Same-origin `/api/*`, no CORS (settled). |
| **Monitoring** | **Settled**: CloudWatch alarms (R-3..R-6, `TreatMissingData: breaching`), log groups (30 d), EMF metrics (NFR §5). **Here**: alarm destination wiring (**Q4**). |
| **Shared** | **Settled**: shared `notify-topic` (referenced, **Q4**), shared ECR repo `${Application}-${Environment}`, shared `ArmContainerBuildProject`, shared deploy role. U-02 creates none of these. |

---

## Part B — Execution checklist (after answers)

- [x] Run Step 5 analysis on the answers (vagueness / contradiction / option-merging / blocking follow-ups) → recorded as Part A2 (5 findings)
- [x] Write `infrastructure-design/infrastructure-design.md` — resource-by-resource mapping of L-1..L-12 across `dashboard.yml` + `dashboard-storage.yml`, four `cornell:*` tags, `HasImage`/naming/least-privilege, Q1–Q7 resolutions
- [x] Write `infrastructure-design/deployment-architecture.md` — Build (two images), the CFN actions (storage `RunOrder 1`, app + site-sync `RunOrder 2` — the corrected ordering), the net-new site-sync action, `stacks.yml` entries, the `dashboard-marker` `manual`→`pipeline` flip (DR-02), partial-state/hand-deploy story
- [x] Noted **shared-infrastructure.md NOT warranted** — U-02 consumes shared infra, creates none; reasoning in `deployment-architecture.md` §7
- [x] No earlier artifact rewritten; the one refinement (Q2 ordering) is a same-stage correction recorded in Part A2, not a change to an approved doc
- [x] Update `aidlc-state.md` (outputs section) and append `audit.md`
- [x] Present `# 🏢 Infrastructure Design Complete - U-02 Dashboard Platform` and wait for explicit approval

---

## Part A2 — Answer analysis

**User input**: "choose defaults and proceed" — an explicit acceptance of every recommendation (Q1–Q7 all **A**),
not an absence of a decision. Seven clean single selections; no vagueness, contradiction, or option-merging; no
blocking follow-up. Five findings surfaced while generating the artifacts — one corrects a loose phrasing in a
question, the rest are consequences worth recording:

1. **Q2/Q3 deploy ordering — corrected, answer unchanged.** Q2-A's text said both stacks "deploy in parallel at
   `RunOrder: 1`." That is wrong in one respect: the site `BucketPolicy` (placed in the app stack) calls
   `PutBucketPolicy` against the named bucket, so the bucket **must already exist**. The correct ordering is
   **`dashboard-storage` at `RunOrder: 1`, then `dashboard` + the site-sync at `RunOrder: 2`** (both of those depend
   only on the bucket existing + the image digests, and run in parallel with each other). The *decision* stands —
   policy in the app stack, no export, only stateful data in storage — only the ordering is serialized by one step.
2. **Two image parameters, two Build actions.** The collector/api split (separate Dockerfile targets) means two
   `ArmContainerBuildProject` Build actions and two `ContainerImageUri`-style params (`CollectorImageUri`,
   `ApiImageUri`), each `Condition`-gated independently.
3. **One `BucketPolicy` per bucket.** The site bucket's OAC grant and its `aws:SecureTransport` deny must live in a
   *single* policy (app stack). The snapshot bucket's TLS-deny policy is separate and stays in the storage stack
   (it references nothing external, so no cycle).
4. **CloudFront `/api/*` forwarding.** The API owns the `/api` prefix in its five-route table, so `/api/*` forwards
   verbatim with no path-rewrite CloudFront Function — routed to Code Generation as a route-table note.
5. **Viewer certificate.** No custom domain is in scope, so the distribution uses the default CloudFront certificate
   (`*.cloudfront.net`); HSTS/CSP still apply. A Cornell custom domain would be a future amendment, not this stage.
