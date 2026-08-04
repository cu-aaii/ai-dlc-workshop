# Public Page Pattern

Public pages live in `client/app/features/public/<name>/` or `client/app/features/home/`.

---

## Route Registration (`app.routes.ts`)

```typescript
{
  path: 'my-page',
  pathMatch: 'full',
  loadComponent: () =>
    import('./features/public/my-page/my-page.component').then(m => m.MyPageComponent),
  data: {
    menu: ['main', 'mobile'],
    title: 'My Page',
  },
  title: 'My Page',
},
```

`data.menu` values:
| Value | Effect |
|---|---|
| `'main'` | Appears in `MainMenuComponent` (desktop top nav) |
| `'mobile'` | Appears in mobile menu |
| `[]` (empty) | Not shown in any nav |

---

## Component

```typescript
import { Component } from '@angular/core';

@Component({
  selector: 'app-my-page',
  template: `
    <h1>Page Title</h1>
    <p>Page content goes here.</p>
  `,
})
export class MyPageComponent {}
```

---

## Service (if needed)

Extend `ClientService` for HTTP calls with optional caching:

```typescript
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ClientService } from '../../../shared/services/client/client.service';

@Injectable({ providedIn: 'root' })
export class MyPageService extends ClientService {
  getData(): Observable<any> {
    return this.get('/api/some-endpoint', {}, {
      storageType: 'memory',
      ttlMS: 5 * 60 * 1000,
    });
  }
}
```

---

## Component Rules

- Do NOT set `standalone: true`
- Use `inject()` for all dependencies
- Use `signal()` for mutable state
- Use `@if` / `@for` — never `*ngIf` / `*ngFor`
