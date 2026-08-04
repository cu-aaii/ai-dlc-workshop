# 0001 — Every blueprint UI conforms to one design language, with accessibility and Cornell logo rules non-waivable

**Status**: accepted
**Date**: 2026-08-04
**Deciders**: requested and directed by the repo owner; drafted with Claude Code

## Context

Blueprints are stamped into template repos that a **non-engineer** customizes. Anything left to the
builder's judgment gets lost — the same reasoning that puts the four `cornell:*` tags in the template
rather than in a builder's checklist.

Three things forced the choice now:

- **A real design language exists.** `blueprints/aisei-site/` shipped the WordPress-migration tokens,
  component library, and a `wp-style-guide` skill. Without a rule pointing at it, the next UI blueprint
  invents its own.
- **`tiny-chatbot` already demonstrates the failure mode.** It serves a self-contained page with inline
  `<style>` and `<script>`, no CSP, `system-ui` instead of the Cornell stack, and three non-brand grays
  (`#ccc`, `#eee`, `#d9e8ff`). Nobody decided that; it accreted.
- **Accessibility is a legal obligation, not a quality bar.** Cornell Policy 5.12, ADA Title II (DOJ's
  2024 rule names WCAG 2.1 AA), and Section 504/508 all apply. A design system that treats contrast as
  a preference is the wrong shape for a legal requirement.

## Decision

`contracts/ui-design-language.md` binds every blueprint that renders human-readable output.
`blueprints/aisei-site/` is its reference implementation.

Authority is **strictly ordered**, because all three sources genuinely conflict:

1. **Accessibility law and Cornell Policy 5.12** — enforce **WCAG 2.2 AA**, chosen because it is a
   superset of the 2.0 AA and 2.1 AA that the obligations above name. **Never waivable.**
2. **Cornell brand guidelines** (brand.cornell.edu) for logo and palette. **Never waivable.**
3. `aisei-site` tokens and patterns — binding except where 1 or 2 overrides, and **deviation is
   permitted when documented** in `blueprints/<name>/docs/`.

Enforcement is `.claude/skills/cornell-ui-compliance/`: it triggers on UI work, stops on a violation,
names the measured value and the threshold it misses, prompts for an adjustment, and **re-measures the
adjustment before accepting it.** No iteration cap, no ship-anyway path for (1) or (2).

## Alternatives

- **A style guide instead of a contract** — rejected. A style guide has no precedence rule, so when
  the reference implementation is itself inaccessible there is nothing to say which wins. That case is
  not hypothetical: `aisei-site`'s global focus ring measures **1.08:1 on carnelian**.
- **Adopt `aisei-site` as-is, verbatim** — rejected on measurement. Four of its tokens fail WCAG AA
  (focus ring on dark surfaces, `--color-border` at 1.32:1 as a boundary, `#F8981D` at 2.21:1 as a
  fill, white-on-orange at 2.21:1). Adopting it unqualified would have adopted the failures.
- **Trust Cornell's palette labels without measuring** — rejected. Cornell marks `#6EB43F` and
  `#F8981D` "graphics only", which means *don't set text in them* — it does **not** mean they are safe
  as graphics. Both fail 1.4.11 on white (2.54:1, 2.21:1). The label and the requirement are different
  questions.
- **A `ui:` key in `blueprint.yaml`** for machine-checkable conformance — deferred, not rejected. That
  manifest is **FROZEN** (`packages/builder-mcp/SPEC.md` §C1, no substantive change without mob
  agreement). Raised as a proposal instead.
- **A PR check in `tools/check`** — deferred. Contrast and logo geometry need a rendered page, not a
  text scan. The skill plus review is honest about being manual; a half-check that passed on greppable
  hexes would read as automated and miss the real cases.

## Consequences

**Easier**: a new UI blueprint starts from decided tokens and a checklist rather than taste. Brand and
accessibility questions have one place to look and one escalation path (`brand@cornell.edu`).

**Harder**: Cornell's approved palette turns out to support only **two identity-safe chart series**
(blue `#006699`, navy `#073949`) once green/orange/red are reserved for status. Contrast *between* those
marks is 1.99:1, under the 3:1 that 1.4.11 wants — so legend, direct labels, a table-view twin, and 2px
gaps become **mandatory** rather than nice-to-have, and multi-series categorical charts are effectively
capped. Emphasis becomes the default chart form.

**Commits us to**: measuring rather than asserting. Every ratio in the contract was computed and is
recorded so the next reader can re-derive it. Also commits us to a real enforcement loop — an agent
that finds a violation must stop and fix it, not annotate it.

**Known non-conformance on acceptance**: `tiny-chatbot` (§11 of the contract recommends a declared
exemption plus two cheap fixes — a speaker label, brand-palette bubbles — but filing it is its owner's
call). `blueprints/dashboard/` is unbuilt and intended as the first full conformer.

**Revisit when**: brand.cornell.edu changes its logo or color rules — that page wins and the contract is
the bug; the manifest freeze lifts, making a machine-readable `ui:` declaration possible; or Cornell
publishes an accent that adds a third identity-safe series color.
