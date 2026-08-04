---
name: admin-data-table
description: Build a server-paginated, filterable admin data table. TRIGGER when user asks to build a list/table page for an entity, add filtering or pagination, or create a browse view with status/date/search filters. DO NOT TRIGGER when building a full CRUD feature from scratch (use feature-module instead), or when only adding a form page.
---

# Admin Data Table

Use this skill when building a **paginated, filterable table** backed by a server API.
All filtering and pagination happens server-side — never use `MatTableDataSource` or client-side `Array.filter()`.

## Architecture

```
Server                              Client
──────────────────────────────      ──────────────────────────────────────────
service.getAll(params)              items.service.ts  → getItems(params)
  filter + paginate                   returns { data, pagination }
  returns { items, total }
routes.ts GET /api/items            items.component.ts
  parses query params                 @ViewChild(MatPaginator)
  returns { data, pagination }        signals: items, total, loading
                                      filters: status, search
                                      reload on every filter/page change
```

## Step Checklist

1. **Server service** — filter + paginate logic (array-based or DB-backed)
2. **Server routes** — parse `page`, `pageSize`, filter params; return `{ data, pagination }`
3. **Client service** — build `HttpParams` from all filter params; extends `ClientService`
4. **Client component** — `@ViewChild(MatPaginator)` + `AfterViewInit`, signals, `load(page)` method
5. **Route** — `pathMatch: 'full'`; sidebar entry needs `icon`, `title`, `path` in `data`

## Server Route Pattern (Hono)

```typescript
router.get('/', (c) => {
  const page = Number(c.req.query('page') ?? 1);
  const pageSize = Number(c.req.query('pageSize') ?? 10);
  const search = c.req.query('search') ?? '';
  const status = c.req.query('status') ?? '';

  const { items, total } = service.getAll(page, pageSize, search, status);
  return c.json({
    status: 200,
    data: items,
    pagination: { total, page, pageSize, totalPages: Math.ceil(total / pageSize) },
  });
});
```

## Client Service Pattern

```typescript
@Injectable({ providedIn: 'root' })
export class ItemsService extends ClientService {
  getItems(page = 1, pageSize = 10, search = '', status = ''): Observable<any> {
    let params = new HttpParams()
      .set('page', page)
      .set('pageSize', pageSize);
    if (search) params = params.set('search', search);
    if (status) params = params.set('status', status);
    return this.get('/api/items', { params });
  }
}
```

## Client Component Pattern

```typescript
@Component({
  selector: 'app-items',
  imports: [MatTableModule, MatPaginatorModule, MatInputModule, MatFormFieldModule],
  template: `
    <mat-form-field appearance="outline" class="full-width">
      <mat-label>Search</mat-label>
      <input matInput (input)="onSearch($event)" />
    </mat-form-field>

    <table mat-table [dataSource]="items()">
      <!-- columns -->
      <tr mat-header-row *matHeaderRowDef="columns"></tr>
      <tr mat-row *matRowDef="let row; columns: columns"></tr>
    </table>

    <mat-paginator
      [length]="total()"
      [pageSize]="pageSize"
      [pageSizeOptions]="[5, 10, 25]"
      (page)="onPage($event)"
    />
  `,
})
export class ItemsComponent implements OnInit {
  private service = inject(ItemsService);
  items = signal<Item[]>([]);
  total = signal(0);
  columns = ['name', 'status', 'actions'];
  pageSize = 10;
  private page = 1;
  private search = '';

  ngOnInit() { this.load(); }

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

## Rules

- Server-side filtering ONLY — no client-side array manipulation
- Always return `pagination` object alongside `data`
- Use signals for component state
- Use `@ViewChild(MatPaginator)` for paginator reference
- Reload data on every filter or page change
- Material table directives (`*matHeaderRowDef`, `*matRowDef`) require star-syntax — this is the exception to the "no structural directives" convention
