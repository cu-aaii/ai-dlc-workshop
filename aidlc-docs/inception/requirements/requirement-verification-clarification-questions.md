# Requirements Clarification Questions — Round 2

I detected two contradictions/ambiguities in your answers that need resolving before I generate
`requirements.md`.

## Contradiction 1: "real-time" cadence vs. cost data being a stretch goal
You indicated cost data source is **not decided yet / a stretch goal** (Q2: C — build inventory
first via the Resource Groups Tagging API, decide the cost API later) but also that data freshness
should be **real-time, querying live on every request** (Q4: A). Q4's option A specifically named
"Cost Explorer / Tagging API" together, which conflicts with deferring the cost side.

### Clarification Question 1
For the first version of this blueprint (inventory only, per Q2), should live/real-time querying
apply to inventory now, with cost added the same way (live query) once its data source is decided —
or does "real-time" only make sense once cost data exists, so v1 should just snapshot/refresh
periodically instead?

A) Real-time now for inventory (Resource Groups Tagging API on every request); cost gets the same
   real-time treatment whenever it's added later — no snapshot/cache layer at all

B) Real-time for inventory now, but plan for cost to use a periodic snapshot later instead
   (Cost Explorer has rate limits and per-call cost that make live-on-every-request less practical
   than it is for the Tagging API)

C) Switch v1 to a periodic snapshot for inventory too (matches how cost will likely need to work,
   keeps the two consistent from the start)

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Contradiction 2: Cognito/SSO "real access control" vs. the Azure/Entra Terraform stage not existing yet
You asked for authenticated Cornell users via Cognito/SSO (Q5: B — "real access control"). But
`CLAUDE.md` lists **"the Terraform stage for Azure/Entra resources"** under "Deliberately not
built... don't pre-build without being asked" — and true SSO for Cornell users means federating
Cognito to Cornell's IdP (Entra ID / Microsoft 365), which needs an app registration in Entra plus
a Terraform stage this pipeline doesn't have yet. Building that stage now is a much larger, separate
piece of work than the dashboard blueprint itself.

### Clarification Question 2
How should auth work for v1 of this blueprint, given the Entra federation piece doesn't exist yet?

A) Build the Azure/Entra Terraform stage now as part of this work, so Cognito can federate to
   Cornell's real IdP — explicitly opting in to pre-building that deliberately-deferred piece

B) Cognito user pool only for v1 (no Entra federation) — e.g. self-signup restricted to
   @cornell.edu email addresses, or organizer-provisioned accounts. Real login/session control,
   just not federated SSO. Swap in Entra federation later once that Terraform stage exists

C) Skip Cognito entirely for v1 — IAM-authenticated API calls only (matches Q5's "internal only"
   option C, which you didn't choose, but may be more realistic for the workshop window)

X) Other (please describe after [Answer]: tag below)

[Answer]:C
