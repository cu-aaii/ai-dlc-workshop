---
name: database
description: >
  Add or configure a database connection using TypeORM 1.0 with PostgreSQL or SQLite.
  TRIGGER when: user asks to add a database, create entities, run migrations, set up TypeORM,
  connect to PostgreSQL or SQLite, or asks about the approved DB pattern.
  DO NOT TRIGGER when: user is only querying data in an existing service or editing route handlers.
---

# Database (TypeORM 1.0)

Approved ORM: **TypeORM 1.0** with **PostgreSQL** (production) or **SQLite/better-sqlite3** (local/lightweight).

## Installation

```bash
# PostgreSQL
npm install typeorm reflect-metadata pg

# SQLite
npm install typeorm reflect-metadata better-sqlite3

# Both (switchable via env)
npm install typeorm reflect-metadata pg better-sqlite3
```

## Project Structure

```
server/
├── data-source.ts          # DataSource configuration
├── entities/               # Entity classes
│   └── index.ts            # Barrel export of all entities
├── migrations/             # Generated migration files
├── subscribers/            # Entity subscribers (optional)
└── modules/<name>/
    └── <name>.entity.ts    # Entity can also live with its module
```

## TypeScript Configuration

Add to `server/tsconfig.json`:

```json
{
  "compilerOptions": {
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true
  }
}
```

## DataSource Configuration (`server/data-source.ts`)

```typescript
import 'reflect-metadata';
import { DataSource } from 'typeorm';
import { config } from './app.config.js';

// Import all entities explicitly (required for ESM)
import { User } from './entities/user.entity.js';

export const AppDataSource = new DataSource({
  // PostgreSQL
  type: 'postgres',
  host: config.dbHost,
  port: config.dbPort,
  username: config.dbUser,
  password: config.dbPassword,
  database: config.dbName,

  // Entities — always pass classes, never glob patterns
  entities: [User],

  // Migrations
  migrations: [],

  // NEVER use synchronize in production
  synchronize: config.dbSync,
  logging: config.dbLogging,
});
```

### SQLite variant

```typescript
import 'reflect-metadata';
import { DataSource } from 'typeorm';

import { User } from './entities/user.entity.js';

export const AppDataSource = new DataSource({
  type: 'better-sqlite3',
  database: './data/app.db',
  entities: [User],
  migrations: [],
  synchronize: false,
  logging: false,
});
```

### Switchable via environment

```typescript
import 'reflect-metadata';
import { DataSource, DataSourceOptions } from 'typeorm';
import { config } from './app.config.js';

import { User } from './entities/user.entity.js';

const entities = [User];

const postgresOptions: DataSourceOptions = {
  type: 'postgres',
  host: config.dbHost,
  port: config.dbPort,
  username: config.dbUser,
  password: config.dbPassword,
  database: config.dbName,
  entities,
  migrations: [],
  synchronize: false,
  logging: config.dbLogging,
};

const sqliteOptions: DataSourceOptions = {
  type: 'better-sqlite3',
  database: config.dbPath ?? './data/app.db',
  entities,
  migrations: [],
  synchronize: false,
  logging: config.dbLogging,
};

export const AppDataSource = new DataSource(
  config.dbType === 'sqlite' ? sqliteOptions : postgresOptions,
);
```

## Environment Variables (`server/app.config.ts`)

```typescript
export interface EnvVars {
  PORT?: string;
  DB_TYPE?: string;       // 'postgres' | 'sqlite'
  DB_HOST?: string;
  DB_PORT?: string;
  DB_USER?: string;
  DB_PASSWORD?: string;
  DB_NAME?: string;
  DB_PATH?: string;       // SQLite file path
  DB_SYNC?: string;       // 'true' only in dev
  DB_LOGGING?: string;
}

const env = process.env as unknown as EnvVars;

export const config = {
  port: Number(env.PORT ?? 4304),
  dbType: env.DB_TYPE ?? 'postgres',
  dbHost: env.DB_HOST ?? 'localhost',
  dbPort: Number(env.DB_PORT ?? 5432),
  dbUser: env.DB_USER ?? 'postgres',
  dbPassword: env.DB_PASSWORD ?? '',
  dbName: env.DB_NAME ?? 'app',
  dbPath: env.DB_PATH ?? './data/app.db',
  dbSync: env.DB_SYNC === 'true',
  dbLogging: env.DB_LOGGING === 'true',
} as const;
```

## Initialize in Server Entry (`server/index.ts`)

```typescript
import { serve } from '@hono/node-server';
import { config } from './app.config.js';
import { app } from './app.js';
import { AppDataSource } from './data-source.js';

const port = config.port;

AppDataSource.initialize()
  .then(() => {
    console.log('[db] connected');
    serve({ fetch: app.fetch, port }, (info) => {
      console.log(`[server] listening on http://localhost:${info.port}`);
    });
  })
  .catch((err) => {
    console.error('[db] connection failed', err);
    process.exit(1);
  });
```

## Entity Pattern

```typescript
// server/entities/user.entity.ts
import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  Relation,
  OneToMany,
} from 'typeorm';
import { Post } from './post.entity.js';

