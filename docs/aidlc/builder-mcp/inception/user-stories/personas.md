# Personas — builder-mcp (Gate 2, per Q-S2 = B: four personas)

Four personas cover the whole journey (Q-S1 = A). Stories in
[stories.md](stories.md) tag each with its persona(s); the story ↔ tool matrix is in
[story-tool-map.md](story-tool-map.md).

---

## P-BUILDER — the Builder

**Role.** Campus instructor or unit developer who wants working, governed AWS
infrastructure without touching AWS. Interacts only through a Claude client speaking to
builder-mcp; has PR-only write access, no console, no credentials (NFR3, D3).

**Motivation.** Ship a course tool or unit app this week by describing it in plain
language. Wants the platform to translate intent into a deployment, not to learn
CloudFormation.

**Fears.**
- Being blocked by AWS jargon or an opaque failure ("authorization error" instead of
  "your stack name broke the convention").
- Accidentally creating something expensive, untagged, or non-compliant.
- A green-looking process that silently deployed nothing (the `deployed_by: pipeline`
  trap).

**Definition of success.** From first utterance to a running, tagged stack with only
plain-language interaction and one human PR approval in between; can later see status,
health, and cost, change or restart the deployment, and hand it off — all without a
single AWS credential.

---

## P-REVIEWER — the Reviewer

**Role.** The human at the gate: approves the registration PR (and every change PR)
before merge. Per Q-S6 = C, this persona also owns acceptance sign-off for these
stories. May be a platform team member or any second person — nobody approves their own
PR.

**Motivation.** Keep `main` green and the shared AWS account safe while approving
quickly enough that builders are not queued behind the gate.

**Fears.**
- An unreviewable diff (a regenerated pipeline.yml instead of a one-action insertion).
- Approving something the tool could then escalate — a PR that hides a deploy, a merge,
  or a credential.
- Missing a policy violation (data classification, missing tags, off-convention stack
  name) that the pipeline will only reveal as an opaque mid-run failure.

**Definition of success.** Every PR arriving at the gate is small, convention-shaped
(SPEC C6), and reviewable in minutes; the tool surface provably cannot merge, push to
tracked branches, or call CloudFormation Create/Update/Delete (C3 invariants), so
approval is the *only* path to a deploy.

---

## P-OPERATOR — the Platform Operator (AI-SEI)

**Role.** Runs the shared account: inventory, cost dashboard, incident response.
Controls the pipeline, the roles, and Secrets Manager; builders never do.

**Motivation.** Know at all times what is deployed, who owns it, what it costs, and
what is unhealthy — across *all* deployments, not one at a time.

**Fears.**
- Untagged resources that are invisible to inventory and the cost dashboard (the four
  `cornell:*` tags are load-bearing).
- Unbounded retries masking real failures and burning pipeline runs.
- Orphaned deployments: repos and stacks whose owner has left or lost interest, with no
  deregistration path.

**Definition of success.** Every resource carries all four tags; every deployment is
attributable to an owner NetID; failures are diagnosable from the chain view (PR →
pipeline → stack) without console archaeology; teardown is as governed as creation.

---

## P-AUTHOR — the Blueprint Author

**Role.** Contributes blueprints to the catalog: a CloudFormation template plus a
`blueprint.yaml` manifest (SPEC C1, FROZEN). The product proposal ranks catalog
starvation a HIGH risk, which is why this persona is in scope (Q-S2 = B).

**Motivation.** Get a reusable building block in front of every campus builder without
having to run support for forty forks (D1: reference, never copy).

**Fears.**
- Writing a manifest that silently fails validation (the CFN format-marker text-scan
  trap, GOTCHA-MARKER).
- Builders never finding the blueprint because its `matches:` phrases don't cover how
  people actually ask.
- Breaking existing deployments with a new version — deployments must stay pinned until
  they opt in.

**Definition of success.** A contributed blueprint passes `tools/check`, appears ranked
in `blueprint_search` results, deploys identically by hand and by pipeline, and can
release new semver versions with release notes while existing deployments stay pinned.
