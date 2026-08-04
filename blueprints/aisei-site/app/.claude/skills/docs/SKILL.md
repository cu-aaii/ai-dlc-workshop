---
name: docs
description: >
  Create or update documentation in this project following the hierarchical index pattern.
  TRIGGER when: user asks to add a doc, update existing docs, document a new feature or module,
  or asks how documentation works in this project.
  DO NOT TRIGGER when: user only wants inline code comments or JSDoc on a single function.
---

# Documentation

**Hierarchical index pattern** — every doc links back to its parent; every directory index links to its children.

## Writing Style

**No fluff. Every line earns its place.**

- **Bold lead** states the rule or fact — the skim target
- **Bullet list** gives specifics: paths, values, caveats — one fact per bullet
- **Inline code** for anything you'd type: paths, commands, variable names
- **Fragments over sentences** — omit words that add no information
- **No prose paragraphs** — if it needs one, it belongs in a linked file, not inline
- **No obvious explanations** — don't explain why a path is a path

Bad: _"This section describes the configuration options that are available for this module."_
Good: **Configuration** — env vars and defaults

## Structure

### Index tables

Two-column markdown table in every index file. Relative link + one-line description per row.

### Breadcrumb footer

Every doc ends with a line linking back up. Count `../` per directory level crossed:

- `docs/foo.md` → `[← docs/](./README.md) · [← README](../README.md)`
- `server/modules/Auth/README.md` → `[← modules/](../README.md) · [← README](../../README.md)`

### One topic per file

Cross-link with relative markdown links — never duplicate content.

### Root `README.md`

Brief project description + table linking to every major doc. No deep technical content.

## Where to Register New Docs

| New doc location                  | Update these indexes                          |
| --------------------------------- | --------------------------------------------- |
| `docs/`                           | `docs/README.md` + root `README.md`           |
| `server/modules/<Name>/README.md` | `server/modules/README.md` + root `README.md` |
| `docs/templates/`                 | `docs/templates/README.md` + `docs/README.md` |
| `client/`                         | `client/README.md` + root `README.md`         |

`docs/README.md` is scoped to `docs/` only — do NOT add `server/modules/` rows there.

## Server Module READMEs

Every `server/modules/<Name>/` gets a `README.md`. Required sections:

- **Overview** — what it does, which routes it owns
- **Endpoints** — table: method, path, auth, description
- **Key exports** — service methods, one-line each
- **Configuration** — env vars or config keys it reads

## Directory READMEs

Any directory with multiple files or non-obvious purpose gets a `README.md`. Single-file folders: skip it.

## Updating Existing Docs

- Keep breadcrumb footer intact
- Renamed/moved doc → grep `*.md` for old filename, fix every stale link

## Angular Documentation Page (REQUIRED)

**Every project has a documentation page at `client/app/features/admin/documentation/documentation.component.ts`.**

When any documentation is created or updated (markdown docs, module READMEs, architecture changes, new features), you **MUST also update the Angular documentation component** to reflect the change.

### Rules

- The documentation page is the **user-facing** version of the project's technical docs
- Keep the component template in sync with the project's actual architecture, workflows, and features
- Use mermaid diagrams (via CDN load in `ngAfterViewInit`) for architecture/flow visuals
- Update sections: overview, architecture diagrams, tech stack, workflows, endpoints
- Do NOT just link to markdown files — render the content directly in the component template
- When a new module/feature is added, add a corresponding section to the documentation page

### Mermaid CDN Pattern

Diagrams use runtime CDN loading — no npm dependency:

```typescript
ngAfterViewInit() {
  const nodes = this.el.nativeElement.querySelectorAll('.mermaid');
  if (!nodes.length) return;
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
  script.onload = () => {
    (window as any).mermaid.initialize({ startOnLoad: false, theme: 'default' });
    (window as any).mermaid.run({ nodes });
  };
  document.head.appendChild(script);
}
```
