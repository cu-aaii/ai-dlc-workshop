# WordPress → Angular Migration: Implementation Plan

**Status (2026-08-04)** — A scoped demo has been built on `feature/public-landing-demo`:
admin interface removed entirely; four static pages shipped — Home, Component
Library, Style Guide, and this Implementation Plan (rendered as an in-app page at
`/implementation-plan`). This covers a slice of Phase 2 (theme port) below plus a
static-content-only slice of Phase 5 (Home only). The data layer (Phases 3–4) and the
remaining Phase 5 pages (Blog, Projects, Events, People, Tools, About, Get Involved)
have not been started.

**Goal** — rebuild [innovationhub.ai.cornell.edu](https://innovationhub.ai.cornell.edu/) (WordPress: `cwd_base_2024` + `ai_innovation_lab` theme + `cornell-ai-innovation-lab-blocks` plugin) on this repo's Angular + Hono stack. Visually identical (Cornell branding, layout, color/type system), full real content, no WordPress/plugin maintenance burden.

## Architecture decisions

- **No CMS, no auth.** Public site reads from a read-only SQLite DB via **GET-only** routes — nothing writable is exposed, so no login/session/auth is needed anywhere in the app.
- **Dynamic without an editor.** Content updates are a re-run, not an edit: `npm run import:wp` re-fetches WordPress's REST API and upserts by slug. This is the only content-refresh mechanism — no admin CRUD UI.
- **Static vs. DB-backed.** Hand-authored copy (About/Hub Model, Get Involved, Tools intro text) lives directly in Angular templates. List/detail content (Blog, Projects, People, Events, Tools catalog) goes through the DB.
- **Events** — native module, not a port. WP's calendar is a 3rd-party Localist/Concept3D embed and isn't portable.
- **Fonts** — keep linking Cornell's Typekit kit (`nwp2wku`) in `client/index.html`. Cornell is entitled to its own kit; don't vendor licensed font files.

## Design reference

- [`style-guide.html`](./style-guide.html) — color tokens, type scale, spacing, breakpoints, Cornell logo/seal usage.
- [`component-library.html`](./component-library.html) — every reusable UI pattern with real markup/CSS (masthead, nav, hero, cards, footer, buttons).
- Consult both — via the `wp-style-guide` skill — before building or styling any component in this plan. Keep them in sync as new tokens/patterns are discovered.

## Page inventory

| WP page | New route | `data.menu` |
|---|---|---|
| Home | `/` | n/a (root) |
| About Us ▾ Hub Model | `/about` | `main` |
| About Us ▾ People | `/people` | `main` |
| Blog (list + post) | `/blog`, `/blog/:slug` | `main` |
| Tools & Resources | `/tools` | `main` |
| Projects ▾ Catalog | `/projects`, `/projects/:slug` | `main` |
| Projects ▾ Workflow | `/project-workflow` | `main` |
| Workshops & Events | `/events`, `/events/:slug` | `main` |
| Get Involved | `/get-involved` | `main` |

**Reusable page anatomy** — utility bar w/ search → red masthead (wordmark + seal) → primary nav w/ dropdowns → dark hero (gradient bg, italic accent headline) → 3-up decorative cards → quote block → article-card grid + See All → event-card list + See All → 4-col footer → legal bar.

## Content types

All content types are served by an existing custom WP REST namespace (`ailab/v1`) — no HTML scraping needed.

| Type | Source endpoint | Notes |
|---|---|---|
| Blog posts | `wp/v2/posts` or `ailab/v1/posts` | title, date, excerpt, content_html, featured image, categories |
| Projects | `ailab/v1/projects` | title, content_html, cohort/date, permalink |
| Events | `ailab/v1/events` | title, date, content_html (location/speakers in body) |
| People | `ailab/v1/people` | name, title, affiliation, college, email, socials — `featured_image` often null → name-only rendering |
| Tools | `ailab/v1/tools` | title, content_html — audience/type inferred from copy, not structured fields |

## Theme port

- Extend `client/app/shared/theme/_variables.scss` with new CSS var tokens: `--color-hero-bg`, `--color-hero-accent-1` (purple), `--color-hero-accent-2` (yellow), `--color-footer-bg`, `--color-footer-text`, `--color-link`. Keep existing `--color-primary`/`--color-accent` — they already match the live site.
- Add Typekit `<link rel="stylesheet" href="https://use.typekit.net/nwp2wku.css">` to `client/index.html`; set heading/body font family to `"freight-sans-pro", sans-serif` in `_typography.scss`.
- Self-host Font Awesome 4.7 (MIT-licensed) under `client/assets/fonts/` for `.fa-*` icon parity.
- New shared components under `client/app/shared/components/` (per `angular-component` skill — signals, OnPush, `host` bindings, no `standalone: true`): `masthead`, `hero`, `decorative-card`, `quote-block`, `article-card`, `project-card`, `event-card`, `person-card`, `tool-card`, `site-footer`.
- Reuse existing `MainMenuComponent`/`MainComponent` for nav shell + content wrapper — no change needed for dropdowns (renders `route.children` as `mat-menu` already).

## Data layer

Per the `database` skill: SQLite (`better-sqlite3`) — single content DB, no concurrent-write concerns since nothing is publicly writable.

- `server/data-source.ts` + `server/entities/{article,project,event,person,tool}.entity.ts` — one entity per content type: slug (unique), title, dates, `contentHtml`, `sourceUrl` (original WP permalink), `featuredImagePath` (migrated local asset).
- `server/modules/{blog,projects,people,events,tools}/` — `types.ts` + `service.ts` (list w/ pagination, `getBySlug`) + `routes.ts` (**GET only**, no auth middleware).
- `server/scripts/import-wp-content.ts` — standalone script, run via `npm run import:wp`, **never** an HTTP route:
  1. Fetch each `ailab/v1/{posts,projects,events,people,tools}` endpoint.
  2. Download every referenced image (`featured_media`, inline `<img>` in `content_html`) into `client/assets/wp/<type>/<slug>/…`; rewrite `content_html` image URLs to `/assets/wp/...`.
  3. Upsert rows by `slug` — safe to re-run; re-running is the content-update mechanism.
- `.gitignore`: add `data/` (SQLite file). Imported assets under `client/assets/wp/` **are** committed (migrated content, not a build artifact).

## Static asset migration

One-time copy of theme chrome (separate from the content-image download above):

- Cornell logo/seal SVGs + chevron/search/hamburger icons → `client/assets/branding/`.
- Favicon → `client/favicon.ico` (confirm match with WP's or replace).
- `angular.json`'s `assets: ["client/favicon.ico", "client/assets"]` already copies everything under `client/assets/**` — no config change, just drop files in.

## Public pages

Per the `feature-module` skill's `public-page.md` pattern (`menu:['main','mobile']`, `ClientService`-backed fetch, `storageType:'memory'` caching) — one folder per route under `client/app/features/public/`:

- `home/` — `hero`, `decorative-card`, `quote-block`, `article-card`, `event-card`, `site-footer`.
- `blog/` (list) + `blog-detail/` (`:slug`).
- `projects/` (list, college/cohort filters — server-side, per `admin-data-table` skill's no-client-filtering rule) + `project-detail/`.
- `events/` + `event-detail/`.
- `people/` — tiered: photo cards (core team/tech leads) vs. name-only lists (cohorts), driven by presence of `featured_image`.
- `tools/` — hand-authored intro sections + tool-card catalog from the tools API.
- `about/` (Hub Model — static), `get-involved/` (static, grouped by audience).
- `client/app/app.routes.ts` — replace `''→admin` redirect with real `HomeComponent`; add each route above with `data.menu:['main','mobile']`; change final wildcard from `redirectTo: 'admin'` to a 404 page or `redirectTo: ''`.

## Phased order

- [x] **1. Design deliverables** — `style-guide.html`, `component-library.html` (shipped for review).
- [ ] **2. Theme port** — SCSS tokens, Typekit link, Font Awesome, new shared chrome/card components, validated against `component-library.html`.
- [ ] **3. Data layer** — entities, `import:wp` script (incl. asset downloader), run it, spot-check row/asset counts against the live site.
- [ ] **4. Server GET modules** — blog, projects, events, people, tools.
- [ ] **5. Public pages** — build + wire into `app.routes.ts` in nav order: Home → Blog → Projects → Events → People → Tools → About → Get Involved (site navigable incrementally, not all-or-nothing).
- [ ] **6. Full nav wiring** — replace root redirect, 404 handling.
- [ ] **7. QA pass.**

## Verification

- `npm run check` after each phase (typecheck + prod build).
- `npm run dev`; load every route from the page inventory table in-browser and visually diff against the live WP page.
- Re-run `npm run import:wp` twice in a row — row counts and asset file counts must be stable (idempotency).
- `grep -r "passport\|jwt\|session" server/` stays empty — GET-only, no auth anywhere.
- Mobile breakpoint check (<768px) for nav collapse and card stacking, matching `_flex.scss`'s existing column-collapse behavior.

---
[← wp-migration/](./README.md) · [← docs/](../README.md) · [← README](../../README.md)
