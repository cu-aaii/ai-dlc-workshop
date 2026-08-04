# builder-mcp plugin — Contract Specifications

Packaging contracts for shipping the Cornell Builder MCP as a **Claude Code / Claude
Cowork plugin**, numbered P1–P7. These sit *below* [`../SPEC.md`](../SPEC.md): the
server's contracts C1–C8 are upstream of this document and are **never** modified to suit
packaging. Where this document and `../SPEC.md` disagree, `../SPEC.md` wins.

Related: [README.md](README.md) (how to install), [`../deploy/LOCAL-TESTING.md`](../deploy/LOCAL-TESTING.md)
(how to run the server by hand), [`../devtools/README.md`](../devtools/README.md) (the
browser console — a *different* consumer of the same server).

---

## P0 — Purpose and non-goals

The plugin is **another wrapper around the same server**, not a second implementation.
The `devtools/` console and this plugin are siblings: both are MCP clients of
`builder_mcp.server`, neither owns it.

**Non-goals, stated so they are not drifted into:**

- **No change to the server.** Nothing under `../src/`, `../infra/`, `../Dockerfile`, or
  `../pyproject.toml` is touched. Other people are working on those simultaneously.
- **No change to `devtools/`.** That is a colleague's demo surface. It is not a
  dependency of this plugin and must keep working untouched.
- **No change outside `packages/builder-mcp/`.** The repo-root `.mcp.json`,
  `.claude/skills/`, `pipeline/`, and `blueprints/` are shared team property.
- **No new tools.** C3 freezes the surface at exactly eight tools and
  `test_all_eight_tools_registered` enforces it. The plugin exposes those eight and
  nothing else.

## P1 — Plugin identity and location

**Consumers**: Claude Code plugin loader, Claude Cowork plugin loader, teammates
installing the demo.

The plugin lives at `packages/builder-mcp/plugin/` — inside the team's builder-mcp
folder, so packaging work never collides with the rest of the workshop repo.

| Field | Value | Why |
|---|---|---|
| plugin `name` | `cornell-builder` | matches the MCP server name reported at `initialize` |
| marketplace `name` | `cornell-builder` | single-plugin marketplace; the directory is both roots |
| `version` | `0.1.0` | tracks `../pyproject.toml` `version` and moves with it |

The directory is simultaneously a **marketplace root** and a **plugin root**: a single
`.claude-plugin/` holding both `marketplace.json` and `plugin.json`, with the marketplace
entry's `source` set to `"./"`. This is an attested pattern, not an invention — the
first-party `cloudflare` marketplace ships exactly this shape.

## P2 — Server acquisition · the load-bearing decision

**Consumers**: every install of this plugin.

A plugin installed from a marketplace receives **only its own directory**. The Python
package at `packages/builder-mcp/src/` is *not* present, and `../` traversal is invalid
once a plugin is cached. The plugin therefore acquires the server from the **public**
repository at launch:

```
uvx --from git+https://github.com/cu-aaii/ai-dlc-workshop@main#subdirectory=packages/builder-mcp builder-mcp
```

`cu-aaii/ai-dlc-workshop` is public (`"visibility": "public"`), so this needs no
credential. `uv` caches the built environment after the first launch.

**Rules:**

- The `@main` ref is pinned in `.mcp.json` and is the only place the source ref appears.
- A local checkout **overrides** the fetch via the `BUILDER_MCP_SOURCE` environment
  variable, using `${BUILDER_MCP_SOURCE:-<git url>}` shell-style default expansion so the
  unset case degrades to the pinned URL rather than to an empty argument. Set it to a
  local package directory to test uncommitted changes. This is deliberately an env var
  and **not** a user-config key. Two different substitution systems are in play: plain
  `${VAR:-default}` shell-style defaults are expanded for ordinary environment variables,
  but `${user_config.KEY:-default}` is **not** supported — the loader parses the key as
  `KEY:-default`, finds no such option, and **silently discards the entire MCP server
  entry**. `BUILDER_MCP_SOURCE` therefore has to stay an env var for its default to be
  expressible at all. Verified by bisect against Claude Code 2.1.220.
- `uv` is a prerequisite. Its absence is an install-time failure with a clear message,
  never a silent tool-less session.

## P3 — Transport

**Consumers**: Claude Code / Cowork MCP client.

The plugin runs the server over **stdio** (`BUILDER_MCP_TRANSPORT=stdio`), one process
per session, owned by the host. It does **not** use the streamable-HTTP path on
`127.0.0.1:8000`.

This is deliberate and is what keeps the plugin and `devtools/` from colliding: the
console binds port 8000, the plugin binds nothing. Both can run at the same time.

C4's container contract (`0.0.0.0:8000`, `/mcp`, stateless) is unaffected — it describes
the AgentCore deployment, not this client.

## P4 — Configuration and credentials

**Consumers**: the person installing the plugin.

Per C7, every setting has a default and a bare install must start. All four config keys
are therefore **optional**.

| Key | Type | Default | Effect when unset |
|---|---|---|---|
| `github_token` | string, `sensitive` | unset | reads work anonymously; **writes return dry-run plans** (C5) |
| `github_org` | string | `cu-aaii` | catalog + PR target org |
| `workshop_repo` | string | `ai-dlc-workshop` | catalog + PR target repo |
| `aws_region` | string | `us-east-1` | region for stack + pipeline status reads |