@Entity()
export class User {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ length: 100 })
  name: string;

  @Column({ unique: true })
  email: string;

  @Column({ default: true })
  isActive: boolean;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;

  // ESM requires Relation<T> wrapper to avoid circular import issues
  @OneToMany(() => Post, (post) => post.author)
  posts: Relation<Post[]>;
}
```

## ESM Rules for Relations

In ESM projects, **always** use the `Relation<T>` wrapper type on relation properties:

```typescript
import { Relation, ManyToOne, OneToMany, ManyToMany } from 'typeorm';

// Correct (ESM)
@ManyToOne(() => User, (user) => user.posts)
author: Relation<User>;

@OneToMany(() => Post, (post) => post.author)
posts: Relation<Post[]>;

@ManyToMany(() => Tag, (tag) => tag.posts)
tags: Relation<Tag[]>;
```

This prevents circular dependency issues that break ESM module resolution.

## Using Repositories in Services

```typescript
// server/modules/user/user.service.ts
import { AppDataSource } from '../../data-source.js';
import { User } from '../../entities/user.entity.js';

const userRepo = AppDataSource.getRepository(User);

class UserService {
  getAll(page = 1, pageSize = 10, search = '') {
    const qb = userRepo.createQueryBuilder('user');

    if (search) {
      qb.where('user.name ILIKE :search OR user.email ILIKE :search', {
        search: `%${search}%`,
      });
    }

    return qb
      .skip((page - 1) * pageSize)
      .take(pageSize)
      .getManyAndCount()
      .then(([items, total]) => ({ items, total }));
  }

  getById(id: string) {
    return userRepo.findOneBy({ id });
  }

  create(data: Partial<User>) {
    const user = userRepo.create(data);
    return userRepo.save(user);
  }

  async update(id: string, data: Partial<User>) {
    await userRepo.update(id, data);
    return userRepo.findOneBy({ id });
  }

  delete(id: string) {
    return userRepo.delete(id);
  }
}

export const userService = new UserService();
```

## Migrations

### Setup: add scripts to `package.json`

```json
{
  "scripts": {
    "typeorm": "typeorm-ts-node-esm",
    "migration:generate": "npm run typeorm -- migration:generate -d server/data-source.ts",
    "migration:run": "npm run typeorm -- migration:run -d server/data-source.ts",
    "migration:revert": "npm run typeorm -- migration:revert -d server/data-source.ts"
  }
}
```

### Generate a migration

```bash
npm run migration:generate -- server/migrations/CreateUserTable
```

This compares entities against the current DB schema and generates a migration file.

### Run migrations

```bash
npm run migration:run
```

### Revert last migration

```bash
npm run migration:revert
```

### Migration file structure

```typescript
// server/migrations/1717000000000-CreateUserTable.ts
import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateUserTable1717000000000 implements MigrationInterface {
  name = 'CreateUserTable1717000000000';

  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE "user" (
        "id" uuid NOT NULL DEFAULT uuid_generate_v4(),
        "name" varchar(100) NOT NULL,
        "email" varchar NOT NULL,
        "isActive" boolean NOT NULL DEFAULT true,
        "createdAt" TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt" TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT "UQ_user_email" UNIQUE ("email"),
        CONSTRAINT "PK_user" PRIMARY KEY ("id")
      )
    `);
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE "user"`);
  }
}
```

### Register migrations in DataSource

```typescript
import { CreateUserTable1717000000000 } from './migrations/1717000000000-CreateUserTable.js';

export const AppDataSource = new DataSource({
  // ...options
  migrations: [CreateUserTable1717000000000],
});
```

## Rules

- **Never use `synchronize: true` in production** — it can cause data loss
- **Always use migrations** for schema changes in non-dev environments
- **Pass entity classes directly** — never use glob patterns (they don't work reliably in ESM)
- **Use `Relation<T>`** wrapper on all relation properties (ESM requirement)
- **Use `.js` extensions** in all imports (ESM requirement)
- **Import `reflect-metadata`** at the top of `data-source.ts` (before any entity imports)
- **One entity per file** — name as `<name>.entity.ts`
- **UUIDs for primary keys** — use `@PrimaryGeneratedColumn('uuid')` for PostgreSQL
- **SQLite uses integer IDs** — use `@PrimaryGeneratedColumn()` if targeting SQLite only
- **`ILIKE` is Postgres-only** — use `LIKE` with `LOWER()` for SQLite compatibility

## SQLite-Specific Notes

- File stored at `./data/app.db` (add `data/` to `.gitignore`)
- No UUID generation — use `@PrimaryGeneratedColumn()` (auto-increment integer)
- No `ILIKE` — use `LOWER(column) LIKE LOWER(:param)` instead
- No concurrent writes — fine for single-server local tools
- `better-sqlite3` is synchronous — TypeORM wraps it in async for consistency

## .env Example

```env
# PostgreSQL
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secret
DB_NAME=myapp
DB_SYNC=false
DB_LOGGING=true

# SQLite (alternative)
# DB_TYPE=sqlite
# DB_PATH=./data/app.db
```

## .gitignore additions

```
data/
```
