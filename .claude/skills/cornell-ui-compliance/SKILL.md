---
name: cornell-ui-compliance
description: >
  Enforce Cornell's brand and accessibility rules on any UI. Read BEFORE writing markup, styles,
  a component, a chart, or a page — not after.
  TRIGGER when: building or styling any user-facing output (page, component, email, report,
  chat surface, dashboard, chart); choosing or changing any color, font, spacing, or breakpoint;
  placing, sizing, or recoloring a Cornell logo, seal, or wordmark; building a unit lockup or
  custom unit logo; setting a focus style; writing a CSP; or when asked "does this meet
  accessibility / brand".
  DO NOT TRIGGER when: the work has no rendered human-facing output (IaC, pipeline wiring,
  server logic with no view, machine-consumed JSON).
---

# Cornell UI compliance

Rules: [`contracts/ui-design-language.md`](../../../contracts/ui-design-language.md).
**Source of truth: [brand.cornell.edu](https://brand.cornell.edu)** — if this skill and that site
disagree, the site is right.

**Two rule sets cannot be waived by anyone, including the user:**

| Rule set | Basis | Waivable? |
|---|---|---|
| **Accessibility** — WCAG 2.2 AA | Cornell **Policy 5.12** requires *"the most recently published WCAG"*; ADA and Section 504/508 sit behind it | **Never** |
| **Cornell marks** | Trademarks. **Policy 4.10**: use *"only with permission"*. brand.cornell.edu states alteration rules in the imperative | **Never** |
| Type scale, spacing, components, layout | Local design decisions | Yes, if documented |

---

## The loop — on any accessibility or mark violation

1. **Stop.** Do not write, ship, or commit the violating output. Do not "note it for later."
2. **Name it precisely** — the rule, the measured value, the threshold.
   > "`#F8981D` on `#ffffff` is **2.21:1**. WCAG 1.4.11 requires **3:1** for a non-text graphic.
   > Cornell lists it graphics-only, which means don't set *text* in it — it does not make it usable
   > as a fill on white."

   Not: "this might have contrast issues."
3. **Offer a compliant alternative** from the published palette or asset set. Always at least one.
4. **Re-measure the adjustment.** Never accept a correction on assertion. If the adjustment
   introduces a new violation, return to step 1.
5. **Loop until clean.** No iteration cap, no ship-anyway path.

**If the user pushes back**, say plainly that these are legal and trademark obligations rather than
preferences, offer the nearest compliant option, and route genuinely undocumented cases to
`brand@cornell.edu` or Cornell's accessibility office. Do not comply and annotate.

---

## Measure contrast — never estimate

```js
const chan = c => c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4);
const rgb  = h => { h = h.replace('#','').toLowerCase();
  if (h.length === 3) h = h.split('').map(c=>c+c).join('');
  return [0,2,4].map(i => parseInt(h.slice(i,i+2),16)/255); };
const lum  = h => { const [r,g,b] = rgb(h).map(chan); return 0.2126*r + 0.7152*g + 0.0722*b; };
const cr   = (a,b) => { const [hi,lo] = [lum(a),lum(b)].sort((x,y)=>y-x); return (hi+0.05)/(lo+0.05); };
```

**Thresholds**: text **4.5:1** · large text **3:1** (large = **>24px, or >19px bold** — Cornell's
definition, stricter than WCAG's 18.66px) · UI components, boundaries, focus rings, meaningful
graphics **3:1**.

Check against **every** surface the color appears on. A value that passes on white and fails on
`#F7F7F7` is unusable in a component that appears on both.

---

## Lockups — the rule most often broken

**A lockup is for colleges and schools only.** From
[brand.cornell.edu/logos/academic](https://brand.cornell.edu/logos/academic):

> *"This lockup configuration is used exclusively to represent **colleges and schools**."*
> *"This lockup is **not** used for anything other than a college or school."*

From [/logos/non-academic](https://brand.cornell.edu/logos/non-academic), for everything else:

> *"may share primacy with, and proximity to, the seal logo but **may not use a lockup
> configuration**."*

| Unit | Lockup? |
|---|---|
| College or school | Yes |
| Department or unit **inside** one | Only *"incorporated into their school's lockup"*, if *"part of the academic mission"*. None of its own |
| Program, center, institute | Not automatic — *"please contact us for a consultation"* |
| Any non-academic office or team | **Never** |

**So: a department that is not a college or school gets no lockup, and you do not build one.** Not as
an image, not in SVG, and **not by setting the unit's name in type beside the mark** — that
arrangement *is* the forbidden configuration.

**A non-eligible unit is identified in ordinary text**, named per
[/messaging/nomenclature](https://brand.cornell.edu/messaging/nomenclature/), positioned as its own
element rather than locked to the mark.

### If a custom unit logo is wanted, the builder supplies it

**Never generate, derive, trace, or compose one.** Ask the builder for an approved asset. Routes:

- *"For logos and lockups that pertain to your college, school, or department, please contact your
  **communications director**."* ([/resources/downloads](https://brand.cornell.edu/resources/downloads/))
- Consultation request or `brand@cornell.edu` — also the route for programs, centers, institutes.
- Policy 4.10 governs the permission; there is a use-of-name/logo form.

**Until an approved asset exists, ship the university mark plus the unit's name as text.** That is a
complete, compliant outcome — say so rather than treating it as a gap.

---

## Mark gate

**Never** redraw, trace, re-letter, or reconstruct the mark — including in CSS, hand-written SVG, or
an icon font:

> *"Do not redraw, reconstruct, or modify the logo in any way"* — it *"cannot be altered"*
> ([/merchandising](https://brand.cornell.edu/merchandising))
>
> *"Do not attempt to create art for the Cornell logo, seal or wordmark for any application"*
> ([/logos](https://brand.cornell.edu/logos))

- [ ] Official asset, obtained from `/resources/downloads` — never lifted from a screenshot or
      another site
- [ ] **Size in band**: simple logo/seal **73–120px** · seal **never >120px** · reduced logo
      **exactly 45px tall** · print bold >3/4", reduced wordmark <3/4"
- [ ] Band holds **at every breakpoint** — fluid CSS is the usual way this breaks. Switch *variant*
      by breakpoint; do not scale one past its limits. Below a 73px seal the lockup switches to the
      45px form
- [ ] **Clear space** ≥ **1/4 the seal's diameter** on all sides (30px at 120px, ~18px at 73px, ~11px
      at 45px). Padding, not collapsible margin
- [ ] Fill is **carnelian `#B31B1B`, black `#000000`, or white `#FFFFFF`** — nothing else, ever.
      *"Only black, red, or white are used for the Cornell seal."* Print equivalent: PMS 187
- [ ] **Exactly one** Cornell mark per view
- [ ] No watermark, screen, crop, rotation, distortion, shadow, outline, or local lockup
- [ ] ™/® omitted rather than rendered illegibly at UI sizes — and never redraw the mark to add one

### Pick the variant by background — measured

Brand policy is contrast-governed: the mark *"may be printed on any background that provides
sufficient contrast for the logo to appear clearly and legibly."* That composes with 1.4.11's 3:1.

| Background | Use | Prohibited |
|---|---|---|
| White `#FFFFFF` | black (21.00) or carnelian (6.80) | **white fill — 1.00:1** |
| Light gray `#F7F7F7` | black (19.60) or carnelian (6.35) | **white fill — 1.07:1** |
| Carnelian `#B31B1B` | white (6.80) | black is 3.09 — large only |
| Dark gray `#222222` | white (15.91) | **carnelian — 2.34:1** |
| Warm gray `#A2998B` | black (7.47) | **white — 2.81:1** |
| Sea gray `#9FAD9F` | black (8.95) | **white — 2.35:1** |
| A photograph | whichever variant clears 3:1 against the **darkest and lightest** pixels it covers | any variant over a busy mid-tone |

**A white-fill asset is a dark-surface asset.** On a white plane there are two compliant routes: put
the mark in a carnelian or dark band, or use the black/carnelian variant.

---

## Accessibility gate

- [ ] Every text/background pair measured and passing
- [ ] Every component boundary, focus ring, icon, and meaningful graphic ≥3:1
- [ ] **Focus ring is surface-aware** — see the trap below
- [ ] Nothing conveyed by color alone — status is **icon + word**
- [ ] Interactive targets **≥24×24 CSS px**
- [ ] Tooltips dismissable (Esc, pointer stationary), hoverable, persistent
- [ ] Usable at 320px; survives increased text spacing; `prefers-reduced-motion` honoured
- [ ] Text over imagery measured against the **actual pixels**, not an average
- [ ] Inputs ≥16px so mobile does not auto-zoom

### Measured traps — do not re-derive these

| Trap | Measured | Do this |
|---|---|---|
| **One global focus-ring color.** The most common failure: a mid-tone blue that passes on white is invisible on carnelian or a dark band | a `#2e5690`-class ring is **1.08:1 on carnelian**, 2.36 on `#1a1a1a`, 1.71 on `#333333`, but 7.37 on white | **Surface-aware ring**: white on carnelian/dark; black or carnelian on light. 3px, 2px offset |
| Near-white hairline as a **component boundary** | `#e0e0e0` on white = **1.32:1** | Decorative dividers only; boundaries need ≥3:1 |
| Cornell **orange `#F8981D`** as fill/icon/boundary on light | **2.21:1** | `#D47500` (3.31). Text on the orange must be `#222222` (7.20) |
| Cornell **green `#6EB43F`** as a mark on light | **2.54:1** | `#4B7B2B` (5.04) or `#578E32` (3.95) |
| **White text on Cornell orange** | **2.21:1** | `#222222` on it |
| `#008800` as a "good" status | 4.64 on white but **4.34 on `#F7F7F7`** | `#4B7B2B` (5.04 / 4.70) |

---

## Palette quick reference

**Primary ~90%** — carnelian `#B31B1B` · dark gray `#222222` · white `#FFFFFF`
(working split ≈ 55% white / 20% carnelian / 15% dark gray). Carnelian is *"the first color people
see"*, and the *only* color in limited-color media.

**Secondary ~7%** — light gray `#F7F7F7` · warm gray `#A2998B` **(black text only)** · sea gray
`#9FAD9F` **(black text only)**

**Accent ~3%** — blue `#006699` · green `#4B7B2B` text / `#578E32` large / ~~`#6EB43F`~~ fails on
light · orange `#D47500` large-or-graphic / ~~`#F8981D`~~ fails on light · secondary red `#DF1E12`
text / `#EF4035` graphic · navy `#073949`

**Status** (reserved — not available for identity or decoration): good `#4B7B2B` · warning `#D47500`
· critical `#DF1E12`. Always icon + word.

**Carnelian encodes nothing** — not data, not status, never inside a plot area. It measures
1.15–1.40:1 against every status color, so a status chip beside carnelian chrome stops reading as an
alarm.

**Type** — Freight Sans Pro (interface), Freight Text Pro (serif), Palatino (primary serif, on the
logo). All licensed/third-party, so **ship a system fallback**. Cornell publishes no weights, scale,
or fallback stack — decide once and document.

---

## Charts

Only two identity-safe series exist once status hues are reserved: **blue `#006699`** and **navy
`#073949`**, plus **dark gray `#222222`** for de-emphasis and "Other".

Contrast *between* those marks is 1.99 / 2.55 / 1.28 — all under 3:1, and unfixable within the
published palette. So **redundancy is mandatory**: legend, direct labels on every series, a table
view, and a 2px surface gap between touching fills. Remove any one and the chart fails 1.4.11.

**Prefer emphasis** — one series in blue, the rest in `#222222`. Marks go on white or `#F7F7F7` only;
blue is 2.55:1 on the dark band.

Never: dual-axis plots, a value ramp on nominal categories, recolor-on-filter, carnelian as data, or a
number on every point.

---

## Delivery

CSP with **no `unsafe-inline`, no `unsafe-eval`**. No inline `<script>` or `<style>`, no runtime
CSS-in-JS that injects a style element, no inline `style="…"` carrying color. Declare the palette once
as custom properties and reference roles, not hexes.

**Verify against a production build** — a dev server injects inline styles and a hot-reload bootstrap,
so it never exercises the real policy. HTML served straight from compute must send the CSP header from
the handler; a page with no CSP is non-conformant even when nothing inline is present.

Webfonts are third-party: self-host the `woff2`, or use the Adobe Fonts **CSS link** — never the JS
loader, which injects an inline script.

**Do not add the legacy Cornell emergency-banner script** — decommissioned 2021-03-31 and *"should be
removed"* where it survives.
