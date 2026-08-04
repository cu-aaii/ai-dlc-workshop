# Contract — UI design language

**Applies to**: every blueprint that renders something a human reads — a web page, a chat surface, a
dashboard, an emailed report, a generated document.

**Reference implementation**: [`blueprints/aisei-site/`](../blueprints/aisei-site/). Its
`app/client/app/shared/theme/` holds the tokens, `app/docs/wp-migration/style-guide.html` and
`component-library.html` are the visual spec, and `app/.claude/skills/wp-style-guide/` is the skill
that keeps implementation pointed at them. **Build against those files, not against memory.**

**Enforcement**: [`.claude/skills/cornell-ui-compliance/`](../.claude/skills/cornell-ui-compliance/SKILL.md)
triggers on any UI work and blocks non-compliant output. §2 and §3 have **no exemption path** — a
violation is corrected before the work proceeds, and the correction is re-checked.

---

## 0. Authority, and what happens when sources disagree

Three sources, in strict precedence order. Higher always wins.

| # | Source | Status |
|---|---|---|
| **1** | **Accessibility law and Cornell Policy 5.12** | **Non-negotiable. Never waived, for any reason, by anyone.** §2 |
| **2** | **Cornell brand guidelines** — [brand.cornell.edu](https://brand.cornell.edu/logos) | **Non-negotiable for logo and palette.** §3, §4 |
| **3** | `blueprints/aisei-site/` design language | The house implementation. Binding *except* where 1 or 2 overrides it. §5 onward |

This ordering is not decorative — **all three conflict in real, measured ways**, and §2.4 and §5.1
list every conflict found with the number that settles it. Where the reference implementation is
inaccessible, the reference implementation is wrong.

### Scope gating

| Section | Binds when |
|---|---|
| §2 accessibility | **always**, no exceptions, no exemptions |
| §3 Cornell logo | **always when a Cornell mark is present**; presence itself is required on public-facing UIs |
| §4 palette · §5 tokens · §6 type · §7 layout · §8 delivery | **always**, any UI |
| §9 charts and data marks | **only if** the UI plots data |
| §10 conformance checklist | **always** — the reviewable artifact |

---

## 1. Declaring conformance

A blueprint with a UI states its conformance in its own `README.md`, and records any
**§5-and-below** deviation in `blueprints/<name>/docs/`.

There is no machine-readable declaration yet. The natural home would be a `ui:` block in
`blueprints/<name>/blueprint.yaml`, but that manifest is **FROZEN** as a cross-team standard
(`packages/builder-mcp/SPEC.md` §C1 — *no substantive changes without mob agreement*), so adding a key is a
substantive change. **Raised as a proposal for mob agreement, not assumed here.**

**Deviation is declarable for §5 and below. It is not declarable for §2 or §3.** A blueprint may
document that it uses a different card treatment. It may not document that it fails contrast.

---

## 2. Accessibility — non-negotiable

**This is law, not preference. There is no exemption, no "temporary" waiver, and no ticket to fix it
later.** A UI that fails any criterion below is not shipped; it is corrected.

### The standard

**WCAG 2.2 Level AA.** Chosen because it is a superset of every standard that applies to Cornell, so
conforming to it conforms to all of them:

| Obligation | Standard it names |
|---|---|
| **Cornell Policy 5.12** (web accessibility) | WCAG 2.0 AA — cited on Cornell's own colors page: *"a contrast ratio of at least 4.5:1 for normal text and 3:1 for large text"* |
| **ADA Title II** — DOJ final rule, 2024 | WCAG 2.1 AA for public-entity web content |
| **Section 504 / 508** context | WCAG 2.0 AA |
| **This contract** | **WCAG 2.2 AA** — ⊇ 2.1 AA ⊇ 2.0 AA |

**"Large text" uses the stricter of the two definitions in play: over 24px, or 19px if bold.**
Cornell's colors page says *"over 24 pixels — or 19 pixels if bold"*; WCAG says 24px / 18.66px bold.
19px is stricter, so 19px is the rule.

### The criteria that do the work

| Criterion | Level | Requirement |
|---|---|---|
| **1.4.1** Use of Color | A | Color is never the only means of conveying information. Status carries an icon **and** a word |
| **1.4.3** Contrast (Minimum) | AA | **4.5:1** text · **3:1** large text (>24px, or >19px bold) |
| **1.4.11** Non-text Contrast | AA | **3:1** for UI components, component boundaries, focus indicators, and graphics required to understand content |
| **1.4.10** Reflow | AA | Usable at 320px equivalent, no two-dimensional scrolling |
| **1.4.12** Text Spacing | AA | Survives increased line-, letter-, word-spacing. Don't pin heights |
| **1.4.13** Content on Hover or Focus | AA | Tooltips/popovers **dismissable** (Esc, pointer stationary), **hoverable**, **persistent** |
| **2.4.7** Focus Visible | AA | Every interactive element shows focus |
| **2.4.11** Focus Not Obscured | AA | Sticky chrome must not cover the focused element |
| **2.5.8** Target Size (Minimum) | AA | **24 × 24 CSS px** minimum for every interactive target |
| **2.3.3** Animation from Interactions | AAA→enforced | `prefers-reduced-motion` honoured. `aisei-site` already does this; keep it |

### How contrast is measured

WCAG contrast ratio only: `(L1 + 0.05) / (L2 + 0.05)` on relative luminance. **Never judged by eye.**
Every ratio in this document was computed; re-compute rather than trust.

**One limitation, stated because it changes what you must do:** WCAG contrast is a *luminance* ratio.
It does not test hue separation and will not flag two colors that collapse together for a colorblind
reader. That is why 1.4.1's redundancy rules are enforced independently and are not treated as
optional belt-and-braces.

### 2.4 Accessibility overrides applied to the reference implementation

Measured failures in `blueprints/aisei-site/`, each with the fix. **These are corrections to the
reference implementation, not deviations from it.**

| Finding | Measured | Required fix |
|---|---|---|
| **Global focus ring `#2e5690` is invisible on dark surfaces.** `_accessability.scss` applies it with `!important`, so the masthead, hero band, and footer — exactly the carnelian and dark regions — have a failing focus indicator | **1.08:1 on carnelian `#b31b1b`** · 2.36:1 on `#1a1a1a` · 1.71:1 on `#333333` · (7.37:1 on white, fine) | **Surface-aware focus ring.** White (`6.80:1` on carnelian, `17.40:1` on `#1a1a1a`) on dark and carnelian surfaces; black (21.00:1) or carnelian (6.80:1) on white and `#f7f7f7`. 3px, 2px offset, as now |
| `--color-border #e0e0e0` used as a component boundary | **1.32:1** on white | Decorative dividers only. Any input border, control outline, or boundary that conveys a component's extent needs **≥3:1** |
| `--color-warning #F8981D` used as a fill or indicator on white | **2.21:1** on white | Not a mark or boundary on light surfaces. Its text pairing is fine (`#222222` on it = 7.20:1). For a warning *graphic* on white use `#D47500` (3.31:1) |
| White text on `#F8981D` | **2.21:1** | Prohibited. `--color-on-warning: #222222` exists for this reason — use it |

---

## 3. Cornell logo and branding — non-negotiable

**Source of authority: [brand.cornell.edu/logos](https://brand.cornell.edu/logos) and the brand
colors page. Values below are quoted from it.** Where this contract is silent, brand.cornell.edu
governs and `brand@cornell.edu` is the escalation — never local judgment.

### 3.1 Presence

**Required on every public-facing or builder-facing UI.** Internal/admin-only surfaces and
machine-facing output are exempt from *presence* — but any mark that **is** present obeys every rule
below regardless of audience.

### 3.2 Size — exact, not approximate

| Variant | Rule |
|---|---|
| Simple Logo (web) | **73–120 px** |
| Simple Seal (web) | **73–120 px**, and *"the dimension must not exceed 120 pixels"* |
| Reduced Logo (web) | ***must be* 45 px tall** — a fixed value, not a range |
| Bold Logo / Bold Seal (print) | greater than **3/4 inch** tall |
| Reduced Wordmark (print) | used **below 3/4 inch** |

The mark *"should always be reproduced at a size that is legible."* A responsive layout must not
scale the mark outside its band at any breakpoint — this is the rule most often broken by fluid CSS.

### 3.3 Clear space

*"Text, headlines, photographs, or illustrations should never be closer to the logo than **1/4 the
diameter of the seal**."*

At the 120px ceiling that is a **30px** exclusion zone; at 73px it is **~18px**; at the 45px reduced
logo it is **~11px**. Padding, not margin collapse — verify against the rendered box.

### 3.4 Color

**Logos are restricted to carnelian, black, or white.** No other fill, ever.

- Carnelian `#B31B1B` · black `#000000` · white `#FFFFFF`
- Recoloring **between those three** is permitted, and only the fill — never the geometry
- Any other color, gradient, tint, or screen is prohibited

### 3.5 Background

*"The logo may be printed on any background that provides sufficient contrast for the logo to appear
clearly and legibly."*

Brand policy is **contrast-governed, not an allowlist** — which means it composes with §2's 1.4.11
threshold rather than competing with it. The operative rule:

> **Pick the logo variant whose fill clears 3:1 against the surface behind it.**

| Surface | Compliant variant | Measured |
|---|---|---|
| White `#FFFFFF` | **black** (21.00:1) or **carnelian** (6.80:1) | white fill = **1.00:1 — prohibited** |
| Light gray `#F7F7F7` | **black** (19.60:1) or **carnelian** (6.35:1) | white fill = **1.07:1 — prohibited** |
| Carnelian `#B31B1B` | **white** (6.80:1) | black = 3.09:1, large-only — avoid |
| Dark gray `#222222` | **white** (15.91:1) | carnelian = 2.34:1 — **prohibited** |
| Hero `#1a1a1a` / footer `#333333` | **white** (17.40:1 / 12.63:1) | — |
| Dark Warm gray `#A2998B` · Sea gray `#9FAD9F` | **black** (7.47:1 / 8.95:1) | white = 2.81 / 2.35 — **prohibited** |

**Important correction to the reference implementation.** `aisei-site`'s style guide says the marks
need *"a dark/red bg, never white."* That is true **of the white-fill assets it ships**, not of
Cornell's policy. The three SVGs in `blueprints/aisei-site/app/client/assets/` are all white-fill, so
they are dark-surface-only — but a **black or carnelian variant on white is fully brand-compliant**,
and Cornell publishes those (`cornell_logo_simple_black.svg`, `cornell_seal_simple_web_black.svg`).

**A UI on a white plane therefore has two compliant routes** — put the mark in a carnelian or dark
masthead band, or obtain the black/carnelian variant. It must not put the white-fill asset on white.

### 3.6 Repetition

*"Cornell logo appears only once on a homepage or communications piece."* One mark per page. A
masthead seal **and** a footer wordmark on the same page violates this.

### 3.7 Prohibited, absolutely

- ***"No watermarking, screening, or cropping of seal in any designs."***
- ***"Do not attempt to create art for the Cornell logo, seal or wordmark for any application."***
  Use the official asset. Do not redraw, trace, re-letter, or reconstruct it — including in code
  (no CSS/SVG re-creation of the mark).
- Any fill outside carnelian / black / white (§3.4)
- Any variant outside its size band (§3.2)
- Anything inside the clear-space zone (§3.3)
- More than one mark per page (§3.6)

**Not addressed upstream** — rotation, distortion/stretching, drop shadows, outlines, and lockups
with other marks. Given *"do not attempt to create art,"* the conservative reading applies and all of
them are **prohibited here**: aspect ratio locked, no transforms, no effects, no co-branded lockup
assembled locally. **Anything not explicitly permitted requires brand consultation** —
`brand@cornell.edu` or the consultation form — not a local decision.

### 3.8 The wordmark-as-text question

`aisei-site` renders *"Cornell University / AI Innovation Hub"* as **HTML text, not an image**, which
is what the live site does. Treat that as a **typographic lockup, not a logo**: it is subject to §6
type rules and §2 contrast, and it does **not** count as the one permitted mark under §3.6. Whether
it is an approved unit signature is a brand question, not ours — if a unit signature is wanted, get
the official lockup asset rather than setting one in CSS.

---

## 4. Palette — Cornell official

**Source: brand.cornell.edu colors page.** Proportions are Cornell's own: **~90% primary, ~7%
secondary, ~3% accent.**

### Primary — ~90%

| Color | Hex | Vetted pairings |
|---|---|---|
| Carnelian | `#B31B1B` | White, Light gray |
| Dark gray | `#222222` | White, Light gray |
| White | `#FFFFFF` | Carnelian, Dark gray |

**The "first and only" rule for red:** carnelian is *"the **first** color people see"* in multi-color
media and the *"**only** color"* in limited-color media. It is brand-leading, and — per §9 — it is
never a data-encoding color.

A practical decomposition of the 90%, if you want a working budget: **~55% white, ~20% carnelian,
~15% dark gray.**

### Secondary — ~7%

| Color | Hex | Text on it |
|---|---|---|
| Light gray | `#F7F7F7` | Carnelian, Dark gray |
| Dark Warm gray | `#A2998B` | **Black only** (7.47:1). White = 2.81:1, prohibited |
| Sea gray | `#9FAD9F` | **Black only** (8.95:1). White = 2.35:1, prohibited |

*"Neutral hues"* that support rather than drive a layout.

### Accent — ~3%

Cornell publishes per-use variants because the base accents are not all text-safe. **This table adds
the 1.4.11 measurement, which narrows it further.**

| Accent | Base (graphics) | Text-safe | Large-text only | On white — **1.4.11 verdict** |
|---|---|---|---|---|
| Blue / link | `#006699` | `#006699` | — | **6.25:1 ✓** |
| Green | `#6EB43F` | `#4B7B2B` | `#578E32` | base **2.54:1 ✗** · `#4B7B2B` 5.04 ✓ · `#578E32` 3.95 ✓ |
| Orange | `#F8981D` | — | `#D47500` | base **2.21:1 ✗** · `#D47500` 3.31 ✓ |
| Secondary Red | `#EF4035` | `#DF1E12` | — | `#EF4035` 3.85 ✓ · `#DF1E12` 4.85 ✓ |
| Navy | `#073949` | `#073949` | — | **12.42:1 ✓** |

> **Accessibility override:** Cornell labels `#6EB43F` and `#F8981D` *"graphics only"*, which means
> *don't set text in them* — **it does not mean they are safe as graphics on white.** Both fail
> 1.4.11 (2.54:1 and 2.21:1). **Neither may be a mark, fill, icon, or boundary on a light surface.**
> Use `#578E32` / `#4B7B2B` and `#D47500`. This is §0 precedence in action.

Accents *"should not be used as full-color bleeds"* and must never become a unit's primary color.

### Status — reserved

Every UI has states. Mapped to Cornell accents that clear 4.5:1 as text on both light surfaces:

| Role | Hex | on `#FFFFFF` | on `#F7F7F7` |
|---|---|---|---|
| good | `#4B7B2B` | 5.04 ✓ | 4.70 ✓ |
| warning | `#D47500` | 3.31 — **large text or graphic only** | 3.09 — same |
| critical | `#DF1E12` | 4.85 ✓ | 4.52 ✓ |

**Always icon + word, never color alone** (1.4.1). **Status hues are reserved**: the green, orange,
and red families are not available for identity, category, or decoration.

**Carnelian is never a status color.** It is 1.31:1 from `#b34f1b`-class oranges and 1.15:1 from
`#cc0000`-class reds — a status chip on or beside carnelian chrome is unreadable as an alarm. Status
lives on the white or light-gray plane.

---

## 5. Tokens — use the reference implementation

Take tokens from `blueprints/aisei-site/app/client/app/shared/theme/_variables.scss`. **Never hardcode
a hex in a component** — the `wp-style-guide` skill's rule, and it holds repo-wide. If a token is
missing, add it to `_variables.scss` and its swatch to `style-guide.html` in the same change; the two
must not drift.

Available and correct as-is: `--color-accent #b31b1b`, `--color-accent-dark #a01114` (white on it =
8.12:1), `--color-primary #2d668e` (6.17:1), `--color-link #1176ac` (4.99:1), `--color-on-warning
#222222`, the hero band (`--color-hero-bg #1a1a1a`, white = 17.40:1), footer (`#333333` with
`#bbbbbb` = 6.58:1), and the hero accents (`#a66dd5` = 4.78:1, `#c6b20f` = 8.10:1 on `#1a1a1a`).

### 5.1 Tokens that need care

| Token | Constraint |
|---|---|
| `--color-border #e0e0e0` | **1.32:1** — decorative only. Never a component boundary (§2.4) |
| `--color-warning #F8981D` | **2.21:1** — never a fill/indicator on light. Text on it must be `#222222` (§2.4) |
| `--color-hero-accent-1/-2` | Dark-background only, for italic headline words. Not general UI colors — the reference skill says so and it is right |
| `--color-primary #2d668e` | Defined but unused in live chrome. **Do not force it into hero/footer** just because it exists |
| focus ring `#2e5690` | Must become surface-aware (§2.4) |

---

## 6. Type

`aisei-site` tokens: `--heading-font: "freight-sans-pro", Georgia, serif` and `--body-font:
"freight-sans-pro", Verdana, Geneva, Tahoma, sans-serif`.

- **Ship a real system fallback.** `freight-sans-pro` is an Adobe Fonts (Typekit) family, so it is not
  self-contained — see §8. If the webfont is blocked the UI must still be readable.
- **Inputs stay ≥16px** — `_accessability.scss` enforces this to stop mobile auto-zoom. Keep it.
- **Large text is >24px, or >19px bold** (§2). A 15px caption gets no relief and needs the full 4.5:1.
- **Numerals**: `font-variant-numeric: lining-nums` for anything read as data; add `tabular-nums`
  only where numbers align vertically. Large standalone values stay proportional.

---

## 7. Layout

- `$cwd-container-fluid-max-width: 1280px`; breakpoints from `_variables.scss`
  (`$screen-sm-min: 768px`, `$screen-md-min: 992px`, `$screen-lg-min: 1200px`, …). **Reuse them —
  do not invent breakpoints.**
- **One control row above everything it scopes.** Filters and scope selectors sit above the content,
  never inside individual cards. If sticky, satisfy **2.4.11**.
- **1.4.10 Reflow** at 320px equivalent; **1.4.12 Text Spacing** survives increased spacing.
- Size containers to include their labels — a height that fits content but not its caption or axis
  band produces a nested scrollbar.
- Honour `prefers-reduced-motion` (already in `_accessability.scss`).

---

## 8. Delivery and Content-Security-Policy

**A blueprint UI serves a CSP with no `unsafe-inline` and no `unsafe-eval`.**

- **No inline `<script>`**, including build-injected bootstrap
- **No inline `<style>`**, and no runtime CSS-in-JS that injects one
- **No `eval` / `new Function`**
- **No inline `style="…"` carrying color** — use custom properties and classes
- Declare the palette once as custom properties; reference roles, not hexes

**Model A — bundled SPA** (Angular, as `aisei-site`; or Vite). Emit CSS as hashed external files. The
**dev server does not run under the production CSP** — verify against a production build or a
violation ships unseen. With Vite specifically, `build.modulePreload.polyfill = false`: the polyfill
is an inline script and will be blocked.

**Model B — HTML served directly by compute** (Lambda, container). The simplest model and the most
likely to violate the policy, because a self-contained page is the natural way to write it. **Send
the CSP header from the handler**; a page with no CSP is non-conformant even if nothing inline is
present. Move CSS/JS to separate routes. If it must stay one file, it takes a **declared exemption
for §8 only** — never for §2 or §3.

**Webfont**: self-host the `woff2` and keep `font-src 'self'`, or use the Typekit **CSS `<link>`** —
never the JS loader, which injects an inline script. The link route needs `https://use.typekit.net` in
`style-src` and `https://use.typekit.net https://p.typekit.net` in `font-src`.

---

## 9. Charts and data marks

**Binds only if the UI plots data.**

### Series palette

Cornell's accent palette has essentially **one identity-neutral accent**, because green, orange, and
red are reserved for status (§4) and the base green/orange fail 1.4.11 anyway.

| Slot | Color | Hex | on `#FFFFFF` | on `#F7F7F7` |
|---|---|---|---|---|
| 1 | Blue | `#006699` | 6.25 ✓ | 5.83 ✓ |
| 2 | Navy | `#073949` | 12.42 ✓ | 11.60 ✓ |
| de-emphasis / "Other" | Dark gray | `#222222` | 15.91 ✓ | 14.85 ✓ |

**Two identity slots, plus a de-emphasis gray. That is the honest ceiling** of Cornell's approved
palette with status reserved — and it is consistent with the 3% accent cap, which cannot fund eight
hues. Beyond two series: rank by the measure, keep the top two, fold the rest into "Other", and put
the full breakdown in the table view.

**Marks live on white or `#F7F7F7`, never the dark band** — blue is 2.55:1 on `#222222` and fails.

### Redundancy is mandatory, and here is why

Contrast **between** the marks: blue↔navy **1.99**, blue↔dark gray **2.55**, navy↔dark gray **1.28**.
All below 3:1, and not fixable by substitution — the approved palette contains no two identity-safe
hues that reach 3:1 between themselves.

1.4.11 binds on *"graphics required to understand the content."* These charts make color redundant by
construction, so each of the following is **required, not an enhancement**:

- A legend whenever two or more series are present
- **Direct labels on every series**
- **A table-view twin for every chart** — every value reachable as text
- **A 2px surface-colored gap between touching fills**

Remove any one and the chart fails AA.

### Emphasis is the preferred form

A hue against gray does clear 3:1 in the right direction, and with only two identity slots the
emphasis pattern — one series in blue, the rest in `#222222` — is both the clearer chart and the
stronger compliance position. **Prefer it whenever the story is about one series.**

### Marks

| Mark | Spec |
|---|---|
| Bar / column | ≤24px thick; 4px rounded data-end, square at the baseline; one shared baseline |
| Line | 2px, round join and cap |
| Marker / end-dot | ≥8px (r ≥ 4) |
| Area fill | series hue at ~10% opacity — a wash, never a saturated block |
| Gridlines / axes | 1px solid, recessive, **never dashed** |

Gridlines are decorative, so no contrast floor applies — **and therefore a gridline must never be the
only way to read a value.** A threshold or target line *is* a data mark: it clears 3:1 and it is
labeled.

Separation is done with a **2px surface gap** and a **2px surface ring** on overlapping markers, never
a stroke around a mark.

**Text never wears the series color.** Labels, values, legend, and axis text use ink tokens; identity
comes from the swatch beside the text. A label inside a fill picks black or white by the fill's
luminance and must itself clear 4.5:1.

### Anti-patterns

1. **Dual-axis charts.** Two y-scales invent a correlation the data does not contain. Two charts,
   small multiples, or index to a common base on one axis.
2. **A value ramp on nominal categories** — double-encodes what bar length already shows.
3. **Recolor-on-filter.** Bind hue to entity with a stable map computed once.
4. **Carnelian as a data color** (§3, §4).
5. **A number on every point.** Label the endpoint, the extreme, or the series that matters.
6. **A one-bar bar chart or two-slice pie.** That is a stat tile.

---

## 10. Conformance checklist

**Accessibility — §2. No exemptions.**
- [ ] Every text/background pair computed: ≥4.5:1 normal, ≥3:1 large (>24px / >19px bold)
- [ ] Every UI component, boundary, focus ring, and meaningful graphic ≥3:1
- [ ] Focus ring is **surface-aware** and visible on carnelian and dark bands
- [ ] No information conveyed by color alone; status is icon + word
- [ ] Interactive targets ≥24×24 CSS px
- [ ] Tooltips dismissable, hoverable, persistent
- [ ] Usable at 320px; survives increased text spacing; `prefers-reduced-motion` honoured
- [ ] `#6EB43F` and `#F8981D` do not appear as marks/fills/boundaries on light surfaces

**Cornell logo — §3. No exemptions.**
- [ ] Present on any public-facing UI
- [ ] Official asset used — **not** redrawn, traced, or CSS/SVG-reconstructed
- [ ] Size inside its band: simple 73–120px · seal ≤120px · reduced **exactly 45px**
- [ ] Size band holds **at every breakpoint**
- [ ] Clear space ≥ 1/4 the seal's diameter on all sides
- [ ] Fill is carnelian, black, or white — nothing else
- [ ] Variant's fill clears **3:1** against its actual background (§3.5 table)
- [ ] **Exactly one** Cornell mark on the page
- [ ] No watermark, screen, crop, rotation, distortion, shadow, outline, or local lockup

**Palette and tokens — §4, §5**
- [ ] ~90% primary / ~7% secondary / ~3% accent, roughly respected
- [ ] Carnelian reads first; it encodes nothing
- [ ] Tokens from `_variables.scss`; no hardcoded hex in components
- [ ] Status families not reused for identity or decoration

**Type, layout, delivery — §6, §7, §8**
- [ ] Cornell font stack with a working system fallback; inputs ≥16px
- [ ] Existing breakpoints reused
- [ ] CSP sent with no `unsafe-inline`/`unsafe-eval`, verified against a **production** build

**Charts — §9, if applicable**
- [ ] ≤2 identity series + "Other"; marks on light surfaces only
- [ ] Legend, direct labels, table-view twin, 2px gaps all present

---

## 11. Enforcement — what happens on a violation

Wired as [`.claude/skills/cornell-ui-compliance/`](../.claude/skills/cornell-ui-compliance/SKILL.md),
which triggers on any UI work.

**For §2 (accessibility) and §3 (logo), the loop is:**

1. **Stop.** Do not write, ship, or commit the violating output.
2. **Name it precisely** — the rule, the measured value, the threshold. *"`#F8981D` on white is
   2.21:1; 1.4.11 requires 3:1"*, not *"this may have contrast issues."*
3. **Prompt for an adjustment**, offering at least one compliant alternative drawn from the approved
   palette or asset set.
4. **Re-check the adjustment against this contract.** A correction is not accepted on the author's
   word — it is measured. If the adjustment introduces a new violation, return to step 1.
5. **Loop until clean.** There is no iteration limit and no ship-anyway path.

**A user may not waive §2 or §3, and neither may an agent.** If someone insists, the response is to
say plainly that these are legal and brand obligations rather than preferences, offer the nearest
compliant alternative, and — for anything genuinely outside the documented rules — route to
`brand@cornell.edu` or Cornell's accessibility office. Not to comply and note it.

§5 and below are different: a documented deviation in `blueprints/<name>/docs/` is legitimate.

---

## 12. Extending this contract

1. New color values come from **brand.cornell.edu**, then `aisei-site`'s tokens. Do not invent hexes.
2. **Compute the WCAG ratio against every surface the color appears on.** Never eyeball.
3. Apply the right threshold: 4.5:1 text, 3:1 large text and meaningful non-text.
4. For a mark, also check it against the fills beside it. If no pair reaches 3:1 — the normal case
   here — the §9 redundancy items are mandatory.
5. **Record the ratio in the tables above**, so the next reader inherits measurements.
6. Logo rules change only at brand.cornell.edu. If this file disagrees with that page, **that page is
   right and this file is a bug** — fix it here and note the date.
7. A blueprint-specific deviation belongs in that blueprint's `docs/`, and only for §5 and below.
