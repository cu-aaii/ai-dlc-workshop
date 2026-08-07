# Frontend Components — C-06 Web UI

**Phase**: CONSTRUCTION → Functional Design (artifact 4 of 4)
**Date**: 2026-08-03
**Mandatory for this unit.** U-01 had no UI, so this artifact appears for the first time here.

**Binding contract**: `contracts/ui-design-language.md` — §2 accessibility (WCAG 2.2 AA) and §3 Cornell
logo have **no exemption path**. Deviation is declarable only at §5 and below. A dashboard addendum
exists at `blueprints/dashboard/docs/design-language.md`, written by another team.

---

## Component hierarchy

```
App                                  view state, one fetch per view (Q4 = A)
├── Masthead                         Cornell logo (§3 — required, not optional)
├── StatusStrip                      collected_at · freshness · the three counts
├── ViewTabs                         inventory | grouping | tag-gaps | status
└── <the active view>
    ├── InventoryView                table of every resource + copy-URL affordance
    ├── GroupingView                 tag-key selector + grouped table
    ├── TagGapView                   incomplete resources and which tags they lack
    └── StatusView                   freshness, counts, skip reasons
        └── (all four wrap) StateBoundary   renders the six states
```

`StateBoundary` is the only component that decides *whether* to render data. Every view delegates to it,
so the six-state logic exists once. Four independent implementations of "is there data?" is precisely how
`no_data` and `ok`-with-zero-resources end up looking the same.

---

## Props and state

```ts
// App
type AppState = { view: ViewName }                  // no router (Q4 = A)

// Per view, via a shared hook
type ViewState<T> =
  | { kind: 'loading' }
  | { kind: 'ready';  envelope: Envelope<T> }
  | { kind: 'failed'; httpStatus: number }

type Envelope<T> = {
  status: 'ok' | 'stale' | 'no_data' | 'error'
  collected_at: string | null
  freshness: 'fresh' | 'stale' | 'invalid' | null
  counts: { resources: number; skipped: number; duplicates_removed: number; raw_returned: number }
  data: T
}
```

| Component | Props | Local state |
|---|---|---|
| `App` | — | `view: ViewName` |
| `Masthead` | — | none |
| `StatusStrip` | `envelope` | none |
| `ViewTabs` | `active`, `onSelect` | none |
| `InventoryView` | — | `ViewState<ResourceRow[]>` |
| `GroupingView` | — | `ViewState<GroupingPayload>`, `tagKey: RequiredTag` |
| `TagGapView` | — | `ViewState<TagGapPayload>` |
| `StatusView` | — | `ViewState<StatusPayload>` |
| `StateBoundary` | `state`, `children` | none |

**No global store, no context, no data-fetching library** (Q4 = A). Four read-only views, no shared
mutable state, no forms. A store would be infrastructure for a problem that does not exist, and each
dependency is surface Q11 = B decided not to scan.

**Explicitly rejected: SWR / React Query.** Client-side caching contradicts ER-03's `/api/*` no-cache
decision and would reintroduce two views disagreeing about freshness — the failure US-05 exists to
prevent. Recorded here so a future contributor adding "just a little caching" sees why not.

**`freshness` is never computed in the browser.** It arrives from the server (U-01's
`evaluate_freshness`). Two viewers must reach the same verdict.

---

## The six states, on screen

`StateBoundary` maps the API's outcome to what a person sees. **Rows 3 and 4 are why this component
exists** — they render identically under a naive implementation and mean opposite things.

| API outcome | Screen | Tone |
|---|---|---|
| 200 `ok`, resources > 0 | The data | normal |
| 200 `stale` | The data + a **prominent** staleness banner naming `collected_at` | warning |
| 200 `ok`, resources = 0 | "**No tagged resources found.** The collector ran successfully and found nothing carrying `cornell:*` tags." | informational |
| 200 `no_data` | "**No data collected yet.** The collector has not completed a successful run." | informational, visibly different from the row above |
| 503 `error` | "The dashboard cannot read its data right now." No internals. | error |
| Network failure / non-JSON | Same generic error, plus that the request itself failed | error |

The two informational rows differ in **wording, icon and heading** — not just in a count. "0 resources"
under both would be the bug.

Row 5 covers `UNREADABLE` *and* the inherited `INVALID` case (a future `collected_at`). The user is told
the same thing, because from their side both mean "the data cannot be trusted"; the *distinction* lives in
the logs and the alarm, not on screen.

---

## Grouping without colour — Q5 = A

The contract leaves **two** identity-safe accents (blue `#006699`, navy `#073949`) plus dark gray, because
green/orange/red are reserved for status. Grouping by `cornell:blueprint` in a shared account produces
five, ten, twenty groups. So:

> **Group identity is not encoded in colour at all.** Grouping views are sorted tables with a
> proportional bar per row, one accent for the bar, text labels for identity. Colour carries **status
> only** — fresh/stale/error, tagged/untagged.

**Why this rather than top-2-plus-Other:**

