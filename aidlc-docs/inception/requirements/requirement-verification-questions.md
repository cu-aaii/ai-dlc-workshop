# Requirements Clarification Questions — `dashboard` blueprint (Cost & Usage Dashboard)

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the
options match, choose the last option (Other) and describe your preference. Let me know when you're done.

## Question 1 — Data scope
What should the dashboard surface?

A) Cost only — dollar spend, broken out by the `cornell:*` tags (owner, blueprint, deployment-id)

B) Inventory only — which resources exist and how they're tagged, no dollar figures

C) Both cost and inventory, cross-referenced by `cornell:deployment-id`

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question 2 — Cost data source
Two AWS mechanisms can supply cost data, with very different setup cost and latency:

- **Cost Explorer API**: usable immediately, no export pipeline, but its tag-based cost breakdowns only
  work if `cornell:owner`, `cornell:blueprint`, etc. are first activated as **user-defined cost
  allocation tags** in the Billing console (a manual, one-time, per-account step — similar to the
  CodeConnections handshake — and newly activated tags take up to 24h to start appearing in cost data).
- **Cost and Usage Report (CUR)**: richer data, but requires a CUR export to S3 (usually configured at
  the payer/organization level, which this workshop account may not have access to) and has its own
  multi-hour-to-24h delay before the first report lands.

Given the workshop runs Aug 3–4, 2026, which should this blueprint use?

A) Cost Explorer API only — accept that tag-based breakdowns may not have real numbers yet if
   cost allocation tags aren't activated in time; fall back to account-level totals for the demo

B) Cost and Usage Report (CUR) pipeline — richer/more accurate, accepted even if it can't fully
   populate before the workshop ends

C) Don't decide yet — build the inventory side first (Resource Groups Tagging API, which has no
   activation delay) and treat cost data as a stretch goal

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question 3 — Presentation
How should the dashboard be consumed?

A) A small web UI (static site, e.g. S3 + CloudFront, calling an API) — visual, but more to build
   and more resources to tag/register

B) An API only (API Gateway + Lambda) returning JSON — builders/tools consume it, no UI

C) No live service — a scheduled job (EventBridge + Lambda) that snapshots cost/inventory data to
   S3 or an SSM parameter, read on demand via CLI (matches how `hello-world` proves itself today)

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question 4 — Update cadence
If a compute/data component is involved, how fresh does the data need to be?

A) Real-time — query Cost Explorer / Tagging API live on every request

B) Periodic snapshot — a scheduled job (e.g. every few hours via EventBridge) refreshes stored data,
   requests read the snapshot

C) Not applicable to my Question 3 answer

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question 5 — Access / audience
Who should be able to view this dashboard, and how should that be controlled?

A) Anyone with network access to the URL — no auth (acceptable only because this is a workshop demo,
   not production)

B) Authenticated Cornell users (e.g. Cognito, SSO) — real access control

C) Not public at all — internal only, e.g. workshop organizers query it directly (CLI/API with IAM auth)

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question 6 — Relationship to the existing `blueprints/dashboard/infra/hello-world.yml`
That file is a leftover copy-paste of the `hello-world` blueprint (same bucket/SSM-parameter shape,
still tagged `cornell:blueprint: hello-world`), not yet registered anywhere. What should happen to it?

A) Delete it and start the `dashboard` blueprint's infra from scratch

B) Keep it as the seed for one of the new stack's resources (e.g. rename it into the deployment-marker
   pattern) and build the real resources alongside it

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic,
   data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for
   projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin
   integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]: 

## Question: Resiliency Extensions
Should the resiliency baseline be applied to this project?

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance
   (recommended for business-critical workloads, as an informed starting point that you can validate
   and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental projects where
   rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]: 
