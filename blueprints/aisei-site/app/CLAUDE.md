# CLAUDE.md

This file provides guidance to Claude Code when working with projects scaffolded from this template.

## What this is

AII base-template — the canonical scaffold for Angular + Hono projects in the AI Innovation Lab (Cornell CIT). All new projects copy this template and extend it with features.

## Tech Stack

- **Server**: Hono (Node.js) via `@hono/node-server`
- **Client**: Angular 21+ (standalone components, signals, Material UI)
- **Module system**: ESM only (`"type": "module"`)
- **Dev**: Concurrent Angular `:4200` + Hono `:4300` with proxy

## Project Structure

```
base-template/
├── server/
│   ├── index.ts          # Entry — starts Hono server
│   ├── app.ts            # Middleware, API routes, static serving
│   ├── app.config.ts     # Env vars + port config
│   └── modules/          # Feature modules (types → service → routes)
├── client/
│   └── app/
│       ├── app.routes.ts     # Top-level + public routes (AppRoute interface)
│       ├── admin.routes.ts   # Admin sub-routes (lazy-loaded)
│       ├── features/
│       │   ├── admin/        # Admin pages (dashboard, settings, documentation)
│       │   └── home/         # Public landing
│       └── shared/
│           ├── components/   # Reusable (bread-crumb)
│           ├── layout/       # Admin sidebar, toolbar, public nav
│           ├── services/     # ClientService (HTTP + caching)
│           └── theme/        # SCSS: variables, palette, typography, utilities
├── package.json
├── Dockerfile            # Multi-stage production build
├── .dockerignore
├── .devcontainer/        # VS Code dev container config
├── tool.json             # Factory registration (id, port, entry)
├── proxy.conf.json       # Angular dev proxy → Hono
└── angular.json
```

## Commands

```bash
npm run dev          # Angular :4200 + Hono :4300 (concurrent)
npm run build        # Production: Angular + tsc server
npm run start        # Serve production build
npm run check        # Type-check (no emit)
```

## Docker

```bash
docker build -t base-template .                        # Build production image
docker run -p 4300:4300 base-template                  # Run container
docker run -p 4300:4300 -e PORT=4300 base-template     # Override port via env
```

The Dockerfile uses a multi-stage build (Node 24 Alpine): build stage compiles Angular + server, prunes to production deps, then copies only `dist/` and `node_modules/` to the final image. Runs as non-root `node` user.

## Dev Container

Open in VS Code with the Dev Containers extension to get a pre-configured Node 24 environment. Ports 4200 (Angular) and 4300 (Hono) are forwarded automatically. Run `npm run dev` after the container starts.

## Key Conventions

| Area | Convention |
|------|-----------|
| Components | Standalone (default), signals, OnPush, native control flow (`@if`, `@for`) |
| Routing | `AppRoute` with `data.menu` array controlling nav visibility |
| HTTP | `ClientService` — pluggable caching (memory/local/session) |
| Server modules | `server/modules/<name>/` — types → service → routes |
| Styling | Cornell Material theme, utility CSS classes |
| Ports | Each project gets unique port in `tool.json` + `server/app.config.ts` |

## Skills Directory

| Skill | Path | Purpose |
|-------|------|---------|
| [Docs](.claude/skills/docs/SKILL.md) | `.claude/skills/docs/` | Documentation conventions and hierarchical index pattern |
| [Angular Component](.claude/skills/angular-component/SKILL.md) | `.claude/skills/angular-component/` | Angular v20+ component patterns (signals, host bindings, a11y) |
| [Routing](.claude/skills/routing/SKILL.md) | `.claude/skills/routing/` | Angular routing with AppRoute interface |
| [Feature Module](.claude/skills/feature-module/SKILL.md) | `.claude/skills/feature-module/` | Full-stack feature scaffolding (Hono server + Angular pages) |
| [Admin Data Table](.claude/skills/admin-data-table/SKILL.md) | `.claude/skills/admin-data-table/` | Server-paginated filterable tables |
| [Database](.claude/skills/database/SKILL.md) | `.claude/skills/database/` | TypeORM 1.0 with PostgreSQL or SQLite — entities, migrations, config |

## Important Rules

- Do NOT set `standalone: true` on components (default in Angular v20+)
- Do NOT use `*ngIf`, `*ngFor`, `*ngSwitch` — use `@if`, `@for`, `@switch`
- Do NOT use `ngClass` or `ngStyle` — use direct `[class.]` and `[style.]` bindings
- Do NOT use `@HostBinding`/`@HostListener` — use `host:` object in `@Component`
- Use `inject()` for all dependencies — no constructor injection
- Use `.js` extensions in server-side ESM imports
- Server filtering/pagination only — no client-side array manipulation for tables
