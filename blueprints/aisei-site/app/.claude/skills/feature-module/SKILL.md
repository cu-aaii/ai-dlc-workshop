---
name: feature-module
description: >
  Add a new full-stack feature to a project — a Hono server module paired with Angular admin or public client pages.
  TRIGGER when: user asks to add a new resource/CRUD section, create an admin page, add a server module, scaffold a new feature, or build a table/form UI for a new entity.
  DO NOT TRIGGER when: editing an existing feature, fixing bugs, or making changes to infrastructure/config.
---

# Feature Module

Use this skill when adding a new full-stack feature to a project. A feature consists of a **server module** and one or more **client pages**.

## Architecture Overview

```
Server module                   Client feature
──────────────────────          ───────────────────────────────────────
server/modules/<name>/          client/app/features/admin/<name>/   (admin)
  <name>.types.ts               client/app/features/public/<name>/  (public)
  <name>.service.ts               <name>.model.ts
  <name>.routes.ts                <name>.service.ts
                                  <name>.component.ts          (list)
                                  <name>-add/                  (add form)
                                  <name>-edit/                 (edit form)
                                  <name>-view/                 (detail, optional)
```

## Step Checklist

1. **Server**: Create types → service → routes in `server/modules/<name>/`
2. **Server**: Mount routes in `server/app.ts`
3. **Client**: Create model interface, service (extends `ClientService`), and page components
4. **Client**: Register routes in `admin.routes.ts` (admin) or `app.routes.ts` (public)

## Reference Files

- [Server module pattern](references/server-module.md) — types, service, Hono routes
- [Admin page pattern](references/admin-page.md) — dashboard, list/table, add/edit forms
- [Public page pattern](references/public-page.md) — public-facing pages
