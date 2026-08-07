# Requirements Clarification Questions — Round 5 (Resiliency Baseline)

You opted into the resiliency baseline extension (answer A on the original question set). That
extension mandates a few decisions the model isn't allowed to make on your behalf — they're listed
below. This is the last set of Requirements-stage questions; two other resiliency questions
(CI/CD & rollback mechanism, incident response process) are deferred to the later NFR
Design/Application Design stage per the extension's own rules, so they won't block requirements.md.

## Question 1 — RTO/RPO Goals and Disaster Recovery Strategy (RESILIENCY-02)
What are your Recovery Time Objective (RTO) and Recovery Point Objective (RPO) goals for this
blueprint? Context: it's a workshop demo (Aug 3–4, 2026) that snapshots tag/inventory (and
eventually cost) data periodically into storage that's trivially rebuildable from IaC — there's no
irreplaceable user data.

A) RPO/RTO: Hours — Backup & Restore strategy. Lowest cost. Suitable for non-critical workloads.

B) RPO/RTO: 10s of minutes — Pilot Light strategy.

C) RPO/RTO: Minutes — Warm Standby strategy.

D) RPO/RTO: Near real-time — Multi-site Active/Active strategy.

E) N/A — Single-region deployment is acceptable, no cross-region DR needed. Rely on multi-zone
   availability within one region.

X) Other (please describe after [Answer]: tag below)

[Answer]:E

## Question 2 — Change Management Process (RESILIENCY-03)
How should production changes for this blueprint be governed?

A) Use our existing organizational change management process — name it (e.g., ServiceNow, Jira
   Change, internal CAB)

B) No formal process exists yet — propose a lightweight change management process (change record +
   approval + rollback note) for the team to adopt. Note: this repo's `main` branch is already
   PR-only with mandatory human approval (no self-approval) — a lightweight process could simply
   point to that existing PR-approval gate rather than inventing a new one

C) N/A — this workload is exempt from formal change management (e.g., it's a workshop demo).
   Document the exemption rationale

X) Other (describe after [Answer]: tag below)

[Answer]:C

## Question 3 — Regional Topology (RESILIENCY-08)
Does this workload require multi-region deployment, or is single-region with multi-zone redundancy
sufficient? (This follows from your Question 1 answer — options A/B/E there align with single-region
multi-zone; C/D imply multi-region.)

A) Single-region, multi-zone — tolerates zone failure, not full-region failure. Lower cost. All
   components here (Lambda, S3, CloudFront, DynamoDB/SSM if used) are inherently multi-AZ within a
   region by default

B) Multi-region active-passive — survives region failure with failover. Higher cost.

C) Multi-region active-active — survives region failure with no downtime. Highest cost.

X) Other (describe after [Answer]: tag below)

[Answer]:A