The server source is **not** a user-config key — it is the `BUILDER_MCP_SOURCE`
environment variable, for the reason given in P2.

`${user_config.KEY}` resolves to the `default` declared for that key in `plugin.json`
when the user has not set it, and to an empty string when no `default` is declared
(verified against Claude Code 2.1.220). **The manifest's `default` values are therefore
load-bearing**: they, not the server's own fallbacks in `config.py`, are what a bare
install actually receives. `github_token` deliberately declares no default and so arrives
as `""`, which `config.py` treats as absent — giving read-only behaviour and dry-run
writes, exactly as C5 and C7 require.

Keep the manifest defaults and the server defaults in `config.py` in sync. They are
asserted independently and nothing detects a drift between them.

**On the token.** It is genuinely optional, and the plugin must never imply otherwise.
Measured against the live API: an anonymous `blueprint_search` costs **9 requests** (one
directory listing plus one per catalog entry) against a **60/hour** anonymous limit —
roughly **six searches per hour per IP**. A token raises that to 5,000/hour and is what
lets `deployment_create` open a real registration PR instead of describing one.

So: **no token needed to install or demo; a token needed for volume or for real PRs.**
The config description says this plainly rather than marking the field required.

The credential boundary from C5 is preserved exactly: the token is held by the server
process the host launches. It reaches that process as an environment variable via
`${user_config.github_token}` and is stored by Claude's own secret handling. Nothing in
this plugin writes a token to disk.

## P5 — Skill

**Consumers**: Claude, when a user asks to deploy something.

Exactly one skill ships: `skills/builder-mcp/SKILL.md`, namespaced on install as
`/cornell-builder:builder-mcp`.

It is **purpose-written for tool usage** and deliberately does **not** copy the repo's
`.claude/skills/` (`add-blueprint`, `add-container-build`, `diagnose-deploy`). Those are
authoring-time guides for people editing the workshop repo, they live outside our folder,
and `add-container-build` currently contradicts C4 on Dockerfile location. Vendoring a
copy would fork that drift into a shipped artifact.

The skill must teach the two things a caller gets wrong unaided:

1. **`dry_run` is a two-step confirm, not a debug flag.** C4's stateless requirement rules
   out MCP elicitation, so every write tool defaults `dry_run=True` and the plan must be
   shown to the user and confirmed before re-calling with `dry_run=False`.
2. **The governance invariants are permanent** (C3): no merge, no push to a tracked
   branch, no CloudFormation Create/Update/Delete. Merge is the only deploy trigger. A
   tool that appears not to deploy is behaving correctly.

## P6 — Distribution targets

**Consumers**: teammates on Claude Code and on Claude Cowork.

One directory produces both targets:

- **Claude Code** — `claude plugin marketplace add` against the repo (or a local path),
  then `claude plugin install cornell-builder@cornell-builder`.
- **Claude Cowork** — `build.sh` zips the plugin directory's *contents* into
  `dist/cornell-builder.plugin` for upload.

A Desktop `.mcpb`/DXT `manifest.json` is **out of scope** for this version. It is a third
schema with its own `${__dirname}` substitution rules, and shipping one unverified would
violate P7.

## P7 — Definition of done

A change to this plugin is done when **all** of the following have been observed, not
inferred. Loading is not passing; the tool-call gate is the one that matters.

| # | Gate | Command |
|---|---|---|
| 1 | Manifests valid, warnings fatal | `claude plugin validate <dir> --strict` |
| 2 | Server unchanged, suite still green | `cd .. && uv run pytest -q` → 77 passed |
| 3 | Installs non-interactively | `claude plugin install cornell-builder@cornell-builder` |
| 4 | Inventory correct | `claude plugin details` lists 1 MCP server + 1 skill |
| 5 | **All 8 tools callable over stdio** | live MCP handshake, `tools/list` equals the C3 set |
| 6 | **A real tool returns real data** | `blueprint_search` returns the live catalog |
| 7 | **A write tool honours `dry_run`** | `deployment_create` returns a plan, creates nothing |
| 8 | Cold path works | gates 5–7 with no checkout and no token |
| 9 | Colleague's console unharmed | `devtools/` still starts and connects on :8000 |
| 10 | **Resolved env correct on a bare install** | `claude mcp get plugin:cornell-builder:cornell-builder` |

Gate 9 is not ceremonial. The plugin and the console share a server module and a repo;
the plugin is finished only when the console is provably still working. `demo/mcp_call.py`
is a third client of the same server and belongs in the same check.

**Gate 10 exists because the failure it catches is invisible.** It must show
`BUILDER_MCP_GITHUB_ORG=cu-aaii`, `BUILDER_MCP_WORKSHOP_REPO=ai-dlc-workshop`,
`GITHUB_TOKEN=` (empty), and `Status: ✔ Connected`. A server entry **missing** from that
output means a substitution was rejected and the plugin is silently tool-less — and
neither plugin loading nor `claude plugin details` will tell you, because both keep
reporting "MCP servers (1)" regardless. Only the resolved-env view distinguishes a
working plugin from a hollow one.

Note also that `claude plugin update` will **not** pick up edits while the version string
is unchanged; re-verification requires `claude plugin uninstall` followed by
`claude plugin install`.
