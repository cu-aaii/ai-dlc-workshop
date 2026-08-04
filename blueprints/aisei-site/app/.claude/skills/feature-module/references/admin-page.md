# Admin Page Pattern

Admin pages live in `client/app/features/admin/<name>/`. They use the admin layout
(sidebar + toolbar) automatically via the `admin.routes.ts` routing.

---

## Route Registration (`admin.routes.ts`)

```typescript
{
  path: 'items',
  pathMatch: 'full',
  loadComponent: () =>
    import('./features/admin/items/items.component').then(m => m.ItemsComponent),
  data: {
    menu: ['admin'],
    icon: 'list',
    title: 'Items',
    path: 'admin/items',
  },
  title: 'Items',
},
```

`data` fields:
| Field | Purpose |
|-------|---------|
| `menu: ['admin']` | Shows in admin sidebar |
| `icon` | Material icon name in sidebar |
| `title` | Sidebar label and breadcrumb |
| `path` | Full absolute path for sidebar link |

---

## List Component (Table)

```typescript
import { Component, inject, OnInit, signal, ViewChild, AfterViewInit } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { RouterLink } from '@angular/router';
import { ItemsService } from './items.service';

@Component({
  selector: 'app-items',
  imports: [
    MatTableModule, MatPaginatorModule, MatButtonModule,
    MatIconModule, MatInputModule, MatFormFieldModule, RouterLink,
  ],
  template: `
    <div class="flex justify-content-space-between align-items-center mb-2">
      <h1>Items</h1>
      <a mat-raised-button color="primary" routerLink="add">
        <mat-icon>add</mat-icon> Add Item
      </a>
    </div>

    <mat-form-field appearance="outline" class="full-width">
      <mat-label>Search</mat-label>
      <input matInput (input)="onSearch($event)" />
    </mat-form-field>

    <table mat-table [dataSource]="items()">
      <ng-container matColumnDef="name">
        <th mat-header-cell *matHeaderCellDef>Name</th>
        <td mat-cell *matCellDef="let item">{{ item.name }}</td>
      </ng-container>
      <ng-container matColumnDef="actions">
        <th mat-header-cell *matHeaderCellDef>Actions</th>
        <td mat-cell *matCellDef="let item">
          <a mat-icon-button [routerLink]="['edit', item.id]">
            <mat-icon>edit</mat-icon>
          </a>
        </td>
      </ng-container>
      <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
      <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
    </table>

    <mat-paginator
      [length]="total()"
      [pageSize]="10"
      [pageSizeOptions]="[5, 10, 25]"
      (page)="onPage($event)"
    />
  `,
})
export class ItemsComponent implements OnInit, AfterViewInit {
  private service = inject(ItemsService);
  items = signal<any[]>([]);
  total = signal(0);
  displayedColumns = ['name', 'actions'];
  @ViewChild(MatPaginator) paginator!: MatPaginator;

  private search = '';
  private page = 1;
  private pageSize = 10;

  ngOnInit() { this.load(); }
  ngAfterViewInit() {}

  load() {
    this.service.getItems(this.page, this.pageSize, this.search).subscribe((res) => {
      this.items.set(res.data);
      this.total.set(res.pagination.total);
    });
  }

  onSearch(event: Event) {
    this.search = (event.target as HTMLInputElement).value;
    this.page = 1;
    this.load();
  }

  onPage(event: any) {
    this.page = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.load();
  }
}
```

---

## Service

```typescript
import { Injectable } from '@angular/core';
import { HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ClientService } from '../../../shared/services/client/client.service';

@Injectable({ providedIn: 'root' })
export class ItemsService extends ClientService {
  getItems(page = 1, pageSize = 10, search = ''): Observable<any> {
    return this.get('/api/items', {
      params: new HttpParams()
        .set('page', page)
        .set('pageSize', pageSize)
        .set('search', search),
    });
  }

  getItem(id: string): Observable<any> {
    return this.get(`/api/items/${id}`);
  }

  createItem(data: any): Observable<any> {
    return this.post('/api/items', data);
  }

  updateItem(id: string, data: any): Observable<any> {
    return this.put(`/api/items/${id}`, data);
  }

  deleteItem(id: string): Observable<any> {
    return this.delete(`/api/items/${id}`);
  }
}
```

---

## Component Rules

- Do NOT set `standalone: true` (default in Angular v20+)
- Use `inject()` for all dependencies
- Use `signal()` for mutable state
- Arrow functions are NOT allowed in template expressions — use component methods
- Use `@if` / `@for` — never `*ngIf` / `*ngFor`
