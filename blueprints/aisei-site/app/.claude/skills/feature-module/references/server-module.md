# Server Module Pattern (Hono)

Each module lives in `server/modules/<name>/` and follows a three-file structure:
types → service → routes (mounted in `server/app.ts`).

---

## 1. Types (`<name>.types.ts`)

```typescript
export interface Item {
  id: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateItemDto {
  name: string;
  description?: string;
}

export interface UpdateItemDto {
  name?: string;
  description?: string;
}
```

---

## 2. Service (`<name>.service.ts`)

Business logic layer. Can use in-memory storage, file-based storage, or a database.
Keeps route handlers thin.

```typescript
import type { Item, CreateItemDto, UpdateItemDto } from './item.types.js';

class ItemService {
  private items: Item[] = [];

  getAll(page = 1, pageSize = 10, search = ''): { items: Item[]; total: number } {
    let filtered = this.items;
    if (search) {
      filtered = filtered.filter((i) =>
        i.name.toLowerCase().includes(search.toLowerCase()),
      );
    }
    const total = filtered.length;
    const start = (page - 1) * pageSize;
    return { items: filtered.slice(start, start + pageSize), total };
  }

  getById(id: string): Item | undefined {
    return this.items.find((i) => i.id === id);
  }

  create(dto: CreateItemDto): Item {
    const item: Item = {
      id: crypto.randomUUID(),
      ...dto,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.items.push(item);
    return item;
  }

  update(id: string, dto: UpdateItemDto): Item | undefined {
    const item = this.items.find((i) => i.id === id);
    if (!item) return undefined;
    Object.assign(item, dto, { updatedAt: new Date().toISOString() });
    return item;
  }

  delete(id: string): boolean {
    const idx = this.items.findIndex((i) => i.id === id);
    if (idx === -1) return false;
    this.items.splice(idx, 1);
    return true;
  }
}

export const itemService = new ItemService();
```

---

## 3. Routes (`<name>.routes.ts`)

Hono router with CRUD endpoints. Middleware can be added per-route when auth is enabled.

```typescript
import { Hono } from 'hono';
import { itemService } from './item.service.js';
import type { CreateItemDto, UpdateItemDto } from './item.types.js';

export const itemRouter = new Hono();

itemRouter.get('/', (c) => {
  const page = Number(c.req.query('page') ?? 1);
  const pageSize = Number(c.req.query('pageSize') ?? 10);
  const search = c.req.query('search') ?? '';
  const { items, total } = itemService.getAll(page, pageSize, search);
  return c.json({
    status: 200,
    data: items,
    pagination: { total, page, pageSize, totalPages: Math.ceil(total / pageSize) },
  });
});

itemRouter.get('/:id', (c) => {
  const item = itemService.getById(c.req.param('id'));
  if (!item) return c.json({ status: 404, message: 'Not found' }, 404);
  return c.json({ status: 200, data: item });
});

itemRouter.post('/', async (c) => {
  const dto = await c.req.json<CreateItemDto>();
  const item = itemService.create(dto);
  return c.json({ status: 201, data: item }, 201);
});

itemRouter.put('/:id', async (c) => {
  const dto = await c.req.json<UpdateItemDto>();
  const item = itemService.update(c.req.param('id'), dto);
  if (!item) return c.json({ status: 404, message: 'Not found' }, 404);
  return c.json({ status: 200, data: item });
});

itemRouter.delete('/:id', (c) => {
  const ok = itemService.delete(c.req.param('id'));
  if (!ok) return c.json({ status: 404, message: 'Not found' }, 404);
  return c.json({ status: 200, message: 'Deleted' });
});
```

---

## 4. Mount in `server/app.ts`

```typescript
import { itemRouter } from './modules/item/item.routes.js';

app.route('/api/items', itemRouter);
```

---

## Rules

- **ESM only** — use `.js` extensions in imports
- **No try/catch in routes** — Hono propagates errors to its error handler
- **Service is stateless singleton** — export a single instance
- **Auth middleware** — when enabled, add as route-level middleware: `itemRouter.use('*', authMiddleware)`
