# contracts/

Standards that bind **more than one** blueprint.

A contract lives here when several blueprints must agree on something for the platform to treat them
uniformly — the way `pipeline/stacks.yml` is the one registry every template is checked against. A
rule that applies to a single blueprint belongs in that blueprint's own `docs/`, not here.

| Contract | Binds | Status |
|---|---|---|
| [`ui-design-language.md`](ui-design-language.md) | Every blueprint that renders something a human reads | Active. Accessibility (§2) and Cornell logo (§3) are **non-waivable**; §5 and below permit documented deviation |

The UI contract is enforced by
[`.claude/skills/cornell-ui-compliance/`](../.claude/skills/cornell-ui-compliance/SKILL.md), which
triggers on UI work, blocks a violation, prompts for an adjustment, and **re-measures the adjustment**
before accepting it. Its design language is [`blueprints/aisei-site/`](../blueprints/aisei-site/); its
external authorities are [brand.cornell.edu](https://brand.cornell.edu/logos) and Cornell Policy 5.12.

## What is not here, and why

**The blueprint manifest** (`blueprints/<name>/blueprint.yaml`) is also a cross-team contract, but it
is specified in [`packages/builder-mcp/SPEC.md`](../packages/builder-mcp/SPEC.md) §C1 and **frozen** as of 2026-08-03 —
no substantive changes without mob agreement. It is not duplicated here; a second copy of a frozen
schema is a second thing to drift.

**The `cornell:*` tagging convention** is stated in [`blueprints/README.md`](../blueprints/README.md)
under "Required of every blueprint" and in `CLAUDE.md`. It predates this directory and is already
linked from where blueprint authors look.

## Conventions for a contract in here

- **Say who it binds, and when it does not.** A contract that appears to apply to everything gets
  applied to nothing. Gate the sections.
- **Separate the waivable from the non-waivable, explicitly.** A contract that treats a legal
  obligation and a styling preference with the same weight teaches readers to ignore both.
- **Record measurements, not assertions.** If a rule rests on a number, the number belongs in the file
  so the next reader can re-derive it instead of re-litigating it.
- **Name the external authority where there is one**, and say that it wins. When this repo disagrees
  with brand.cornell.edu, the repo is the bug.
- **State enforcement status plainly.** Nothing here is wired into `tools/check`; enforcement is a
  skill plus review. A contract that reads as automated when it is manual is worse than one that
  admits it.
