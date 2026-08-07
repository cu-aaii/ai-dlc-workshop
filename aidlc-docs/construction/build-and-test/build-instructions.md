# Build Instructions

**Phase**: CONSTRUCTION → Build and Test
**Date**: 2026-08-03 (U-01); **updated 2026-08-04 for U-02**
**Scope**: U-01 Domain Core **and** U-02 Dashboard Platform. The U-01 steps below still hold; U-02
adds two container images and a static-site build (§ "U-02 build steps").

There is no compile step for the Python. U-01 is pure Python with **no runtime dependencies**, so
"build" there means resolving the dev toolchain and confirming the package imports. U-02 adds real
build artifacts: two arm64 Lambda images and a Vite bundle.

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| `uv` | The repo's only Python prerequisite. Fetches the interpreter, pyyaml, cfn-lint and both packages' test dependencies. | `brew install uv` · `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `terraform` | Required by `tools/check` for the Azure/Entra modules. Not needed by U-01, but `tools/check` exits early without it. | `brew install hashicorp/tap/terraform` |

`blueprints/dashboard/.python-version` pins **3.13**. That pin is load-bearing: without it `uv` may
select a 32-bit interpreter, on which `cryptography` has no wheel and the install disappears into a
failing Rust build. The pin is why this package resolves a 64-bit CPython.

## Build steps

### 1. Resolve dependencies

```sh
cd blueprints/dashboard
uv sync
```

Creates `uv.lock` on first run. **Commit it** — it does not exist yet, because the package was
authored in an environment with no `uv`. Reproducibility across laptop, PR checks and CodeBuild
depends on it, and until it is committed those three can resolve different Hypothesis and mypy
versions.

### 2. Configure environment

**Nothing to configure.** No environment variable, credential, region, or profile. U-01 reads no
environment and no clock — `tools/check` greps to enforce that. This is why the unit can be built and
tested with no AWS account.

### 3. Build

```sh
uv run python -c "import dashboard.core; print(len(dashboard.core.__all__), 'public names')"
```

Expected: `22 public names`. There is no artifact to produce — U-01 ships as source inside U-02's two
container images.

### 4. Verify

```sh
tools/check
```

Runs everything: the stack registry, cfn-lint, both packages' tests, the domain-core boundary grep,
mypy, and terraform. CI runs this same script, so green here means green on the PR.

## Troubleshooting

**`error: uv is required and was not found`** — install `uv`. `tools/check` refuses to run partially
rather than skipping checks silently.

**`error: terraform is required and was not found`** — install terraform. It gates the whole script
even though U-01 does not use it.

**`cryptography` starts a Rust build** — `.python-version` is missing or `uv` picked a 32-bit
interpreter. Confirm the file exists and reads `3.13`.

**`dashboard core boundary` fails** — something under `src/dashboard/core/` imported an AWS SDK, read
`os`/a clock, logged, printed, used `assert`, or reached for pickle/yaml. That is not a lint nit: ten
property tests are runnable without AWS precisely because the code underneath cannot reach it. Move
the offending code to the collector or api package.

**`E0003 <template> could not be processed by glob.glob`** — a CRLF crept into
`validate_stacks.py --list` output. It reads like a broken template and is a broken path.

---

## U-02 build steps

U-02 adds three build artifacts. `tools/check` covers the Python and the templates; the images and
the UI bundle are built by these extra commands (and by the pipeline at deploy).

### Prerequisites (additional)

| Tool | Why |
|---|---|
| `docker` | Builds the two arm64 Lambda images. The daemon must be running. |
| `node` / `npm` | Builds the Vite/React UI bundle. |

### 1. The two container images (arm64)

```sh
cd blueprints/dashboard
docker build --platform linux/arm64 --target collector -t dashboard-collector .
docker build --platform linux/arm64 --target api        -t dashboard-api .
```

Both install `.[aws]` (boto3) into `${LAMBDA_TASK_ROOT}`; each `CMD` names its handler
(`dashboard.collector.handler.handler`, `dashboard.api.handler.handler`). Verified 2026-08-04: both
build, and each handler module imports cleanly inside the arm64 image. In the pipeline these are the
two `ArmContainerBuildProject` Build actions (`CONTAINER_TARGET=collector|api`,
`CONTAINER_CONTEXT=blueprints/dashboard`); deployed by digest.

### 2. The UI bundle

```sh
cd blueprints/dashboard/ui
npm ci
npm run build      # tsc --noEmit && vite build -> dist/
```

Expected: `dist/index.html` with an external module `<script>` and external CSS, **no inline
script** (the strict-CSP precondition; `modulePreload.polyfill=false`). In the pipeline this is the
`SiteBuildProject` action, which then `aws s3 sync dist/ s3://…-site/` **without `--delete`**.

### 3. Deployment artifact note

Nothing is deployed by this build. The images and bundle become live only through the pipeline's
BlueprintDeploy stage on a merge to `main` (shared account). The four `deployed`-only requirements
close there, not here.
