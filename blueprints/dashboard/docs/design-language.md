# `dashboard` — UI design addendum

**The rules live in [`contracts/ui-design-language.md`](../../../contracts/ui-design-language.md),
and the design language is [`blueprints/aisei-site/`](../../aisei-site/).** This file holds only what
is specific to this blueprint. If anything here contradicts the contract, the contract wins and this
file is the bug.

Written ahead of the template; `blueprints/dashboard/` is otherwise unbuilt.

## Conformance

| Contract section | Position |
|---|---|
| §2 accessibility (WCAG 2.2 AA) | Conform. Non-waivable |
| §3 Cornell logo | Conform. Public-facing, so a mark is **required** — see below |
| §4–§7 palette, tokens, type, layout | Conform, from `aisei-site` tokens |
| §8 delivery | Bundled SPA behind CloudFront, CSP with no `unsafe-inline` |
| §9 charts | Conform — this blueprint is the reason §9 exists |

## Correction to earlier drafts of this file

An earlier version of this addendum specified a three-hue series palette of blue, **gold `#8f6b00`**,
and **purple `#7c32c4`**. Those came from the `cwd_framework` tutorial-callout colors, and **they are
not Cornell brand accents at all** — Cornell's accent palette is blue, green, orange, secondary red,
and navy. That palette has been replaced by §9's, and the gold/purple values must not be reintroduced.

## Dashboard-specific decisions

### The series ceiling is two, and it binds immediately

Per contract §9, once the green/orange/red families are reserved for status, Cornell's palette leaves
**two identity-safe accents**: blue `#006699` and navy `#073949`, plus dark gray `#222222` for
de-emphasis and "Other".

This dashboard groups by `cornell:blueprint` and `cornell:owner`, and `main` already carries
`hello-world`, `notify-topic`, `knowledgebase`, `entra-probe`, `tiny-chatbot`, `course-chatbot`, and
`aisei-site` — **seven blueprints against two slots.** So:

- The **"Other" fold is a launch requirement**, not a later refinement.
- The **table view is the only place the full breakdown appears**, which makes it load-bearing for
  1.4.11 rather than a convenience — contrast between blue, navy, and dark gray is 1.99, 2.55, and
  1.28, all under 3:1, so the legend, direct labels, table view, and 2px gaps are what make these
  charts conformant.
- **Emphasis is the default form**, not the exception: one blueprint in blue, the rest in `#222222`.

### Status is inventory health, not a category

Two conditions wear status tokens, because both mean *bad* when they trip:

- **Tag completeness** — a resource missing any of the four `cornell:*` tags
- **Snapshot staleness** — inventory older than its freshness threshold

Grouping by blueprint or owner is **identity** and wears the series palette. Getting this backwards
makes a busy blueprint look like an alarm.

### The Cornell mark

Public-facing, so §3.1 requires a mark. The plane is predominantly white and the only assets in
`aisei-site/app/client/assets/` are **white-fill** (1.00:1 on white — prohibited). Two compliant
routes; this blueprint takes the first:

1. **A carnelian or dark masthead band carrying the white-fill seal** — white on carnelian is 6.80:1,
   on `#1a1a1a` 17.40:1. Reuses the existing asset and the `aisei-site` masthead pattern.
2. Obtain the black or carnelian variant from brand.cornell.edu for direct placement on white.

Either way: **one mark only** (§3.6 — so a masthead seal *and* a footer wordmark is a violation), size
in band at **every breakpoint**, and clear space of 1/4 the seal's diameter.

### View composition

| Question | Form |
|---|---|
| How many resources are deployed right now? | Hero figure |
| Resource count, deployment count, tag-completeness %, cost | KPI row |
| Resources per blueprint / per owner | Horizontal bar, one series (blue) |
| One blueprint is the story | **Emphasis** — blue + `#222222` |
| Tagged vs. untagged share | Stacked bar, 2 segments, status colors |
| Snapshot freshness vs. threshold | Meter or stat tile with status |
| Change since previous snapshot | Diverging bar |
| More than 2 blueprints compared at once | Table, or table + emphasis chart |

**The dual-axis temptation is specific to this blueprint**: cost and resource-count on one plot is the
most natural chart to reach for on a cost-and-usage dashboard, and it is prohibited (§9
anti-pattern 1). Two charts, or index both to a common base on one axis.

## Open

- **Cost figures are deferred** with the data source undecided (Cost Explorer vs. CUR), so the cost KPI
  and cost-over-time chart are specified but not yet sourced.
- **No `blueprint.yaml` yet**, so this blueprint is invisible to the Builder — correct while it is a
  scaffold, and required before it is finished. The manifest schema is frozen
  (`packages/builder-mcp/SPEC.md` §C1).
