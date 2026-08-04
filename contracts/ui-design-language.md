# Contract — Cornell UI design language

**Applies to**: any application that renders something a human reads — a web page, a chat surface, a
dashboard, an emailed report, a generated document. Framework-agnostic and
implementation-agnostic by design: it constrains the output, not the toolchain.

**Source of truth**: **[brand.cornell.edu](https://brand.cornell.edu)**. Every brand rule below is
quoted or derived from a page listed in §12, and each section cites the page it comes from. **Where
this file and brand.cornell.edu disagree, brand.cornell.edu is right and this file is a bug** — fix
it here and note the date.

**Enforcement**: [`.claude/skills/cornell-ui-compliance/`](../.claude/skills/cornell-ui-compliance/SKILL.md).
§2 and §3 have **no exemption path** — a violation is corrected before the work proceeds, and the
correction is re-measured.

---

## 0. Precedence — what wins when sources disagree

| # | Source | Status |
|---|---|---|
| **1** | **Accessibility law and Cornell Policy 5.12** | **Non-negotiable. Never waived, by anyone.** §2 |
| **2** | **Cornell brand guidelines** — brand.cornell.edu | **Non-negotiable for marks, color, and type.** §3–§6 |
| **3** | A local implementation, theme, or component library | Binding on its own project *except* where 1 or 2 overrides it |

This ordering is load-bearing rather than decorative: **the three genuinely conflict**, and §2.4 and
§4.3 record every conflict found with the measurement that settles it. **An inaccessible
implementation is wrong even when it is the house style, and even when its colors are on-brand.**

### Scope gating

| Section | Binds when |
|---|---|
| §2 accessibility | **always**, no exceptions |
| §3 Cornell marks | **always when a Cornell mark is present**; presence itself is required on public-facing UIs |
| §4 color · §5 type · §6 imagery · §7 layout · §8 delivery | **always**, any UI |
| §9 data visualization | **only if** the UI plots data |
| §10 conformance checklist | **always** — the reviewable artifact |

### Declaring conformance

A project with a UI states its conformance in its own README, and records any **§4-and-below**
deviation in its own `docs/`.

**Deviation is declarable below §3. It is not declarable for §2 or §3.** A project may document that
it uses a different card treatment. It may not document that it fails contrast, or that it invented a
logo.

---

## 1. Non-negotiable, restated plainly

Two rule sets cannot be waived — not by a builder, not by a reviewer, not by an agent, and not by
whoever is asking loudest:

- **Accessibility (§2)** is a legal obligation. Cornell **Policy 5.12** requires it; the ADA and
  Section 504/508 sit behind it.
- **Cornell marks (§3)** are trademarks. **Policy 4.10** makes permission mandatory, and
  brand.cornell.edu states the alteration rules in the imperative.

If someone insists on a violation, the response is to say plainly that these are legal and trademark
obligations rather than preferences, offer the nearest compliant alternative, and route anything
genuinely undocumented to `brand@cornell.edu` (marks) or Cornell's accessibility office. **Never
comply and annotate.**

---

## 2. Accessibility — non-negotiable

### The standard

**WCAG 2.2 Level AA.**

Cornell **Policy 5.12 "Web Accessibility Standards"** requires new, newly added, or redesigned web
content and applications to meet *"the most recently published Web Content Accessibility Guidelines
(WCAG)"* — a moving reference, currently **WCAG 2.2**. Conforming to 2.2 AA therefore satisfies
Policy 5.12 as written, and also satisfies the older versions named elsewhere: brand.cornell.edu's
colors page cites the 2.0 AA numbers, and the DOJ's 2024 ADA Title II rule names 2.1 AA. **2.2 AA is
a superset of both.**

Policy 5.12 allows exceptions only where compliance would cause a *"fundamental alteration"* or
*"undue financial and administrative burdens"*, and even then *"equally effective alternative means
of access must be provided."* **A blueprint UI is new content being authored from scratch — neither
exception applies to choosing an accessible color or writing a visible focus ring.** Do not treat
that clause as a waiver.

### Thresholds

| Criterion | Level | Requirement |
|---|---|---|
| **1.4.1** Use of Color | A | Color is never the only means of conveying information |
| **1.4.3** Contrast (Minimum) | AA | **4.5:1** text · **3:1** large text |
| **1.4.11** Non-text Contrast | AA | **3:1** for UI components, component boundaries, focus indicators, and graphics required to understand content |
| **1.4.10** Reflow | AA | Usable at 320px equivalent, no two-dimensional scrolling |
| **1.4.12** Text Spacing | AA | Survives increased line-, letter-, word-spacing |
| **1.4.13** Content on Hover or Focus | AA | Tooltips/popovers **dismissable**, **hoverable**, **persistent** |
| **2.4.7** Focus Visible | AA | Every interactive element shows focus |
| **2.4.11** Focus Not Obscured | AA | Sticky chrome must not cover the focused element |
| **2.5.8** Target Size (Minimum) | AA | **24 × 24 CSS px** minimum per interactive target |
| **2.3.3** Animation from Interactions | enforced here | `prefers-reduced-motion` honoured |

**"Large text" is over 24px, or over 19px bold.** brand.cornell.edu's colors page states *"over 24
pixels — or 19 pixels if bold"*; WCAG says 24px / 18.66px bold. **19px is stricter, so 19px is the
rule.**

### How contrast is measured

WCAG contrast ratio only: `(L1 + 0.05) / (L2 + 0.05)` on relative luminance. **Never judged by eye.**
Every ratio in this document was computed; re-compute rather than trust.

```js
const chan = c => c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4);
const rgb  = h => { h = h.replace('#','').toLowerCase();
  if (h.length === 3) h = h.split('').map(c=>c+c).join('');
  return [0,2,4].map(i => parseInt(h.slice(i,i+2),16)/255); };
const lum  = h => { const [r,g,b] = rgb(h).map(chan); return 0.2126*r + 0.7152*g + 0.0722*b; };
const cr   = (a,b) => { const [hi,lo] = [lum(a),lum(b)].sort((x,y)=>y-x); return (hi+0.05)/(lo+0.05); };
```

**One limitation that changes what you must do:** WCAG contrast is a *luminance* ratio. It does not
test hue separation and will not flag two colors that collapse together for a colorblind reader. That
is why 1.4.1's redundancy rules are enforced independently, not as belt-and-braces.

### 2.4 Failure modes to check for — each one measured

These are the recurring ways a Cornell-palette UI fails AA. All values computed against the §4
surfaces.

| Failure mode | Measured | Required instead |
|---|---|---|
| **One global focus-ring color, applied everywhere.** The single most common failure: a mid-tone blue ring that passes on white is invisible on a carnelian masthead or a dark footer | a `#2e5690`-class ring measures **1.08:1 on carnelian**, 2.36:1 on `#1a1a1a`, 1.71:1 on `#333333` — while passing 7.37:1 on white | **Surface-aware ring.** White on carnelian (6.80) and dark (15.91); black (21.00) or carnelian (6.80) on white and `#F7F7F7`. §4.4 has the per-surface table |
| A near-white hairline used as a **component boundary** | `#e0e0e0` on white = **1.32:1** | Decorative dividers only. An input border or control outline needs **≥3:1** |
| Cornell **orange `#F8981D`** as a fill, icon, or boundary on a light surface | **2.21:1** on white | `#D47500` (3.31:1). See §4.3 — this is a brand-palette color that fails AA |
| Cornell **green `#6EB43F`** as a mark on a light surface | **2.54:1** on white | `#4B7B2B` (5.04:1) or `#578E32` (3.95:1) |
| **White text on Cornell orange** | **2.21:1** | Dark gray `#222222` on it (7.20:1) |
| **White-fill mark on a light surface** | **1.00:1** on white, 1.07:1 on `#F7F7F7` | The black or carnelian variant. §3.6 |

---

## 3. Cornell marks — non-negotiable

**Source: [brand.cornell.edu/logos](https://brand.cornell.edu/logos),
[/logos/academic](https://brand.cornell.edu/logos/academic),
[/logos/non-academic](https://brand.cornell.edu/logos/non-academic),
[/merchandising](https://brand.cornell.edu/merchandising), Policy 4.10.**

The logo is *"a trademark of Cornell University"* and the name *"Cornell University"* is registered
(/merchandising). Policy 4.10 states the university *"allows the use of its name, and its logos,
trademarks, insignias, and other indicia **only with permission**."*

### 3.1 Lockups are for colleges and schools only

**This is the rule most often broken, and it is unambiguous.** From /logos/academic:

> *"This lockup configuration is used exclusively to represent **colleges and schools**."*
>
> *"This lockup is **not** used for anything other than a college or school."*

And from /logos/non-academic, for everything else:

> a non-academic logo, wordmark, or identifier *"may share primacy with, and proximity to, the seal
> logo but **may not use a lockup configuration**."*

So:

| Unit type | Lockup? |
|---|---|
| A **college or school** | **Yes** — the academic lockup represents it |
| A **department or unit inside** a college or school | Only by being *"incorporated into their school's lockup"*, and only where it is *"part of the academic mission"*. It does not get a lockup of its own |
| A **program, center, or institute** | **Not automatic.** *"For programs, centers and institutes, please contact us for a consultation."* |
| Any **non-academic** office, service, or team | **No lockup, ever.** It may sit beside the seal logo with equal prominence — that is not a lockup |

**Therefore: a department that is not a college or school does not get a lockup, and this platform
will not compose one.** Not in an image, not in SVG, and not by setting the unit's name in type
beside the mark to imitate one — that arrangement *is* the lockup configuration the rule forbids.

**A non-eligible unit identifies itself in ordinary text**, set per §5 and named per the nomenclature
rules ([/messaging/nomenclature](https://brand.cornell.edu/messaging/nomenclature/)), positioned as
its own element rather than locked to the mark.

### 3.2 A custom unit logo is the builder's to supply

If a project wants a unit-specific mark, **the builder provides the approved asset.** The platform
does not generate, derive, or synthesize one, because doing so would violate both the alteration
prohibition (§3.7) and Policy 4.10's permission requirement.

Routes to a legitimate asset, per brand.cornell.edu:

- *"For logos and lockups that pertain to your college, school, or department, please contact your
  **communications director**."* (/resources/downloads)
- A consultation request or `brand@cornell.edu`, which is also the stated route for programs,
  centers, and institutes.
- Use of a name or logo is requested through the brand forms; Policy 4.10 governs the permission.

**Until an approved asset exists, the UI ships with the university mark and the unit's name as text.**
That is a complete, compliant outcome — not a placeholder.

### 3.3 Presence

**Required on every public-facing UI.** Internal/admin-only surfaces and machine-facing output are
exempt from *presence* — but any mark that **is** present obeys every rule here regardless of
audience.

### 3.4 Size — exact, not approximate

From /logos:

| Variant | Rule |
|---|---|
| Simple Logo (web) | **73–120 px** |
| Simple Seal (web) | **73–120 px**, and *"the dimension must not exceed 120 pixels"* |
| Reduced Logo (web) | ***must be* 45 px tall** — a fixed value, not a range |
| Bold Logo / Bold Seal (print) | greater than **3/4 inch** |
| Reduced Wordmark (print) | below **3/4 inch** |

/logos/academic adds the lockup's own floor and its fallback: *"The seal is at least 73px square"*,
and below that *"the design switches to the 45px logo lockup."*

The mark *"should always be reproduced at a size that is legible."* **A responsive layout must not
scale the mark outside its band at any breakpoint** — fluid CSS is the usual way this breaks. Both
pages describe a mark that *"responds"* to its container, so switching variant by breakpoint is the
intended mechanism; scaling one variant past its limits is not.

### 3.5 Clear space and internal spacing

From /logos:

> *"Text, headlines, photographs, or illustrations should never be closer to the logo than **1/4 the
> diameter of the seal**."*

At the 120px ceiling that is **30px**; at 73px, **~18px**; at the 45px reduced logo, **~11px**. Use
padding — a collapsible margin is not an exclusion zone.

For the lockup itself (/logos/academic): *"Hairline and seal logo are equal height"*, and *"The space
between the first letter and seal logo is 1/2 width of the seal."*

### 3.6 Color, and choosing a variant by background

**Marks are restricted to carnelian, black, or white.** /logos/academic: *"Only black, red, or white
are used for the Cornell seal."* /merchandising gives the print equivalents: Cornell red **PMS 187**,
white, or black.

Background rules are **contrast-governed, not an allowlist** (/logos):

> *"The logo may be printed on any background that provides sufficient contrast for the logo to
> appear clearly and legibly."*

That composes with §2's 1.4.11 threshold instead of competing with it, giving one operative rule:

> **Pick the variant whose fill clears 3:1 against the surface behind it.**

| Surface | Compliant variant | Prohibited |
|---|---|---|
| White `#FFFFFF` | **black** (21.00) or **carnelian** (6.80) | white fill — **1.00:1** |
| Light gray `#F7F7F7` | **black** (19.60) or **carnelian** (6.35) | white fill — **1.07:1** |
| Carnelian `#B31B1B` | **white** (6.80) | black is 3.09 — large-only, avoid |
| Dark gray `#222222` | **white** (15.91) | carnelian — **2.34:1** |
| Dark Warm gray `#A2998B` | **black** (7.47) | white — **2.81:1** |
| Sea gray `#9FAD9F` | **black** (8.95) | white — **2.35:1** |
| A photograph | whichever variant clears 3:1 against the **darkest and lightest** pixels behind it | any variant over a busy mid-tone region |

**A white-fill asset is a dark-surface asset.** On a predominantly white UI there are exactly two
compliant routes: place the mark in a carnelian or dark band, or use the black/carnelian variant.

### 3.7 Prohibited, absolutely

- **"Do not redraw, reconstruct, or modify the logo in any way"** — the mark *"cannot be altered"*
  (/merchandising).
- **"Do not attempt to create art for the Cornell logo, seal or wordmark for any application"**
  (/logos). This includes reconstructing it in CSS, hand-written SVG, or an icon font.
- **"No watermarking, screening, or cropping of seal in any designs"** (/logos).
- Any fill outside carnelian / black / white (§3.6).
- Any variant outside its size band (§3.4).
- Anything inside the clear-space zone (§3.5).
- A lockup for any unit that is not a college or school (§3.1).
- More than one mark per view: *"Cornell logo appears only once on a homepage or communications
  piece"* (/logos).

**Not addressed upstream** — rotation, distortion/stretching, drop shadows, outlines, and locally
assembled co-brand lockups. Given *"cannot be altered"* and *"do not attempt to create art"*, the
conservative reading applies and all are **prohibited here**: aspect ratio locked, no transforms, no
effects. **Anything not explicitly permitted requires brand consultation, not local judgment.**

### 3.8 Trademark symbols

From /merchandising: the logo carries **™**; the logotype used by itself carries **®**. Symbols are
omitted where size or reproduction would render them *"illegible"*, and are not required on banners,
flags, or signs. In a web UI at 45–120px, the symbol is frequently illegible — omit it rather than
render it as a smudge, and never redraw the mark to add one.

---

## 4. Color

**Source: [brand.cornell.edu/design-center/colors](https://brand.cornell.edu/design-center/colors).**
Proportions are Cornell's: **~90% primary, ~7% secondary, ~3% accent.**

### 4.1 Primary — ~90%

| Color | Hex | Vetted pairings |
|---|---|---|
| Carnelian | `#B31B1B` | White, Light gray |
| Dark gray | `#222222` | White, Light gray |
| White | `#FFFFFF` | Carnelian, Dark gray |

**The "first and only" rule:** carnelian is *"the **first** color people see"* in multi-color media
and the *"**only** color"* in limited-color media. It leads the composition — and per §9 it never
encodes data.

A workable decomposition of the 90%: **~55% white, ~20% carnelian, ~15% dark gray.**

### 4.2 Secondary — ~7%

*"Neutral hues"* that support rather than drive a layout.

| Color | Hex | Text on it |
|---|---|---|
| Light gray | `#F7F7F7` | Carnelian, Dark gray |
| Dark Warm gray | `#A2998B` | **Black only** (7.47:1). White = 2.81:1 — fails |
| Sea gray | `#9FAD9F` | **Black only** (8.95:1). White = 2.35:1 — fails |

### 4.3 Accent — ~3%, with the AA measurement Cornell does not publish

Cornell publishes per-use variants because the base accents are not all text-safe. **The last column
is measured here and narrows the set further.**

| Accent | Base (graphics) | Text-safe | Large-text only | On white — **1.4.11 verdict** |
|---|---|---|---|---|
| Blue / link | `#006699` | `#006699` | — | **6.25 ✓** |
| Green | `#6EB43F` | `#4B7B2B` | `#578E32` | base **2.54 ✗** · 5.04 ✓ · 3.95 ✓ |
| Orange | `#F8981D` | — | `#D47500` | base **2.21 ✗** · 3.31 ✓ |
| Secondary Red | `#EF4035` | `#DF1E12` | — | 3.85 ✓ · 4.85 ✓ |
| Navy | `#073949` | `#073949` | — | **12.42 ✓** |

> **Accessibility override.** Cornell labels `#6EB43F` and `#F8981D` *"graphics only"* — that means
> *do not set text in them*. **It does not mean they are safe as graphics.** Both fail 1.4.11 on a
> light surface (2.54:1, 2.21:1), so **neither may be a mark, fill, icon, or boundary there.** Use
> `#578E32`/`#4B7B2B` and `#D47500`. This is §0 precedence in action: the palette is on-brand and the
> usage would be inaccessible, so accessibility wins.

Accents *"should not be used as full-color bleeds"* and must never become a unit's primary color.

### 4.4 Focus indicators, per surface (1.4.11 ≥3:1)

| Surface | Usable ring colors |
|---|---|
| `#FFFFFF` | black 21.00 · carnelian 6.80 |
| `#F7F7F7` | black 19.60 · carnelian 6.35 |
| `#A2998B` | **black 7.47 only** |
| `#9FAD9F` | **black 8.95 only** |
| `#222222` | white 15.91 |
| `#B31B1B` | white 6.80 |

On the two mid-tone secondaries, **black is the only compliant ring.**

### 4.5 Status — reserved

Mapped to Cornell accents that clear 4.5:1 as text on both light surfaces:

| Role | Hex | on `#FFFFFF` | on `#F7F7F7` |
|---|---|---|---|
| good | `#4B7B2B` | 5.04 ✓ | 4.70 ✓ |
| warning | `#D47500` | 3.31 — large text or graphic only | 3.09 — same |
| critical | `#DF1E12` | 4.85 ✓ | 4.52 ✓ |

`#008800` is a tempting "good" and **fails**: 4.64 on white but **4.34 on `#F7F7F7`**.

**Always icon + word, never color alone** (1.4.1). **Status hues are reserved** — the green, orange,
and red families are not available for identity, category, or decoration.

**Carnelian is never a status color.** It measures 1.15–1.40:1 against every status color, so a status
chip on or beside carnelian chrome is unreadable as an alarm. Status lives on the white or light-gray
plane.

---

## 5. Typography

**Source: [brand.cornell.edu/design-center/typography](https://brand.cornell.edu/design-center/typography).**

| Typeface | Role, as stated |
|---|---|
| **Palatino** | *"the primary serif typeface for the university"*; *"appears on the Cornell logo"*. Licensed (purchase) |
| **Freight Text Pro** | *"a more contemporary serif"*; *"appears on web properties, such as cornell.edu"*. Adobe Fonts |
| **Freight Sans Pro** | sans serif, *"comes in a variety of weights and styles and is easily legible on screen"*. Adobe Fonts |

For a web UI, that makes **Freight Sans Pro** the interface face and **Freight Text Pro** the serif —
both Adobe Fonts, so **neither is a self-contained asset**; see §8.

**Ship a real system fallback** (`system-ui, -apple-system, "Segoe UI", sans-serif`). If the webfont
is blocked or slow, the UI must still be readable and still meet §2.

Cornell does **not** publish weights, a type scale, line-height, or fallback stacks (§11). Those are
local decisions — make them once, write them down, and keep them consistent.

Two rules that are not optional:

- **Large text is >24px, or >19px bold** (§2). A 15px caption gets no relief.
- **Numerals that are read as data** use lining figures; add tabular figures only where numbers align
  vertically. Large standalone values stay proportional.

---

## 6. Imagery

**Source: [brand.cornell.edu/design-center/photography](https://brand.cornell.edu/design-center/photography).**

- *"Professional photography should be used as often as possible"*, *"particularly important for
  external communications."*
- *"All photographs should be printed at 300 dpi at the actual size."*
- **The one explicit prohibition:** *"Do not increase the size of digital images as this can cause
  the image to be distorted."*
- Approved source: the Cornell Photos library at `photo.cornell.edu`.

**Accessibility obligations that attach to imagery**, since brand.cornell.edu does not state them:

- Every image needs a text alternative; decorative images are marked as such.
- **Text over a photograph must clear 4.5:1 against the actual pixels behind it** — not against an
  average. Use a scrim, a solid panel, or a crop that guarantees it.
- A mark over a photograph follows §3.6: the chosen variant clears 3:1 against the darkest *and*
  lightest region it covers.
- Third-party imagery needs permissions
  ([/design-center/copyright-licensing](https://brand.cornell.edu/design-center/copyright-licensing));
  do not assume anything found online is usable.

---

## 7. Layout and interaction

Cornell publishes no grid, breakpoint, or spacing system (§11), so these are the accessibility
obligations plus the conventions that keep a UI predictable.

- **One control row above everything it scopes.** Filters and scope selectors sit above the content,
  never inside individual cards — two cards must not be able to disagree about what they show. If
  sticky, satisfy **2.4.11**.
- **1.4.10 Reflow**: usable at 320px equivalent; **1.4.12 Text Spacing**: survives increased spacing,
  so do not pin the height of legends, labels, or chips.
- Size containers to include their labels — a height that fits content but not its caption or axis
  band produces a nested scrollbar.
- **Interactive targets ≥24×24 CSS px** (2.5.8).
- **Tooltips enhance, never gate.** Every value reachable without hover; keyboard focus shows what
  hover shows; dismissable, hoverable, persistent (1.4.13).
- Honour `prefers-reduced-motion`.
- **Do not add the legacy Cornell emergency banner script.** It was
  [decommissioned](https://brand.cornell.edu/messaging/emergency-banner/) on 2021-03-31 and *"should
  be removed"* where it survives.

---

## 8. Delivery and Content-Security-Policy

**A UI serves a CSP with no `unsafe-inline` and no `unsafe-eval`.**

- **No inline `<script>`**, including build-injected bootstrap
- **No inline `<style>`**, and no runtime CSS-in-JS that injects one
- **No `eval` / `new Function`**
- **No inline `style="…"` carrying color** — use custom properties and classes
- Declare the palette once as custom properties and reference roles, never raw hexes, so a surface
  change is a one-place edit

**Bundled single-page apps**: emit CSS as hashed external files. **The dev server does not run under
the production CSP** — it injects inline styles and a hot-reload bootstrap. Verify against a
production build, or a violation ships unseen. Bundlers that emit an inline module-preload polyfill
must have it disabled.

**HTML served directly by compute** (Lambda, container): the simplest model and the most likely to
violate the policy, because a self-contained page is the natural way to write it. **Send the CSP
header from the handler** — a page with no CSP is non-conformant even when nothing inline is present.
Move CSS and JS to separate routes. A genuinely single-file page takes a **declared exemption for §8
only** — never for §2 or §3.

**The brand webfonts are third-party.** Either self-host the `woff2` files (licence permitting) and
keep `font-src 'self'`, or use the Adobe Fonts **CSS `<link>`** — never the JS loader, which injects
an inline script. The link route needs the Adobe Fonts origins in `style-src` and `font-src`.

---

## 9. Data visualization

**Binds only if the UI plots data.** Cornell publishes no chart guidance (§11), so this section
derives from §4's palette under §2's thresholds.

### Series palette

Once the green, orange, and red families are reserved for status (§4.5), and the base green and
orange are excluded for failing 1.4.11 (§4.3), Cornell's palette leaves **two identity-safe accents**:

| Slot | Color | Hex | on `#FFFFFF` | on `#F7F7F7` |
|---|---|---|---|---|
| 1 | Blue | `#006699` | 6.25 ✓ | 5.83 ✓ |
| 2 | Navy | `#073949` | 12.42 ✓ | 11.60 ✓ |
| de-emphasis / "Other" | Dark gray | `#222222` | 15.91 ✓ | 14.85 ✓ |

**Two identity slots plus a de-emphasis gray is the honest ceiling** — and it is consistent with a 3%
accent budget, which cannot fund eight hues. Beyond two series: rank by the measure, keep the top
two, fold the rest into "Other", and put the full breakdown in a table.

**Marks live on white or `#F7F7F7`.** Blue is 2.55:1 on `#222222` and fails there.

### Redundancy is mandatory

Contrast **between** the marks: blue↔navy **1.99**, blue↔dark gray **2.55**, navy↔dark gray **1.28** —
all below 3:1, and **not fixable by substitution: no two identity-safe Cornell hues reach 3:1 between
themselves.**

1.4.11 binds on *"graphics required to understand the content."* These charts make color redundant by
construction, so each item is **required, not an enhancement**:

- A legend whenever two or more series are present
- **Direct labels on every series**
- **A table view of every chart** — every value reachable as text
- **A 2px surface-colored gap between touching fills**

Remove any one and the chart fails AA.

### Emphasis is the preferred form

With two identity slots, **emphasis** — one series in blue, the rest in `#222222` — is both the
clearer chart and the stronger compliance position. Prefer it whenever the story is about one series.

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

Separate marks with a **2px surface gap** and a **2px surface ring** on overlapping markers, never a
stroke drawn around a mark.

**Text never wears the series color.** Labels, values, legend, and axis text use ink colors; identity
comes from the swatch beside the text. A label inside a fill picks black or white by the fill's
luminance and must itself clear 4.5:1.

### Anti-patterns

1. **Dual-axis charts.** Two y-scales invent a correlation the data does not contain. Two charts,
   small multiples, or index to a common base on one axis.
2. **A value ramp on nominal categories** — double-encodes what bar length already shows.
3. **Recolor-on-filter.** Bind hue to entity with a stable map computed once.
4. **Carnelian as a data color** (§3, §4.1).
5. **A number on every point.** Label the endpoint, the extreme, or the series that matters.
6. **A one-bar bar chart or two-slice pie.** That is a single number — show it as one.

---

## 10. Conformance checklist

**Accessibility — §2. No exemptions.**
- [ ] Every text/background pair computed: ≥4.5:1 normal, ≥3:1 large (>24px / >19px bold)
- [ ] Every component boundary, focus ring, icon, and meaningful graphic ≥3:1
- [ ] Focus rings should defer to user agent defualt (such as the browser) as much as possible (don't add styling for buttons or links that naturally gain focus)
- [ ] Focus ring is **surface-aware** and visible on carnelian and dark surfaces
- [ ] Nothing conveyed by color alone; status is icon + word
- [ ] Interactive targets ≥24×24 CSS px
- [ ] Tooltips dismissable, hoverable, persistent
- [ ] Usable at 320px; survives increased text spacing; `prefers-reduced-motion` honoured
- [ ] `#6EB43F` and `#F8981D` appear nowhere as marks/fills/boundaries on light surfaces
- [ ] Text over imagery measured against actual pixels, not an average

**Cornell marks — §3. No exemptions.**
- [ ] Official asset used — **not** redrawn, reconstructed, or CSS/SVG-recreated
- [ ] **No lockup unless the unit is a college or school.** A non-eligible unit's name is plain text, not locked to the mark
- [ ] A custom unit mark, if any, was **supplied by the builder** as an approved asset — never generated here
- [ ] Size in band: simple 73–120px · seal ≤120px · reduced **exactly 45px** — **at every breakpoint**
- [ ] Clear space ≥ 1/4 the seal's diameter, as padding
- [ ] Fill is carnelian, black, or white — nothing else
- [ ] Variant's fill clears **3:1** against its actual background (§3.6)
- [ ] **Exactly one** Cornell mark per view
- [ ] No watermark, screen, crop, rotation, distortion, shadow, outline, or local lockup
- [ ] ™/® omitted rather than rendered illegibly

**Color, type, imagery — §4–§6**
- [ ] ~90% primary / ~7% secondary / ~3% accent, roughly respected; carnelian reads first
- [ ] Carnelian encodes nothing
- [ ] Status families not reused for identity or decoration
- [ ] Cornell typefaces with a working system fallback; no hardcoded hex in a component
- [ ] Images not upscaled; third-party imagery cleared

**Delivery — §8**
- [ ] CSP sent with no `unsafe-inline`/`unsafe-eval`, verified against a **production** build
- [ ] No legacy emergency-banner script

**Charts — §9, if applicable**
- [ ] ≤2 identity series + "Other"; marks on light surfaces only
- [ ] Legend, direct labels, table view, 2px gaps all present

---

## 11. What brand.cornell.edu does not specify

Recorded so local decisions are visible as decisions rather than mistaken for brand rules. For each,
brand.cornell.edu is silent and the choice is the project's — but §2 still binds.

| Not published | Consequence |
|---|---|
| Type weights, type scale, line-height, fallback stacks | Choose once, document, keep consistent (§5) |
| Grid, breakpoints, spacing scale | Local; must satisfy 1.4.10 and 1.4.12 (§7) |
| Any chart or data-visualization guidance | §9 derives it from the palette under AA |
| Rotation, distortion, shadows, outlines on the mark | Treated as **prohibited** under *"cannot be altered"* (§3.7) |
| Whether a unit may commission its own logo, and the criteria | Route to a communications director or `brand@cornell.edu` (§3.2) |
| Contrast values for the accent palette | Measured here (§4.3) — and two base accents fail |
| Photo style principles, crops, text-over-image contrast | §6 supplies the accessibility half only |
| Dark-mode or dark-theme guidance | None exists. A dark theme must re-derive accents against its surface and record the measurements |
| Icon or illustration system | Local |

**Asset download note:** logo files sit behind an authenticated path
([/resources/downloads](https://brand.cornell.edu/resources/downloads/)) — `cornell_logo_simple_web.zip`,
`cornell_seal_simple_web.zip`, `cornell-reduced.zip`, `cornell-reduced-wordmark.zip`, plus the print
`bold_*` archives. Obtain them from there; do not extract a mark from a screenshot or another site.

---

## 12. Cross-reference index — every source consulted

Retrieved **2026-08-04**. brand.cornell.edu is the source of truth; this file is a derivative.

| Page | URL | What it governs here |
|---|---|---|
| Logos | [brand.cornell.edu/logos](https://brand.cornell.edu/logos) | Size bands, clear space, background/contrast rule, seal prohibitions, one-mark-per-piece, "do not create art" | 
| Logos — Academic | [/logos/academic](https://brand.cornell.edu/logos/academic) | **Lockups are colleges and schools only**; sub-unit incorporation; programs/centers/institutes need consultation; seal color limits; lockup spacing and the 73px→45px switch |
| Logos — Non-academic | [/logos/non-academic](https://brand.cornell.edu/logos/non-academic) | **Non-academic identifiers may not use a lockup**; may sit beside the seal with equal primacy |
| Colors | [/design-center/colors](https://brand.cornell.edu/design-center/colors) | Full palette, 90/7/3 proportions, "first and only" red rule, per-use accent variants, AA thresholds and the 24px/19px-bold definition |
| Typography | [/design-center/typography](https://brand.cornell.edu/design-center/typography) | Palatino, Freight Text Pro, Freight Sans Pro and their stated roles |
| Photography | [/design-center/photography](https://brand.cornell.edu/design-center/photography) | Professional photography, 300 dpi, no upscaling, `photo.cornell.edu` |
| Copyright & Licensing | [/design-center/copyright-licensing](https://brand.cornell.edu/design-center/copyright-licensing) | Third-party media permissions (not Cornell marks) |
| Stationery | [/design-center/stationery](https://brand.cornell.edu/design-center/stationery) | Nothing generalizable — routes to Print Services |
| Merchandising | [/merchandising](https://brand.cornell.edu/merchandising) | **"Do not redraw, reconstruct, or modify the logo in any way"**; PMS 187 / white / black; ™ and ® usage; pre-production approval |
| Policies | [/policies](https://brand.cornell.edu/policies) | **Policy 4.10** name/logo permission; **Policy 5.12** web accessibility ("most recently published WCAG", exception clause); 4.16 social media; 5.6 domains |
| Nomenclature | [/messaging/nomenclature](https://brand.cornell.edu/messaging/nomenclature/) | Formal/standard/shorthand naming tiers; institution-before-location; approved and prohibited unit names |
| Downloads | [/resources/downloads](https://brand.cornell.edu/resources/downloads/) | Asset filenames and size notes; **"contact your communications director"** for unit marks |
| Emergency banner | [/messaging/emergency-banner](https://brand.cornell.edu/messaging/emergency-banner/) | Decommissioned 2021-03-31; the script should be removed |
| Design Center index | [/design-center](https://brand.cornell.edu/design-center) | Subpage enumeration; confirms no web-standards or iconography section exists |

**Not consulted**, as they bear on no UI rule: `/design-center/video`, `/design-center/music`,
`/messaging` subpages other than nomenclature and the emergency banner, `/resources` terminology.

**Brand contacts:** `brand@cornell.edu` · consultation, use-of-name, merchandise-approval and
misuse-reporting forms are linked from brand.cornell.edu. Accessibility questions route to Cornell's
accessibility office. Copyright questions: `copyright@cornell.edu`.

---

## 13. Changing this contract

1. **Re-read brand.cornell.edu first.** It moves; this file does not move itself. If the two
   disagree, that page is right.
2. New color values come from the published palette. **Do not invent hexes.**
3. **Compute the WCAG ratio against every surface the color appears on.** Never eyeball.
4. Apply the right threshold: 4.5:1 text, 3:1 large text and meaningful non-text.
5. For a mark, also check it against the fills beside it. If no pair reaches 3:1 — the normal case
   here — the §9 redundancy items are mandatory.
6. **Record every new ratio in the tables above**, so the next reader inherits measurements rather
   than assertions.
7. A project-specific deviation belongs in that project's `docs/`, and only below §3.
8. Update §12 with the retrieval date whenever a rule is re-checked upstream.

**The limitation worth repeating: WCAG contrast is luminance-only.** Two colors can pass every ratio
here and still be indistinguishable to a colorblind reader. When adding a hue, check perceptual
separation too, and keep the redundant coding regardless.
