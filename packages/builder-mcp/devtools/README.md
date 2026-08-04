# devtools — local harnesses for the Builder MCP server

Two tools, neither on the deploy path:

| | |
|---|---|
| [`console.py`](#run-it) | Drive the server by hand in a browser — every tool, its schema, and a live call log. |
| [`preview_deploy.py`](#preview_deploypy--what-a-deployment_create-pr-would-deploy) | Render what a `deployment_create` PR *would* deploy, into a gitignored folder, before opening it. |

## `preview_deploy.py` — what a `deployment_create` PR would deploy

`deployment_create` returns a plan in prose. This renders the artifacts that plan describes,
so you can read the template CloudFormation receives, the parameter values it receives with
it, and the diff the registration PR would apply to `pipeline/pipeline.yml`.

```sh
cd packages/builder-mcp
uv run python devtools/preview_deploy.py tiny-chatbot --owner <netid>
uv run python devtools/preview_deploy.py tiny-chatbot --owner <netid> --name my-bot
```

Writes `outputs-preview/<name>/` at the repo root — gitignored, regenerated wholesale each
run. No AWS call, no GitHub call, nothing deployed.

| Path | What it is |
|---|---|
| `aws/template.yml` | The template CloudFormation receives, byte-identical to the blueprint's. Copied, not rendered: a CFN template is passed verbatim alongside its parameter values. |
| `aws/parameters.json` | Those values, split into `resolved`, `runtime_resolved` (CodePipeline `#{Ns.VAR}` variables, unknowable from a checkout) and `template_defaults_used`. |
| `pipeline/action.yml` | The exact `BlueprintDeploy` action the PR appends. |
| `pipeline/pipeline.yml.diff` | That insertion as a unified diff — the reviewable half of the PR. |
| `shell/` | The two files the Builder writes to `outputs/<name>/`. A record of intent; **nothing reads them at deploy time.** |
| `PREFLIGHT.md` | What would go wrong, and why. |

### Preflight

Exit status is `1` when a `BLOCKER` is found, `0` otherwise, so it works in a script. The
checks are the failure modes this repo has actually hit — each one produces a *green plan*
and then either a red PR check or a wrong stack:

- an override referencing a CodePipeline namespace no action declares (the component's Build
  stage was never wired)
- a blueprint registered `deployed_by: manual` that this PR would have the pipeline deploy —
  `validate_stacks.py` rejects the combination, so the PR cannot merge
- an advertised input that never reaches the template, and so is silently ignored
- a generated action landing outside the `BlueprintDeploy` stage
- overrides naming parameters the template does not declare, parameters with neither an
  override nor a default, and values violating their `AllowedPattern`

It calls the server's own `render_pipeline_action`, `deployment_repo_files`,
`insert_blueprint_action` and `Blueprint.from_manifest` rather than reimplementing them. A
preview that reimplemented the transforms would drift from the server and start lying, which
is worse than having no preview.

> `outputs-preview/` holds verbatim copies of blueprint templates, so it is in
> `validate_stacks.py`'s `SKIP_DIRS` as well as `.gitignore` — that scan walks the filesystem,
> not git, and would otherwise report every copy as an unregistered template.

## console.py — local console for the Builder MCP server

A browser harness for driving [`builder-mcp`](../README.md) by hand: a chat window on the
right, and on the left every tool the server advertises, its schema, and a live log of
every call with its raw arguments and result.

It is **not part of the deploy path** — no template, no `pipeline/stacks.yml` entry, no
image target, no pipeline action. Nothing here can be deployed, and a merge that touches
only this directory creates no AWS resources.

## Run it

`uv` is the only prerequisite. Everything below is local: nothing deploys, and no AWS
credentials are involved.

### One command — `tools/dev`

From the **repo root**. Starts the server and the console together, waits for the server to
accept connections, and takes both down on Ctrl-C.

| | |
|---|---|
| **Linux** | `tools/dev` |
| **macOS** | `tools/dev` |
| **Windows** | open **Git Bash**, then `tools/dev` |

Then open <http://127.0.0.1:8765>.

Expected output:

```
==> builder-mcp        http://127.0.0.1:8000/mcp
[mcp] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    note: ANTHROPIC_API_KEY is unset. ...
==> console            http://127.0.0.1:8765
    Ctrl-C stops both.
```

**Windows: use Git Bash, not PowerShell.** `tools/dev` is bash — it needs `/dev/tcp`, `trap`
and GNU `sed`. Typing `bash tools/dev` in PowerShell does *not* work: `bash` on the PATH
resolves to `C:\WINDOWS\system32\bash.exe`, which is the **WSL** launcher, and on a machine
with no WSL distro it fails with
`WSL (9 - Relay) ERROR: CreateProcessCommon:800: execvpe(/bin/bash) failed`.

If you want to launch it from PowerShell anyway, name Git Bash explicitly:

```powershell
& "C:\Program Files\Git\bin\bash.exe" tools/dev
```

### Stop it

**Ctrl-C in the terminal running it.** That is the only supported stop — the script traps it
and kills the server's process tree (`taskkill //T` on Windows, because msys turns `kill` into
`TerminateProcess`, which leaves children running).

Closing the terminal window, or killing the wrapper from outside, skips that trap and **leaks
both processes**. The ports stay bound and the next `tools/dev` fails to bind. Recovery:

```powershell
# Windows / PowerShell
Get-NetTCPConnection -State Listen -LocalPort 8000,8765 |
  ForEach-Object { taskkill /PID $_.OwningProcess /T /F }
```

```sh
# Linux / macOS
lsof -ti :8000 -ti :8765 | xargs -r kill
```

### Two terminals, if you prefer

Works in any shell on any platform, PowerShell included — no bash needed. First the server:

```sh
cd packages/builder-mcp
uv run builder-mcp                 # streamable HTTP on http://127.0.0.1:8000/mcp
```

Then the console:

```sh
cd packages/builder-mcp
uv run --script devtools/console.py    # http://127.0.0.1:8765
```

### Ports

`8000` server, `8765` console. Override with `BUILDER_MCP_PORT` and `BUILDER_CONSOLE_PORT`
(`tools/dev` reads both), or the full set in [Configuration](#configuration) below.

### Credentials

Neither process needs AWS. The tool panel and direct tool invokes work with nothing set. The
**chat** needs an Anthropic credential, and the write tools stay in plan-only mode without a
GitHub token:

| | Without it | Set it |
|---|---|---|
| `ANTHROPIC_API_KEY` | tool panel works, chat is unavailable | `export ANTHROPIC_API_KEY=...`, or `ant auth login` (the SDK finds the profile with no env var) |
| `GITHUB_TOKEN` | write tools return plans instead of touching GitHub (SPEC C5) | `export GITHUB_TOKEN=...` |

The header shows which of the two are present.

> Verified on Windows 11 / Git Bash 5.2 / uv 0.12.1: both ports bind, the console returns 200,
> and the MCP `initialize` handshake succeeds. The Linux and macOS paths are the same script
> and are not verified here — on macOS in particular, if you get `sed: illegal option -- u`,
> that is the `sed -u` in the `[mcp]` log prefix and it needs a BSD-compatible fallback.

`uv` reads the script's inline dependency block and builds a throwaway environment — there
is nothing to install, and `packages/builder-mcp/pyproject.toml` and `uv.lock` are
untouched. That is deliberate: `anthropic` is a dependency of this console and of nothing
else, and adding it to the package would put it in the lockfile and in the AgentCore image
the pipeline builds.

The chat needs an Anthropic credential. `ANTHROPIC_API_KEY` works; so does an
`ant auth login` profile, which the SDK picks up with no environment variable set. The
header shows which of `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` are present.

## What the panel shows

| | |
|---|---|
| **Tools** | Read from the live server's `tools/list` — name, description, parameter table, and a JSON box to invoke the tool directly. A direct invoke is a probe: it does **not** enter the conversation. |
| **Activity** | Every call from either source, newest first, with arguments, result, duration, and whether it came from `chat` or a `manual` invoke. |
| **Header** | Connection state, server name/version, model and effort, credential flags. |

In the chat, each tool call appears inline as a collapsible block with its arguments and
the server's raw response, plus a token-usage line per model turn. Claude's reasoning
summary, when there is one, sits above the reply under `thinking`.

## Why it looks like this

- **A real MCP client, not an import.** The console speaks MCP over streamable HTTP and
  reads tool schemas from `tools/list`, so it exercises the transport and the schemas a
  builder's Claude client would — including the `0.0.0.0:8000/mcp` contract in SPEC C4.
  Importing `builder_mcp` and calling the functions would test less.
- **The server's own instructions are the system prompt.** Taken from the `initialize`
  response, so the model is steered by what the server actually tells clients (plus a
  short note that it is being driven from a debug console), not by a prompt invented here.
- **A manual tool-use loop, not the SDK tool runner.** The point of the console is to show
  each tool call and its raw result as they happen; the loop is where those events come
  from. The runner would hide exactly what this is here to watch.
- **A fresh MCP session per operation.** Locally the server is stateful on `127.0.0.1` and
  sessions are cheap, so this avoids owning an anyio task-group lifetime across requests
  for no benefit at this scale.

## Governance

The console can't do anything the server can't. Mutating tools default to `dry_run=true`
(SPEC C3), the invoke box seeds `dry_run: true` so a stray click can't open a pull request,
and with no `GITHUB_TOKEN` the write tools return plans instead of touching GitHub
(SPEC C5). No tool here — or there — can deploy: merge is the only deploy trigger.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BUILDER_MCP_URL` | `http://127.0.0.1:8000/mcp` | Server to drive |
| `BUILDER_CONSOLE_HOST` / `BUILDER_CONSOLE_PORT` | `127.0.0.1` / `8765` | Console bind address |
| `BUILDER_CONSOLE_MODEL` | `claude-opus-5` | Model for the chat |
| `BUILDER_CONSOLE_EFFORT` | `medium` | `low` … `max`; raise for harder multi-tool reasoning |
| `BUILDER_CONSOLE_MAX_TURNS` | `12` | Tool-use rounds per message before giving up |
