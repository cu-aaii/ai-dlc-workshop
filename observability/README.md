# observability/

Track E: seeing what's running. Centrally, every deployment across the university with its owner
and health; for a unit, only their own — metrics, logs, failures, cost — **without giving them
access to the AWS account.** That last clause is the whole difficulty. The rest is dashboards.

**Nothing here yet.**

## Why the tagging convention is not bureaucracy

Every resource in this repo carries four tags: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. They exist for this track and nothing else.

- `cornell:deployment-id` is the join key — it turns a pile of account resources into
  deployments.
- `cornell:owner` is what scopes a unit's view to its own.
- `cornell:blueprint` + `cornell:blueprint-version` are what let you answer "how many units are
  on the old chatbot" without reading templates.

An untagged resource is not merely undocumented, it is **absent** from anything built here. If
this track finds a resource the dashboard can't see, that is a bug in the blueprint that owns it,
and worth fixing there rather than special-casing here.

Resource Groups Tagging `get-resources` is the cheapest way to enumerate by tag, and
`packages/builder-mcp/src/builder_mcp/aws_ops.py` already calls it for `deployment_health`'s tag
audit — that inventory-plus-audit logic is worth reading before writing a second version of it.

## The hard part, stated plainly

Builders have no AWS account and no console access. That is deliberate: the builder experience
being designed doesn't include one, so the workshop rehearses the real thing. So a unit's view of
its own deployment has to be **served**, not granted — something reads the account and hands back
only that owner's rows.

Two shapes, and the choice is worth writing down in [`docs/decisions/`](../docs/decisions/)
rather than being implied by whatever gets built first:

- **A dashboard that authenticates users** and filters by `cornell:owner`. Familiar; needs an
  auth story, a hosting story, and a place to run.
- **Tools on the Cornell Builder MCP**, so a builder asks "how's my deployment" in the same
  conversation they deployed from. `deployment_read` and `deployment_health` already do most of
  this for one deployment — the missing piece is the fleet view and cost, not the per-deployment
  read. No new front end, no new auth surface, and it matches how a builder already works.

They are not exclusive; the second is closer to shipping and the first is what a provost sees.

## Cost

The demo's seventh beat is "the dashboard shows the deployment that just appeared, with its owner
and estimated cost." Cost per deployment comes from Cost Explorer grouped by the
`cornell:deployment-id` tag — which requires that tag to be **activated as a cost allocation tag**
in Billing, by hand, once per account, and it only applies to usage recorded after activation.
Nobody discovers that in time on demo morning. Check it early.

## Anything deployed from here follows the same rules

If this track produces AWS resources, it is CloudFormation, registered in `pipeline/stacks.yml`,
wired to an action in `pipeline/pipeline.yml`, named `<application>-<environment>-<name>`, and
tagged with all four `cornell:*` tags like everything else. The observability stack being
observable is not a joke — it is the first thing anyone will ask about.
