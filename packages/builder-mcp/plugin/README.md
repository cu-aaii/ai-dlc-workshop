# Cornell Builder — Claude Code / Cowork plugin

Packages the [builder-mcp](../README.md) server as a plugin, so you can deploy Cornell
AWS infrastructure by talking to Claude.

This is **one of three surfaces** onto the same server, not a fork of it:

| Surface | What it is | Where |
|---|---|---|
| the server | MCP over streamable HTTP, deployed on AgentCore | [`../src/builder_mcp/`](../src/builder_mcp/) |
| the console | a browser devtools UI for live demos | [`../devtools/`](../devtools/) |
| **this plugin** | Claude Code + Claude Cowork packaging | you are here |

The contract is [SPEC-PLUGIN.md](SPEC-PLUGIN.md); the server's own contracts are
[`../SPEC.md`](../SPEC.md) and always win.

## Install — Claude Code

You need [`uv`](https://docs.astral.sh/uv/) on your PATH. Nothing else — no clone of this
repo, no AWS credentials, no GitHub token.

```bash
claude plugin marketplace add cu-aaii/ai-dlc-workshop --sparse packages/builder-mcp/plugin
claude plugin install cornell-builder@cornell-builder
```

Then restart Claude Code and confirm with `/mcp` that `cornell-builder` is connected.

To install from a local checkout instead:

```bash
claude plugin marketplace add ./packages/builder-mcp/plugin
claude plugin install cornell-builder@cornell-builder
```

## Install — Claude Cowork

```bash
./build.sh
```

produces `dist/cornell-builder.plugin`. In Claude, open the customize menu, press `+`
next to Personal plugins, choose **Add → Upload plugin**, pick that file, then **fully
quit and reopen Claude**. The restart is required; skipping it is the usual reason tools
do not appear.

## Configuration — all optional

Set these interactively with `/plugin configure cornell-builder@cornell-builder`, or
non-interactively at install time with `--config KEY=VALUE`.

| Key | Default | What it changes |
|---|---|---|
| `github_token` | unset | see below |
| `github_org` | `cu-aaii` | org the catalog is read from and PRs go to |
| `workshop_repo` | `ai-dlc-workshop` | repo the pipeline tracks |
| `aws_region` | `us-east-1` | region for stack and pipeline status |

### Do I need a GitHub token?

**No, not to install or to demo.** The workshop repo is public, so the blueprint catalog
is read anonymously.

Supply one for either of two reasons:

1. **Volume.** One catalog search costs about nine GitHub API requests, and anonymous
   access is capped at 60 per hour per IP — roughly six searches an hour, shared across
   everyone behind the same campus NAT. A token raises the cap to 5,000/hour.
2. **Real pull requests.** Without a token every write tool returns a *dry-run plan*
   instead of opening a PR. That is the designed behaviour (contract C5), not a failure.

A fine-grained PAT with `repo` scope on the target repo is enough. It is held by the
server process Claude launches and stored by Claude's own secret handling; this plugin
never writes it to disk.

## What it can and cannot do

Eight tools, frozen by contract C3. Read: `blueprint_search`, `deployment_read`,
`deployment_health`, `spec_export`. Write: `deployment_create`, `deployment_update`,
`deployment_restart`, `deployment_delete`.

Every write tool defaults to `dry_run=True` and returns a plan you must confirm before it
is re-run for real. The server is stateless and cannot prompt you itself, so this two-step
*is* the confirmation.

**Permanent invariants.** The builder never merges, never pushes to a tracked branch, and
never calls CloudFormation Create, Update, or Delete. A human merging a pull request is
the only thing that deploys. This is the security model.

## Development

Point the plugin at a local package instead of GitHub:

```bash
export BUILDER_MCP_SOURCE=/path/to/packages/builder-mcp
```

Verify a change the way [SPEC-PLUGIN.md](SPEC-PLUGIN.md) §P7 requires — validation,
the server's own suite, a live handshake listing all eight tools, and a dry-run write
that provably creates nothing:

```bash
claude plugin validate . --strict
cd .. && uv run pytest -q
```
