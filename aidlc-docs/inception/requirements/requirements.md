# Requirements — `dashboard` Blueprint (Cost & Usage Dashboard)

**Stage**: INCEPTION → Requirements Analysis
**Date**: 2026-08-03
**Depth**: Standard (see rationale in Intent Analysis)

---

## 1. Intent Analysis

| Aspect | Assessment |
|---|---|
| **User request** | "continue building out the dashboard blueprint" — resolved through clarification to: build the `dashboard` blueprint as a **Cost & Usage Dashboard** that surfaces `cornell:*` tag inventory (and, later, cost data) for resources deployed by this platform. |
| **Request clarity** | Initially **Vague** (the branch contained only an unregistered copy-paste of `hello-world.yml`, and no spec existed). Now **Clear** after five rounds of clarifying questions. |
| **Request type** | **New Feature** — a new blueprint added to an existing, working deploy path. |
| **Scope estimate** | **Multiple Components** — a new `blueprints/dashboard/` directory (infra + application code + README) *plus* edits to two existing shared files: `pipeline/stacks.yml` (registry) and `pipeline/pipeline.yml` (deploy action). |
| **Complexity estimate** | **Moderate** — individually simple AWS primitives, but with several interacting constraints: `cornell:*` tagging, stack-naming rules that gate IAM permissions, the three-step registry/pipeline wiring, and three opted-in blocking rule extensions (security, PBT, resiliency). |
| **Depth rationale** | Standard rather than Comprehensive: single team, single account, non-production workshop workload with no irreplaceable data. Standard rather than Minimal: the request needed five clarification rounds, and it is user-facing with real functional and non-functional requirements. |

### Project context (binding, from `CLAUDE.md` / `README.md`)
This repo is the deploy path for Cornell's AI-DLC workshop (Aug 3–4, 2026). **Every merge to
`main` deploys to a shared AWS account.** The repo's hard constraints bind this blueprint
regardless of what the vendored AI-DLC rules say (see §5).

---

## 2. Source of Requirements — Clarification Answers

All requirements below trace to answers the user gave in five question rounds.

