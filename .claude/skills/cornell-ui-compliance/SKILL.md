---
name: cornell-ui-compliance
description: >
  Enforce Cornell's brand and accessibility rules on any UI a blueprint renders. Read BEFORE
  writing markup, styles, a component, a chart, or a page — not after.
  TRIGGER when: building or styling any user-facing output (page, component, email, report,
  chat surface, dashboard, chart); choosing or changing any color, font, spacing, or breakpoint;
  placing or resizing a Cornell logo, seal, or wordmark; setting a focus style; writing a CSP;
  or when asked "does this meet accessibility / brand".
  DO NOT TRIGGER when: the work has no rendered human-facing output (IaC, pipeline wiring,
  server logic with no view, machine-consumed JSON).
---

# Cornell UI compliance

The rules are in [`contracts/ui-design-language.md`](../../../contracts/ui-design-language.md). This
skill is how they are enforced. The design language itself lives in
[`blueprints/aisei-site/`](../../../blueprints/aisei-site/) — build against its tokens and its
`docs/wp-migration/` style guide, never against memory.

**Two of these rule sets cannot be waived by anyone, including the user:**

| Rule set | Why | Waivable? |
|---|---|---|
| **Accessibility** — WCAG 2.2 AA | Legal obligation: Cornell Policy 5.12, ADA Title II (DOJ 2024 → WCAG 2.1 AA), Section 504/508. 2.2 AA is a superset of all three | **Never** |
| **Cornell logo** | Brand policy, brand.cornell.edu, enforced by University Relations | **Never** |
| Tokens, components, layout | House design language | Yes, if documented in `blueprints/<name>/docs/` |

---

## The loop — on any violation of accessibility or logo rules

1. **Stop.** Do not write, ship, or commit the violating output. Do not "note it for later."
2. **Name it precisely**: the rule, the measured value, the threshold.
   > "`#F8981D` on `#ffffff` is **2.21:1**. WCAG 1.4.11 requires **3:1** for a non-text graphic.
   > Cornell's own palette lists it graphics-only, which means don't set text in it — it does not
   > make it usable as a fill on white."

   Not: "this might have contrast issues."
3. **Offer a compliant alternative** from the approved palette or asset set. Always at least one.
4. **Re-measure the adjustment.** A correction is never accepted on assertion — compute it. If the
   adjustment introduces a new violation, return to step 1.
5. **Loop until clean.** No iteration cap, no ship-anyway path.

**If the user pushes back**, say plainly that these are legal and brand obligations rather than
preferences, offer the nearest compliant option, and route genuinely undocumented cases to
`brand@cornell.edu` or Cornell's accessibility office. Do not comply and annotate.

---

## Measure contrast — never estimate it

```js
const chan = c => c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4);
const rgb  = h => { h = h.replace('#','').toLowerCase();
  if (h.length === 3) h = h.split('').map(c=>c+c).join('');
  return [0,2,4].map(i => parseInt(h.slice(i,i+2),16)/255); };
const lum  = h => { const [r,g,b] = rgb(h).map(chan); return 0.2126*r + 0.7152*g + 0.0722*b; };
const cr   = (a,b) => { const [hi,lo] = [lum(a),lum(b)].sort((x,y)=>y-x); return (hi+0.05)/(lo+0.05); };
```

**Thresholds**: text **4.5:1** · large text **3:1** (large = **>24px, or >19px bold** — Cornell's
definition, stricter than WCAG's 18.66px) · UI components, boundaries, focus rings, and meaningful
graphics **3:1**.

Check against **every** surface the color actually appears on. A value that passes on white and fails
on `#f7f7f7` is unusable in a component that appears on both.

---

## Accessibility gate

- [ ] Every text/background pair measured and passing
- [ ] Every component boundary, focus ring, icon, and meaningful graphic ≥3:1
- [ ] **Focus ring is surface-aware** (see the trap below)
- [ ] Nothing conveyed by color alone — status is **icon + word**
- [ ] Interactive targets **≥24×24 CSS px**
- [ ] Tooltips dismissable (Esc, pointer stationary), hoverable, persistent
- [ ] Usable at 320px; survives increased text spacing; `prefers-reduced-motion` honoured
- [ ] Inputs ≥16px (stops mobile auto-zoom — already in `_accessability.scss`)

### Known traps in the reference implementation

These are **already-measured failures in `aisei-site`**. Do not copy them forward, and do not
re-derive them.

| Trap | Measured | Do this |
|---|---|---|
| Global focus ring `#2e5690`, applied with `!important` | **1.08:1 on carnelian**, 2.36:1 on `#1a1a1a`, 1.71:1 on `#333333` (7.37:1 on white) | **Surface-aware ring.** White on carnelian/dark (6.80 / 17.40), black or carnelian on white/`#f7f7f7` (21.00 / 6.80). Keep 3px + 2px offset |
| `--color-border #e0e0e0` as a component boundary | **1.32:1** | Decorative dividers only. Boundaries need ≥3:1 |
| `--color-warning #F8981D` as fill/indicator on light | **2.21:1** | Use `#D47500` (3.31:1). Text on the orange must be `#222222` (7.20:1) |
| White text on `#F8981D` | **2.21:1** | Prohibited — use `--color-on-warning: #222222` |
| Cornell base green `#6EB43F` as a mark on white | **2.54:1** | Use `#578E32` (3.95) or `#4B7B2B` (5.04) |

---

## Cornell logo gate

**Never** redraw, trace, re-letter, or reconstruct the mark — including in CSS or hand-written SVG.
*"Do not attempt to create art for the Cornell logo, seal or wordmark for any application."* Use the
official asset.

- [ ] Present on any public-facing UI (internal/admin exempt from *presence* only)
- [ ] **Size in band**: simple logo/seal **73–120px** · seal **never >120px** · reduced logo **exactly
      45px tall** · print bold >3/4", reduced wordmark <3/4"
- [ ] Band holds **at every breakpoint** — fluid CSS is the usual way this breaks
- [ ] **Clear space** ≥ **1/4 the seal's diameter** on all sides (30px at 120px, ~18px at 73px,
      ~11px at 45px). Padding, not collapsible margin
