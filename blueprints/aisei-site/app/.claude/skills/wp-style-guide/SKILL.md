---
name: wp-style-guide
description: >
  Reference the WordPress-migration design tokens and component patterns before building or
  styling any public-facing page or component in this project.
  TRIGGER when: building/styling a public page or shared component (hero, masthead, nav,
  cards, footer, buttons), adding or changing a color/font/spacing token, or asked what
  something should look like ("what does the event card look like on the live site").
  DO NOT TRIGGER when: working only on admin dashboard/settings styling, or on server-side/
  logic-only changes with no visual output.
---

# WP Style Guide & Component Library

Two standalone HTML files produced while migrating innovationhub.ai.cornell.edu (WordPress)
into this Angular/Hono app. They are the visual spec for the migration — build every new
component/page against them, not against memory of the live site.

- `docs/wp-migration/style-guide.html` — color tokens (existing + new), type scale, spacing
  scale, breakpoints, Cornell logo/seal usage, buttons.
- `docs/wp-migration/component-library.html` — one page rendering every reusable pattern with
  real markup/CSS: masthead + utility bar, primary nav w/ dropdowns, mobile nav, hero,
  decorative cards, quote block, article/project/event/person/tool cards, buttons, footer.

## How to use them

1. Open the file directly before implementing anything (plain HTML/CSS, no build step) —
   `file://<repo>/docs/wp-migration/component-library.html`, or view source.
2. Find the section matching the component you're about to build (e.g. "Event card").
3. Copy its markup structure and CSS as the spec, then translate into an Angular standalone
   component per the `angular-component` skill (signals, OnPush, `host` bindings,
   `@if`/`@for`, no `standalone: true`).
4. Never hardcode a hex color in a new component's styles — use the CSS custom property named
   in `style-guide.html` (`--color-accent`, `--color-hero-bg`, `--color-hero-accent-1`, etc.).
   If a token isn't in `client/app/shared/theme/_variables.scss` yet, add it there first (see
   the guide's "new tokens" section), then reference it.
5. Match spacing/breakpoints from the guide's tables — reuse the existing SCSS vars
   (`$screen-sm-min`, etc.) instead of inventing new breakpoints.

## Keeping them in sync

These are living references for the length of the migration, not one-off snapshots.

- New pattern variant discovered during implementation (e.g. a new card state)? Add a section
  for it in `component-library.html` before/while building the Angular component.
- New token introduced? Add its swatch to `style-guide.html` in the same change that adds it
  to `_variables.scss` — the two must never drift.
- Extend an existing section (e.g. a new `.badge` variant next to the existing ones) rather
  than creating a near-duplicate block.

## Known quirks (already resolved — don't re-derive)

- Both "logo" SVGs shipped by the WP theme (`cornell_logo_simple_b31b1b.svg`,
  `cornell_seal.svg`) are the same white-fill circular seal icon at different weights — render
  on a dark/red background only, never white. The "Cornell University / AI Innovation Hub"
  wordmark in the live masthead is HTML text, not an image.
- `--color-primary` (Cornell blue) exists in the template but isn't used anywhere in this
  site's live chrome — don't force it into hero/footer just because it's defined.
- `--color-hero-accent-1` (purple) / `--color-hero-accent-2` (yellow) are dark-background-only
  accent colors for italic headline words, not general-purpose UI colors.