- It dissolves the conflict instead of rationing a palette that will always run out.
- §2 requires colour never be the sole carrier of meaning, so this is what accessibility wants anyway.
- Twenty categorical colours are unreadable even where a palette permits them.
- Collapsing the long tail into "Other" hides exactly what a *tag inventory* is for — the one-off
  resource nobody owns is what US-04 exists to surface.

Group ordering comes from U-01 (count desc, value asc, **missing group pinned last**) and the UI must not
re-sort. The missing group gets a distinct label — "(no `cornell:owner` tag)" — not a blank cell, and the
`TagGapView` is the actionable companion since the missing group sits last here.

**⚠️ This diverges from the addendum another team wrote**, which specifies a two-accent series with
"Other" for charts. It is *more* conservative than the contract requires, not a contract violation — but
that file is not ours to rewrite. Flagged for the user to relay; the authors should decide whether the
addendum changes or Q5 = A does.

---

## Accessibility — §2, non-waivable

| Requirement | How |
|---|---|
| Contrast ≥ 4.5:1 body, 3:1 large | Palette from `aisei-site` tokens; no custom colours |
| Colour never the sole carrier | Guaranteed by Q5 = A: identity is textual. Status uses icon **and** text alongside colour |
| Keyboard operable | Tabs are real `<button>`s in a `role="tablist"`; the table is native markup; no custom widgets |
| Focus visible | Never removed; token-defined focus ring |
| Semantic structure | One `<h1>`, `<table>` with `<th scope="col">`, `<caption>` per view |
| Live regions | The staleness banner and error states use `role="status"` / `role="alert"` so a screen reader is told when a view changes |
| Zoom to 200% | Fluid layout, no fixed pixel widths on containers |
| Reduced motion | No animation; nothing to suppress |

The three that are easiest to lose in implementation: **live regions** (a view swap that announces
nothing), **focus visibility** (removed by a reset), and **table semantics** (a `<div>` grid). Named for
review.

---

## CSP — no `unsafe-inline`, no `unsafe-eval`

`.claude/skills/cornell-ui-compliance/` blocks non-compliant UI output, and ER-04 sets a strict CSP.

**Concretely for Vite**: the production build emits an inline `<script>` for the **modulepreload
polyfill** by default. It must be disabled (`build.modulePreload.polyfill = false`) or hash-allowlisted.
Recorded as a setting because "keep the CSP strict" is not actionable and "disable the polyfill" is.

React does not need `unsafe-eval` in a production build. No third-party CDN scripts, so there is nothing
requiring SRI (SECURITY-14).

---

## API integration

| Component | Endpoint | Notes |
|---|---|---|
| `InventoryView` | `GET /api/inventory` | Also the copy-URL target (Q6 = A) |
| `GroupingView` | `GET /api/groups/{tag_key}` | `tag_key` from a four-option selector, never free text |
| `TagGapView` | `GET /api/tag-gaps` | |
| `StatusView` | `GET /api/status` | |
| `StatusStrip` | whichever view is active | Reads that view's envelope; **does not fetch** |

Same-origin `/api/*` (Application Design Q4), so no CORS, no credentials, no SigV4, no token (FR-4.5).

`StatusStrip` deliberately does not fetch. A fifth request for freshness could return a different snapshot
than the view beneath it, and two parts of one screen disagreeing is the US-05 failure in miniature.

**No deep-linking**, a consequence of Q4 = A: one URL for the app, so a specific view cannot be shared.
The copy-URL affordance therefore copies the **API** URL, which is what Q6 = A intends. Cheap mitigation
if it bites: a `?view=` parameter read on mount, needing no router.

---

## `data-testid` naming

`{component}-{element-role}`, stable across changes:

```
view-tabs-inventory          view-tabs-grouping        view-tabs-tag-gaps
status-strip-collected-at    status-strip-freshness    status-strip-skipped-count
inventory-table              inventory-copy-url-button
grouping-tag-key-select      grouping-table            grouping-missing-group-row
tag-gap-table                tag-gap-missing-tags
state-boundary-no-data       state-boundary-no-resources
state-boundary-stale-banner  state-boundary-error
```

`state-boundary-no-data` and `state-boundary-no-resources` are **separate ids on purpose**: it makes the
US-06 distinction assertable from an automated test, rather than resting on a human noticing two similar
screens.

---

## Out of scope for C-06

| Absent | Why |
|---|---|
| Login, user menu, profile | No identity system (FR-5.5) |
| Any mutation, form, or write | Read-only (FR-4.5) |
| A refresh button that re-collects | A read never causes a write (FR-2.1, US-07). A *re-fetch* button is fine; triggering collection is not. |
| Cost views | FR-8 deferred (US-D1/D2) |
| Client-side freshness computation | Server judgement only (US-05) |
| Client-side cache | Contradicts ER-03 |
| Charts beyond proportional bars | Contract §9 applies if plotting; bars with text labels stay inside Q5 = A |