- [ ] Fill is **carnelian `#B31B1B`, black `#000000`, or white `#FFFFFF`** — nothing else, ever.
      Recolor only between those three, and only the fill, never the geometry
- [ ] **Exactly one** Cornell mark per page
- [ ] No watermark, screen, crop, rotation, distortion, shadow, outline, or locally-assembled lockup

### Pick the variant by background — measured

| Background | Use | Prohibited |
|---|---|---|
| White `#FFFFFF` | black (21.00) or carnelian (6.80) | **white fill — 1.00:1** |
| Light gray `#F7F7F7` | black (19.60) or carnelian (6.35) | **white fill — 1.07:1** |
| Carnelian `#B31B1B` | white (6.80) | carnelian-on-carnelian; black is 3.09 (large only) |
| Dark gray `#222222` | white (15.91) | **carnelian — 2.34:1** |
| Hero `#1a1a1a` / footer `#333333` | white (17.40 / 12.63) | — |
| Warm gray `#A2998B` / Sea gray `#9FAD9F` | black (7.47 / 8.95) | **white — 2.81 / 2.35** |

**The correction most likely to be needed:** the three SVGs in
`blueprints/aisei-site/app/client/assets/` are all **white-fill**, so they are dark-surface-only. The
style guide's "never on white" describes *those assets*, not Cornell policy — brand policy is
contrast-governed, so a **black or carnelian mark on white is fully compliant**. A white-plane UI
either puts the mark in a carnelian/dark masthead band **or** uses the black/carnelian variant from
brand.cornell.edu. It must not put the white-fill asset on white.

The `"Cornell University / AI Innovation Hub"` text in the masthead is **HTML text, a typographic
lockup — not a logo.** It does not satisfy the logo requirement and does not consume the
one-mark-per-page allowance.

---

## Palette quick reference

**Primary ~90%** — carnelian `#B31B1B` · dark gray `#222222` · white `#FFFFFF`
(working split ≈ 55% white / 20% carnelian / 15% dark gray)

**Secondary ~7%** — light gray `#F7F7F7` · warm gray `#A2998B` **(black text only)** · sea gray
`#9FAD9F` **(black text only)**

**Accent ~3%** — blue `#006699` · green `#4B7B2B` text / `#578E32` large / ~~`#6EB43F`~~ fails on
light · orange `#D47500` large-or-graphic / ~~`#F8981D`~~ fails on light · secondary red `#DF1E12`
text / `#EF4035` graphic · navy `#073949`

**Carnelian reads first and encodes nothing.** Not a data color, not a status color, never inside a
plot area. Status = green/orange/red families, reserved, always with an icon and a word.

**Tokens come from** `blueprints/aisei-site/app/client/app/shared/theme/_variables.scss`. Never
hardcode a hex in a component. Missing token → add it there *and* to
`app/docs/wp-migration/style-guide.html` in the same change.

---

## Charts

Only two identity-safe series exist in Cornell's palette once status hues are reserved: **blue
`#006699`** and **navy `#073949`**, plus **dark gray `#222222`** for de-emphasis and "Other".

Contrast *between* those marks is 1.99 / 2.55 / 1.28 — all under 3:1, and unfixable within the
approved palette. So **redundancy is mandatory, not optional**: legend, direct labels on every series,
a table-view twin, and a 2px surface gap between touching fills. Remove any one and the chart fails
1.4.11.

**Prefer emphasis** — one series in blue, the rest in `#222222`. Marks go on white or `#F7F7F7` only;
blue is 2.55:1 on the dark band and fails there.

Never: dual-axis plots, a value ramp on nominal categories, recolor-on-filter, carnelian as data, or a
number on every point.

---

## Delivery

CSP with **no `unsafe-inline`, no `unsafe-eval`**. No inline `<script>` or `<style>`, no runtime
CSS-in-JS that injects a style element, no inline `style="…"` carrying color.

**Verify against a production build** — a dev server injects inline styles and an HMR bootstrap, so it
never exercises the real policy. HTML served straight from a Lambda must send the CSP header from the
handler; a page with no CSP is non-conformant even when nothing inline is present.

Webfont: self-host the `woff2`, or use the Typekit **CSS link** — never the JS loader, which injects
an inline script.
