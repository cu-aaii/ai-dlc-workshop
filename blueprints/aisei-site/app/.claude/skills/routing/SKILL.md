---
name: routing
description: >
  Add, modify, or understand routes in this Angular application.
  TRIGGER when: user asks to add a new page, add a route, make a page appear in a nav menu,
  or asks how the routing system works.
  DO NOT TRIGGER when: user is only editing the content of an existing page component.
---

# Angular Routing

Routes in this project use the custom `AppRoute` type, which extends Angular's `Route` and
requires a `data` object. The `data` fields drive navigation menus, breadcrumbs, and
access control.

## `AppRoute` — the custom route type

```typescript
// client/app/app.routes.ts
export interface RouteData {
  menu: string[];     // REQUIRED — which nav menus render a link for this route
  title?: string;     // display label in nav menus and breadcrumbs
  icon?: string;      // Material icon name (admin sidebar only)
  path?: string;      // FULL absolute path used by sidebar links (e.g. 'admin/users')
  roles?: string[];   // reserved for future auth guard
  [key: string]: any;
}

export interface AppRoute extends Route {
  data: RouteData;
  children?: AppRoute[];
}
```

### `data.menu` — which navs show this route

| Value | Component that renders it |
|-------|--------------------------|
| `'main'` | `MainMenuComponent` — horizontal desktop nav bar |
| `'admin'` | `SimpleSideMenuComponent` — admin sidebar |

Most routes use `[]` (hidden everywhere) or `['main']` for public pages.
Admin pages use `['admin']`.

### `data.path` vs Angular's `route.path`

`data.path` is the **full absolute path** the sidebar links to (e.g. `'admin/users'`).
Angular's `route.path` is the **relative segment** used by the router (e.g. `'users'`).
These are different — the sidebar reads `data.path` because it needs the full URL.

### `Route.title` vs `data.title`

`Route.title` (Angular built-in) sets the browser tab title.
`data.title` is the label shown in nav menus and breadcrumbs — always set this too.

---

## File structure

```
client/app/
  app.routes.ts       ← public + top-level routes (welcome, admin, login, error pages)
  admin.routes.ts     ← admin sub-routes, lazy-loaded from the 'admin' route
```

Use `app.routes.ts` for public pages and the top-level `admin` wrapper.
Use `admin.routes.ts` for anything under `/admin/`.

---

## Adding a public page

1. Create the component under `client/app/features/public/<name>/`.
2. Add to `app.routes.ts`:

```typescript
{
  path: 'my-page',
  loadComponent: () => import('./features/public/my-page/my-page.component')
    .then(m => m.MyPageComponent),
  data: {
    menu: ['main'],
    title: 'My Page',
  },
  title: 'My Page',
},
```

Add before the `**` wildcard catch-all.

---

## Adding an admin page

1. Create the component under `client/app/features/admin/<name>/`.
2. Add to `admin.routes.ts`:

```typescript
{
  path: 'my-section',
  pathMatch: 'full',
  loadComponent: () => import('./features/admin/my-section/my-section.component')
    .then(m => m.MySectionComponent),
  data: {
    menu: ['admin'],
    icon: 'settings',          // Material icon — shown in the sidebar
    title: 'My Section',       // sidebar label and breadcrumb
    path: 'admin/my-section',  // FULL path for the sidebar link
  },
  title: 'My Section',         // browser tab title
},
```

The route will automatically appear in the admin sidebar because `data.menu` includes
`'admin'` and `SimpleSideMenuComponent` filters on that value.

---

## Protecting a route by role (planned)

Auth guards are not yet implemented in the base-template. When added, use
`canActivate: [MultiRoleGuard]` and `data.roles`:

```typescript
{
  path: 'admin',
  canActivate: [MultiRoleGuard],
  data: {
    menu: ['admin'],
    roles: ['admin'],     // user must have at least one of these roles
  },
  loadChildren: () => import('./admin.routes').then(m => m.AdminRoutes),
}
```

---

## Breadcrumbs

`BreadCrumbComponent` reads `Route.title` from each segment in the active route tree.
Set `title:` (the Angular built-in, not `data.title`) on every route you want to appear
in the breadcrumb.

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Setting `data.path: 'admin/users'` to a relative path | Must be the full absolute path — the sidebar builds links with it directly |
| Using `data.title` but not `title:` | Breadcrumb won't show the page name |
| Adding a route after the `**` wildcard | Move it before the wildcard; routes after it are unreachable |