| # | Question | Answer | Effect |
|---|---|---|---|
| R1-Q1 | Data scope | **C**, plus other metrics later | Both cost **and** inventory, cross-referenced by `cornell:deployment-id`; the data model must be extensible to further metrics. |
| R1-Q2 | Cost data source | **C** | Don't decide the cost API yet. Build inventory first (Resource Groups Tagging API — no activation delay). Cost is a **stretch goal**. |
| R1-Q3 | Presentation | **A** | A small web UI — static site (S3 + CloudFront) calling an API. |
| R1-Q4 | Update cadence | **A**, superseded by **R2-Q1 = C** | Periodic snapshot, not live-per-request. |
| R1-Q5 | Access / audience | **B**, superseded by **R2-Q2 = C** → **R3-Q3** → **R4-Q4 = A** | No Cognito, no IAM-SigV4-in-browser. Access is restricted at the **network layer**: CloudFront + AWS WAF IP-allowlist for Cornell's known ranges. |
| R1-Q6 | Existing stray `hello-world.yml` | **B** | Keep it as the seed for one of the new stack's resources (rename into the deployment-marker pattern); build real resources alongside it. Do **not** delete. |
| R1-ext | security-baseline | **A** | SECURITY-01..15 enforced as blocking constraints. |
| R1-ext | property-based-testing | **A** | PBT-01..10 enforced as blocking constraints (full, not partial). |
| R1-ext | resiliency-baseline | **A** | RESILIENCY-01..15 applied as design-time guidance/blocking findings. |
| R2-Q1 | Cadence vs. deferred cost source | **C** | v1 uses a periodic snapshot for inventory too, so cost can be added the same way later. |
| R2-Q2 | Cognito/SSO vs. missing Entra stage | **C** | Skip Cognito entirely for v1; do **not** pre-build the deliberately-deferred Azure/Entra Terraform stage. |
| R3-Q3 | IAM-auth vs. browser UI | **Other**: "Deploy to an internal subnet that has no public access" | Move the security boundary to the network layer instead of forcing credentials into a browser. |
| R4-Q4 | Literal VPC subnet vs. effective network restriction | **A** | CloudFront + WAF IP-allowlist (Cornell's known ranges). **No VPC, no subnets, no VPN/Direct Connect/Transit Gateway** — none exist in this repo today and standing them up is out of scope. |
| R5-Q1 | RTO/RPO & DR strategy (RESILIENCY-02) | **E** | N/A — single-region is acceptable, no cross-region DR. Rely on in-region multi-AZ. |
| R5-Q2 | Change management (RESILIENCY-03) | **C** | Exempt from formal change management; rationale documented (§4.6). |
| R5-Q3 | Regional topology (RESILIENCY-08) | **A** | Single-region (`us-east-1`), multi-AZ via inherently multi-AZ managed services. |

**Contradiction status**: none outstanding. Superseded answers are recorded above rather than
silently dropped, and the supersession chain is logged in `aidlc-docs/audit.md`.

---

## 3. Functional Requirements

### FR-1 — Resource inventory from `cornell:*` tags
1. The system MUST collect an inventory of AWS resources in the deployment account that carry
   `cornell:*` tags, using the **Resource Groups Tagging API** (chosen because it has no cost
   allocation tag activation delay).
2. For each resource the inventory MUST capture, at minimum: resource ARN, resource type,
   region, and the values of all four required tags — `cornell:owner`, `cornell:blueprint`,
   `cornell:blueprint-version`, `cornell:deployment-id`.
3. The inventory MUST be groupable/aggregatable by **`cornell:deployment-id`** (the designated
   cross-reference key per R1-Q1), and also by `cornell:owner` and `cornell:blueprint`.
4. The system MUST be able to identify resources that are **missing one or more** of the four
   required tags, since an untagged resource is invisible to inventory and cost attribution —
   surfacing that gap is a primary purpose of this dashboard.

### FR-2 — Periodic snapshot (not live query)
1. Inventory collection MUST run on a **schedule** (EventBridge-driven), writing a snapshot to
   durable storage. Read requests MUST serve the stored snapshot, not trigger a live
   collection.
2. The snapshot MUST record its own collection timestamp, and every response served to a user
   MUST expose that timestamp so data age is never ambiguous.
3. The refresh interval MUST be a stack parameter, not hardcoded, so it can be tuned without a
   template change.
4. Snapshot storage MUST be structured so that a **later** cost dataset can be added alongside
   inventory and joined on `cornell:deployment-id`, without redesigning the store (R1-Q1's
   "other metrics to be defined later", R1-Q2's stretch goal).

### FR-3 — Read API
1. An HTTP API MUST expose the current snapshot as JSON to the web UI.
2. The API MUST support at least: the full inventory, and aggregation grouped by
   `cornell:deployment-id` / `cornell:owner` / `cornell:blueprint`.
3. All API request parameters MUST be validated against an allowlist of expected
   names/types/ranges, rejecting anything else (SECURITY-05).
4. Error responses MUST be generic and MUST NOT leak stack traces, ARNs of unrelated
   resources, internal paths, or account details (SECURITY-09, SECURITY-15).
5. The API MUST be rate-limited (SECURITY-12).

### FR-4 — Web UI
1. A **static** web UI MUST be served from S3 via CloudFront, calling the API from the browser
   (R1-Q3 = A).
2. The S3 origin MUST NOT be publicly readable; CloudFront MUST reach it via origin access
   control, and S3 Block Public Access MUST be on (SECURITY-09).
3. The UI MUST display: the inventory, the aggregation by `cornell:deployment-id`, the
   snapshot's collection timestamp, and a clear indication of untagged/mis-tagged resources.
4. The UI MUST show an explicit, non-alarming state when the snapshot is absent or stale rather
   than failing blank (graceful degradation, RESILIENCY-10).
5. There is **no login UI** in v1 — no Cognito user pool, no identity pool, no SigV4 signing in
   the browser (R2-Q2 = C).

### FR-5 — Network-layer access control
1. Access MUST be restricted by an **AWS WAF web ACL with an IP-set allowlist** of Cornell's
   known network ranges (campus + VPN egress), applied to CloudFront, with a **default action of
   block** (R4-Q4 = A; SECURITY-07 deny-by-default).
2. The same restriction MUST cover the API path, not just the static site — the API must not be
   reachable from outside the allowlist.
3. The allowlist ranges MUST be supplied as a stack parameter, not hardcoded in the template, so
   they can be corrected without editing the blueprint.
4. **No VPC, subnet, VPN, Direct Connect, or Transit Gateway resources** may be created. None
   exist in this repo, and creating them is explicitly out of scope (R4-Q4 = A).
5. This is a **network** control, not user authentication. It MUST be documented as such in the
   blueprint README, including the fact that it does not identify individual users and does not
   satisfy a future requirement for per-user access control.

### FR-6 — Repurpose the existing stray template
1. `blueprints/dashboard/infra/hello-world.yml` MUST be **repurposed, not deleted** (R1-Q6 = B):
   renamed into the dashboard's own deployment-marker pattern, with its `cornell:blueprint` tag
   corrected from `hello-world` to `dashboard`, its description rewritten, and its
   `cornell:blueprint-version` reset for this blueprint.
2. Real dashboard resources MUST be built alongside it.

### FR-7 — Platform wiring (all three steps)
1. Every CloudFormation template added MUST be registered in `pipeline/stacks.yml`, in the same
   PR as the template.
2. Every `deployed_by: pipeline` entry MUST have a matching action in `pipeline/pipeline.yml` —
   omitting it deploys nothing while reporting success.
3. Every parameter MUST be passed explicitly from the pipeline; template defaults exist only for
   manual debug deploys.
4. Stack names MUST follow `<application>-<environment>-<name>` (e.g. `aidlc-main-dashboard`),
   because `BuildPipelineRole` scopes CloudFormation permissions to
   `stack/${Application}-${Environment}*` and a non-conforming name fails with an opaque
   authorization error.
5. `tools/check` MUST pass before push.

### FR-8 — Cost data (stretch goal, explicitly out of v1 scope)
1. Cost figures are a **stretch goal**. The cost data source (Cost Explorer API vs. Cost and
   Usage Report) is deliberately **not decided** in this stage (R1-Q2 = C).
2. v1 MUST NOT block on cost data, but MUST leave the snapshot schema and API shape extensible
   for it (see FR-2.4).
3. When cost is taken up, the decision MUST be revisited as its own clarification, capturing the
   known tradeoff: Cost Explorer needs `cornell:*` activated as user-defined cost allocation
   tags in the Billing console (manual, one-time, per-account, ~24h before data appears), while
   CUR needs a payer/organization-level export this workshop account may not control.

---

## 4. Non-Functional Requirements

### 4.1 Security (SECURITY-01..15 — all blocking)

| Rule | Requirement for this blueprint |
|---|---|
| SECURITY-01 Encryption at rest | S3 buckets encrypted; snapshot store encrypted; CloudWatch Logs encryption considered. |
| SECURITY-02 Encryption in transit | HTTPS only — CloudFront viewer protocol policy redirects/requires HTTPS; TLS 1.2+ minimum; no plaintext endpoint. |
| SECURITY-03 Access logging | CloudFront access logging enabled; S3 server access logging or equivalent; WAF logging enabled so blocked requests are visible. |
| SECURITY-04 Application logging | Structured (JSON) logging from the collector and API Lambdas, to CloudWatch Logs, with no secrets or PII in log output. |
| SECURITY-05 Input validation | All API parameters allowlist-validated (FR-3.3). |
| SECURITY-06 Least-privilege IAM | Collector role limited to the read-only Tagging API actions it needs; API role limited to reading the snapshot store. **No wildcard actions or resources without a documented exception.** Note: `tag:GetResources` is inherently account-wide (it has no per-resource ARN scoping) — this is a documented, justified exception, not an oversight. |
| SECURITY-07 Restrictive network config | Deny-by-default WAF (FR-5.1); no `0.0.0.0/0` ingress; S3 not public. |
| SECURITY-08 Application access control | No CORS wildcard on the API — CORS restricted to the CloudFront distribution origin. |
| SECURITY-09 Hardening | S3 Block Public Access on; no default credentials anywhere; generic error responses. |
| SECURITY-10 Supply chain | Python dependencies pinned (hashes/versions); Lambda uses **container images** (repo constraint), base image pinned by digest; vulnerability scanning and SBOM addressed at Construction. |
| SECURITY-11 Security headers | CloudFront response headers policy setting CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy. |
| SECURITY-12 Secure design | Separation of collector (write) from API (read); defense in depth (WAF **and** private S3 origin **and** least-privilege IAM); API rate limiting. |
| SECURITY-13 Authentication / credentials | **No application authentication in v1** — access control is the network allowlist (FR-5.5). This is a deliberate, documented deviation from SECURITY-13's password/MFA/session provisions, justified by R2-Q2/R3/R4 and by the absence of the Entra federation stage. It MUST be recorded as an accepted exception with the compensating control (WAF allowlist), and revisited if the dashboard ever needs per-user identity. **No secret may ever be committed — this repo is public with secret scanning disabled.** |
| SECURITY-14 Integrity | No unsafe deserialization (JSON only, no `pickle`/`yaml.load`); Subresource Integrity on any third-party script the UI loads (preferably: load none); snapshot writes attributable via logs. |
| SECURITY-15 Fail-safe defaults | Fail **closed** — if the snapshot can't be read or the collector fails, serve an explicit error/stale-data state, never fabricated or partial-looking-complete data. Global error handler; no information leakage. |

### 4.2 Property-Based Testing (PBT-01..10 — all blocking, full enforcement)

1. **PBT-01** — Properties MUST be identified during Functional Design, categorized
   (round-trip, invariant, idempotence, commutativity, oracle, induction,
   easy-verification). Candidate properties for this blueprint:
   - **Round-trip**: snapshot serialize → store → deserialize returns an equal inventory.
   - **Invariant**: aggregation by `cornell:deployment-id` preserves total resource count; every
     resource appears in exactly one group; no group is empty.
   - **Idempotence**: collecting the same tag data twice produces the same snapshot; re-writing
     an identical snapshot changes nothing observable.
   - **Oracle/model**: aggregation output matches a naive reference implementation over the same
     input.
   - **Easy-verification**: the "missing required tags" classifier flags exactly those resources
     lacking at least one of the four `cornell:*` keys.
2. **PBT-02..06** — Round-trip, invariant, idempotency, and oracle/model tests MUST exist for
   the above; stateful property testing MUST be applied to the snapshot store's
   write-then-read behaviour.
3. **PBT-07** — Generators MUST be domain-specific (realistic ARNs, valid/invalid
   `cornell:*` tag sets, mixed-completeness tag maps), not raw primitives.
4. **PBT-08** — Shrinking and seed-based reproducibility MUST be enabled so failures are
   minimal and replayable.
5. **PBT-09** — The framework MUST be chosen and documented in the tech stack. **Hypothesis**
   (Python) is the expected choice, consistent with the repo's existing Python usage.
6. **PBT-10** — PBT MUST **complement**, not replace, example-based tests.

### 4.3 Resiliency (RESILIENCY-01..15)

| Rule | Status for this blueprint |
|---|---|
| RESILIENCY-01 Criticality | **Medium/Low**. This is an observability aid for a two-day workshop, not a revenue or safety path. Unavailability means organizers temporarily can't see tag/cost inventory; there is no data loss of record, because every input is re-derivable from the live AWS account. Dependencies: Resource Groups Tagging API (upstream), snapshot store, CloudFront/WAF (downstream of the UI). Nothing depends on this blueprint. |
| RESILIENCY-02 Availability & recovery targets | **RTO/RPO: N/A per user answer (R5-Q1 = E)** — no cross-region DR. Justification: the snapshot is fully rebuildable by re-running the collector against the live account, so RPO is effectively bounded by the refresh interval and no data is irreplaceable. Availability target: best-effort in-region; not SLA-bound. Explicitly **not** over-engineered — matching the rule's requirement that over-engineering is itself a finding. |
| RESILIENCY-03 Change management | **Exempt per user answer (R5-Q2 = C).** Rationale: this is workshop teaching infrastructure with no external customers. In practice changes are still gated — `main` is PR-only with one mandatory human approval and no self-approval (branch protection) — but no formal change-record process (CAB/ServiceNow) applies. This exemption is recorded here as the rule requires. **⚠️ SUPERSEDED IN PART — see `inception/amendments/repo-baseline-2026-08-03.md` §A1.1.** `CLAUDE.md` now requires **zero approving reviews**; a team member merges their own PR. The exemption (a recorded user decision) stands, but the compensating control cited in this rationale no longer exists. |
| RESILIENCY-04 Automated deploy & rollback | Deployment is already automated (CodePipeline → CodeBuild → CloudFormation). Rollback mechanism and deployment style are **user decisions deferred to NFR/Application Design** per the extension's own scoping. |
| RESILIENCY-05 Monitoring & alerting | Metrics, structured logs, and a health dashboard required. Distributed tracing: **N/A** (not a multi-service distributed system). |
| RESILIENCY-06 Health checks | The API MUST expose a health endpoint. A deep check verifying the snapshot store is readable is required for the API. Synthetic canary monitoring: documented as not applicable (the endpoint is not publicly reachable — WAF-allowlisted only). |
| RESILIENCY-07 Resiliency monitoring | Alarms required for **collector failure** and **snapshot staleness** (the two conditions that silently degrade this dashboard), plus Lambda error/throttle alarms. |
| RESILIENCY-08 Multi-zone / multi-region | **Single-region `us-east-1`, multi-AZ (R5-Q3 = A)** — satisfied inherently: Lambda, S3, CloudFront, and DynamoDB/SSM are all multi-AZ managed services. No multi-region. Statically stable: no control-plane action is needed to survive an AZ event. |
| RESILIENCY-09 Auto-scaling & quotas | Serverless throughout, so scaling is inherent; Lambda **reserved/maximum concurrency MUST be set** to bound blast radius and cost. Relevant quotas to identify and document: Resource Groups Tagging API request rate, Lambda concurrency, WAF IP-set size limits. |
| RESILIENCY-10 Dependency isolation | Explicit timeouts on **every** AWS SDK call (no unbounded waits); bounded retries with backoff on Tagging API throttling; graceful degradation — stale snapshot served with its timestamp rather than an outage (FR-4.4). |
| RESILIENCY-11 DR strategy | **Backup & Restore by construction**: the entire stack is redeployable from IaC and the snapshot is regenerable from the live account. No separate DR tier needed, consistent with R5-Q1 = E. |
| RESILIENCY-12 Backup & replication | Snapshot store encrypted at rest; S3 versioning where a bucket holds the snapshot. Cross-region replication **not required** — justified: the data is derived, not authoritative, and is regenerable in one collector run. |
| RESILIENCY-13 Failover & recovery procedures | Recovery procedure documented in the blueprint README: redeploy the stack, then invoke the collector to repopulate. No cross-region failover exists to run. |
| RESILIENCY-14 Chaos / DR testing | **Deferred to NFR Design** per the extension's scoping (user decision). |
| RESILIENCY-15 Incident response | **Deferred to NFR Design** per the extension's scoping (user decision). |

### 4.4 Performance & scale
- Read requests serve a precomputed snapshot, so response time is dominated by snapshot retrieval,
  not by AWS API latency.
- Expected data volume is small (tens to low hundreds of tagged resources in one workshop account);
  the design MUST NOT assume this but also MUST NOT be built for scale that isn't there.
- The collector MUST paginate the Tagging API correctly — silently truncating at the first page
  would under-report inventory, which is worse than failing.

### 4.5 Maintainability & testability
- Tagging/aggregation logic MUST be pure and unit-testable independently of AWS calls, so PBT
  can exercise it without network access.
- The blueprint MUST be self-contained under `blueprints/dashboard/` (per `blueprints/README.md`),
  apart from its two required registry/pipeline entries.
- `blueprints/dashboard/README.md` MUST document: what the blueprint deploys, its parameters,
  the WAF-allowlist access model and its limits, the recovery procedure, and the accepted
  SECURITY-13 exception.

### 4.6 Documented exceptions (accepted, with rationale)
1. **No application-level authentication (SECURITY-13)** — compensating control: WAF IP
   allowlist. Driven by R2-Q2/R3-Q3/R4-Q4 and by `CLAUDE.md` listing the Azure/Entra Terraform
   stage as deliberately not built.
2. **Account-wide read scope for `tag:GetResources` (SECURITY-06)** — the action does not
   support per-resource ARN scoping; it is read-only and inventory-only.
3. **Formal change management exempt (RESILIENCY-03)** — R5-Q2 = C; PR approval gate remains.
4. **No cross-region DR (RESILIENCY-02, -08, -12)** — R5-Q1 = E / R5-Q3 = A; data is derived
   and regenerable.

---

## 5. Constraints Inherited from the Repository

These bind regardless of the vendored AI-DLC rules, per `CLAUDE.md`:

1. Everything is IaC — CloudFormation via CodePipeline → CodeBuild. No click-ops.
2. Serverless-first, `us-east-1`. **Lambda means container images**, not zip.
3. Secrets live only in AWS Secrets Manager. **The repo is public with secret scanning disabled
   — never commit a credential.**
4. `main` is PR-only, one human approval, no self-approval. **⚠️ SUPERSEDED — see
   `inception/amendments/repo-baseline-2026-08-03.md` §A1.1.** Now: PR required and direct pushes
   rejected, the `validate` check must pass, `ai-dlc-workshop` team members only — but **zero
   approving reviews**, so a team member merges their own PR and `validate` is the only automated
   gate between a branch and a shared-account deploy.
5. All four `cornell:*` tags on every resource. `cornell:owner` and `cornell:deployment-id`
   arrive as stack parameters; `cornell:blueprint` is hardcoded to `dashboard` and
   `cornell:blueprint-version` is a template default bumped in the PR that changes the blueprint.
6. Stack naming `<application>-<environment>-<name>`; `Environment` matches `[a-z0-9]{1,4}`;
   `Application` is `aidlc` (≤10 chars).
7. Register in `pipeline/stacks.yml` **and** add the matching `pipeline/pipeline.yml` action.
8. Pass every parameter explicitly from the pipeline.
9. Don't reshape the pipeline's known-good mechanics (source stage, artifact handling, role
   assumptions, digest export).
10. `tools/check` is the sanctioned pre-push check; never the bare `cfn-lint` /
    `validate_stacks.py` forms.
11. Known gotchas that apply here: `AWS::SSM::Parameter` takes `Tags` as a **map**, not a list;
    `cfn-lint --region` needs a literal `--` before paths (handled by `tools/check`); the org
    allowed-actions policy permits only github-owned actions plus `hashicorp/setup-terraform@*`.
12. Do **not** pre-build the deliberately-deferred pieces: `builder-mcp/`,
    `blueprints/course-chatbot/`, the Azure/Entra Terraform stage, `observability/`.

---

## 6. Out of Scope for v1

- Cost dollar figures and the choice of cost data source (stretch goal — FR-8).
- Cognito, any login flow, per-user identity, and Entra/SSO federation.
- Any VPC, subnet, VPN, Direct Connect, or Transit Gateway networking.
- Multi-region deployment and cross-region DR.
- The `observability/` directory and `builder-mcp/`.

---

## 7. Summary of Key Requirements

A scheduled collector snapshots `cornell:*`-tagged resource inventory from the Resource Groups
Tagging API into an encrypted store; a read API serves that snapshot as JSON; a static S3 +
CloudFront UI renders it, grouped by `cornell:deployment-id`, with the snapshot age always
visible and untagged resources called out. Access is controlled at the network layer by a
deny-by-default WAF IP allowlist of Cornell ranges — there is no login and no VPC. The existing
stray `hello-world.yml` copy is repurposed as the dashboard's deployment marker rather than
deleted. All three opted-in extensions apply as blocking constraints, with four explicitly
documented and justified exceptions. The blueprint is wired through all three required platform
steps (template + `stacks.yml` registration + `pipeline.yml` action) and must pass `tools/check`.
