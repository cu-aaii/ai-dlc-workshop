# AII Base Template

Scaffold for Angular + Hono projects in the AI Innovation Lab (Cornell CIT). Each project built from this template ships a standalone Angular frontend backed by a Hono API server.

## Quick Start

```bash
# Install dependencies
npm install

# Start development servers
npm run dev
# → Angular on http://localhost:4200
# → Hono API on http://localhost:4300 (proxied from Angular)
```

## Documentation

| Doc | Description |
|---|---|
| [docs/](./docs/README.md) | Project-specific docs (migrations, design references) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Hono (Node.js) via `@hono/node-server` |
| Client | Angular 21+ (standalone components, signals, Material UI) |
| Runtime | Node 24 (ESM only) |
| Theme | Cornell Material palettes (blue primary, red accent) |

### Why Hono?

| | Hono | Express | Flask | FastAPI |
|---|---|---|---|---|
| Language | TypeScript/JS | JavaScript | Python | Python |
| Module system | ESM native | CJS (ESM partial) | N/A | N/A |
| Performance | ~4x Express (Web Standards API) | Baseline | Moderate | High (async) |
| Type safety | Full TypeScript, typed routes | Bolt-on via `@types` | Optional (mypy) | Pydantic models |
| Bundle size | ~14KB | ~200KB | N/A | N/A |
| Runtime portability | Node, Deno, Bun, Cloudflare Workers, edge | Node only | CPython/PyPy | CPython + uvicorn |
| Middleware | Web-standard, composable | Connect-style | Decorators/WSGI | Depends/middleware |
| Shared language with frontend | Yes (same TypeScript) | Yes (JS) | No | No |
| Learning curve | Low (familiar patterns) | Low | Low | Moderate (async + Pydantic) |
| Ecosystem maturity | Growing (2022+) | Very mature (2010+) | Very mature (2010+) | Mature (2018+) |

**Our choice: Hono** — same TypeScript across the full stack, ESM native, runs anywhere Node runs (or at the edge), minimal footprint, and no framework lock-in (it's just Web Standards `Request`/`Response`).

### Why Angular?

| | Angular 21+ | React 19+ |
|---|---|---|
| Architecture | Opinionated full framework | Library + ecosystem assembly |
| Reactivity | Signals (fine-grained, no VDOM) | Virtual DOM diffing |
| Change detection | OnPush (opt-in granular) | Re-renders entire subtree by default |
| Module system | Full ESM, standalone components | ESM (but bundler-dependent) |
| CLI | Built-in (`ng generate`, `ng serve`, `ng build`) | Third-party (Vite, CRA deprecated, Next) |
| Dev server | Integrated with HMR + proxy config | Varies by meta-framework |
| Migration tooling | `ng update` with automated schematics | Manual, breaking changes common |
| Routing | Built-in, lazy-loading, guards, resolvers | `react-router` (separate library) |
| Forms | Built-in reactive forms + validation | `react-hook-form` or similar (separate) |
| HTTP client | Built-in with interceptors | `fetch` / `axios` (separate) |
| Styling | Component-scoped SCSS (ViewEncapsulation) | CSS Modules, styled-components, Tailwind |
| Testing | Karma/Jest + TestBed built-in | Jest/Vitest + Testing Library (separate) |
| Dependency injection | First-class DI system | Context API / prop drilling |
| Meta-framework influence | Self-contained (no Next.js equivalent needed) | Heavily influenced by Next.js/Remix |
| Vendor lock-in risk | Low (Google-backed, stable API contracts) | Moderate (Next.js pushing Vercel platform features) |
| LTS & stability | Predictable 6-month releases, deprecation policy | Frequent paradigm shifts (classes → hooks → RSC) |
| Template syntax | Native control flow (`@if`, `@for`) | JSX (mixed logic + markup) |

**Our choice: Angular** — signals-based reactivity with no VDOM overhead, full ESM, built-in tooling (CLI, proxy, migrations), strong DI, and long-term stability without relying on a meta-framework. No vendor lock-in to a hosting platform.

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
│       ├── app.routes.ts     # Top-level routes (AppRoute interface)
│       ├── admin.routes.ts   # Admin sub-routes (lazy-loaded)
│       ├── features/         # Feature pages (admin, home)
│       └── shared/           # Components, layout, services, theme
├── Dockerfile            # Multi-stage production build
├── .devcontainer/        # VS Code dev container config
├── package.json
├── tool.json             # Factory registration (id, port, entry)
├── proxy.conf.json       # Angular dev proxy → Hono
└── angular.json
```

## Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Angular :4200 + Hono :4300 concurrently |
| `npm run build` | Production build (Angular + tsc server) |
| `npm run start` | Serve production build |
| `npm run run:local` | Build and serve in one step |
| `npm run check` | Type-check without emitting |

## Local Development

### Prerequisites

- Node.js 24+
- npm 11+

### Environment Variables

Copy the example env file and adjust as needed:

```bash
cp example.env .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `4300` | Server port |

### Dev Proxy

In development, Angular runs on `:4200` and proxies `/api/*` requests to the Hono server on `:4300` via `proxy.conf.json`. In production, Hono serves both the API and the static Angular build.

## Docker

### Build

```bash
docker build -t base-template .
```

The Dockerfile uses a multi-stage build:
1. **Build stage** — installs all dependencies, compiles Angular + server TypeScript, prunes to production deps only
2. **Production stage** — copies `dist/` and pruned `node_modules/` into a clean Node 24 Alpine image

### Run

```bash
docker run -p 4300:4300 base-template
```

Override configuration via environment variables:

```bash
docker run -p 8080:8080 -e PORT=8080 base-template
```

### Security

- Runs as non-root `node` user
- Multi-stage build excludes source code, dev dependencies, and build tools from the final image
- `.dockerignore` excludes `node_modules`, `.env`, `.git`, and other sensitive/unnecessary files
- No secrets baked into the image — inject via `-e` or `--env-file` at runtime

## Dev Container

Open the project in VS Code with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) for a pre-configured environment:

- Node 24 with npm
- Ports 4200 and 4300 forwarded automatically
- Angular Language Service and Prettier extensions pre-installed
- Dependencies installed on container creation

Run `npm run dev` after the container starts.

## Production Deployment

1. Build the Docker image
2. Push to your container registry
3. Deploy to any container runtime (Docker, Podman, Kubernetes, Cloud Run, ECS, etc.)
4. Set environment variables for your target environment
5. Expose the container port (default 4300)

The image is self-contained — no external file mounts or build steps needed at deploy time.

## Security Considerations

- **No secrets in images** — environment variables are injected at runtime, never during build
- **Non-root execution** — container runs as the `node` user (UID 1000)
- **Minimal attack surface** — Alpine base, production deps only, no shell tools beyond what Alpine provides
- **`.env` excluded** — listed in both `.gitignore` and `.dockerignore`
- **Dependency auditing** — run `npm audit` regularly; `npm ci` in the Dockerfile ensures reproducible installs from the lockfile
- **Update policy** — use `npm update --before="$(date -u -d '-36 hours' +%Y-%m-%dT%H:%M:%S)"` to only install versions published at least 36 hours ago, reducing supply-chain risk from compromised new releases
- **Package manager** — pnpm preferred for faster installs and stricter dependency resolution
