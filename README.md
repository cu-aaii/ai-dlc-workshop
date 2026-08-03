# ai-dlc-workshop

Deploy path for Cornell's AI-DLC workshop (Aug 3–4, 2026). GitHub → CodePipeline → CodeBuild
→ CloudFormation, into an AWS account that builders never touch.

Adapted from the AI Innovation Lab reference pipeline. Its mechanics were preserved
deliberately; what changed is its shape — it deploys stacks from blueprint subdirectories
rather than one application.

> **This repository is public, and there is no secret-scanning safety net.** Never commit a
> credential, key, connection string, or anything else that should stay private. Secrets
> belong in AWS Secrets Manager; blueprints are configured to *use* them without ever
> containing them.
>
> Public repositories normally get secret-scanning push protection for free, but the
> `cu-aaii` org applies an enforced security configuration (`cu-aaii-org-config-1`) that
> disables secret scanning, and an enforced configuration cannot be overridden per
> repository. So nothing will stop you pushing a key — and once pushed to a public repo, a
> credential must be treated as compromised and rotated, not just deleted.

## Layout

A monorepo: one deploy path, a deploy surface, and one package per component.

```
blueprints/                 THE DEPLOY SURFACE — one directory per blueprint
  hello-world/                trivial tagged stack; proves the pipeline, and the demo floor
  course-chatbot/             the workshop MVP — scaffold only, deploys nothing yet
packages/                   components, one package each
  builder-mcp/                the Cornell Builder MCP server (track A)
pipeline/                   the deploy path
  pipeline.yml                CodePipeline / CodeBuild / ECR / IAM
  stacks.yml                  registry of every CloudFormation template in the repo
  validate_stacks.py          enforces registry ↔ filesystem ↔ pipeline ↔ manifest agreement
  codebuild.yml               container image buildspec
bootstrap/                  account baseline — deployed BY HAND, once per account
  account-bootstrap.yml       deploy role, artifact bucket, GitHub connection
observability/              seeing what's running (track E) — scaffold only
docs/
  aidlc-rules/                the AI-DLC methodology — vendored from awslabs, do not edit
  aidlc/                      how things here were built — a record, not a backlog
  decisions/                  one file per decision made on purpose
Dockerfile                  every container image, one target per component
tools/check                 the checks that gate a merge; CI runs this exact script
.github/workflows/
  pr-checks.yml               runs tools/check. No AWS calls, no credentials.
.mcp.json                   GitHub MCP server for Claude Code — needs one env var, see below
```

Every directory has its own README explaining what goes in it, except `docs/aidlc-rules/` — see
below for why that one is left exactly as upstream ships it.

**Two paths cannot move.** `pipeline/pipeline.yml`, because the running pipeline deploys itself
from that literal path and a commit that relocates it breaks the stage that would have picked up
the new location — recovery is a by-hand deploy. And `blueprints/`, which the pipeline names in a
`TemplatePath` and the Builder's catalog globs. Everything else is free to be rearranged.

## The AI-DLC rules

`docs/aidlc-rules/` is a verbatim copy of the `aidlc-rules/` directory from
[awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows) — the methodology this
workshop teaches, as a set of prompt files an agent reads.

| | |
|---|---|
| Upstream | `https://github.com/awslabs/aidlc-workflows` |
| Commit | `114ef4d0ae6082e63ff0c7d14a910e3195163235` (2026-07-22) |
| `docs/aidlc-rules/VERSION` | `1.0.1` |
| License | MIT No Attribution (MIT-0) — no attribution required, recorded here for re-sync |

**Nothing in `docs/aidlc-rules/` has been modified, and nothing should be.** Re-syncing a future
release is then a delete-and-replace:

```sh
git clone --depth 1 https://github.com/awslabs/aidlc-workflows.git /tmp/aidlc-upstream
rm -rf docs/aidlc-rules && cp -R /tmp/aidlc-upstream/aidlc-rules docs/aidlc-rules
```

> **The path deliberately differs from upstream's.** Upstream ships this at the repository root;
> here it sits under `docs/` beside `docs/aidlc/`. Copy it to `docs/aidlc-rules` rather than
> running upstream's own `cp -R … .`, which would recreate it at the root and leave the repo with
> two copies — one of them the one every reference points at, and not the new one.

Because a delete-and-replace discards local edits without warning, anything this repo needs to
say about the rules lives in `CLAUDE.md` or here instead.

The rules are **invocation-gated**: `CLAUDE.md` tells an agent to read
`docs/aidlc-rules/aws-aidlc-rules/core-workflow.md` when someone invokes AI-DLC, not on every
session. `core-workflow.md` claims priority over all other instructions, so loading it for
ordinary pipeline work would override this repo's own constraints. `CLAUDE.md` also has to name
`docs/aidlc-rules/aws-aidlc-rule-details/` explicitly, because the four rule-detail paths
`core-workflow.md` looks for natively (`.aidlc-rule-details/`, `.kiro/…`, and two others) do not
exist here.

Upstream's `.claude/settings.json` was **not** copied as-is. Its only real setting was a PR
attribution line asserting that contributions are licensed under *awslabs'* project license,
which would be false on this repo — and this repo has no `LICENSE` file to repoint it at. The
file here carries just the settings schema; add an attribution statement deliberately if the
workshop wants one.

## How a merge becomes a deployment

```
approved PR merged to main
  └─ Source ............ webhook fires within seconds (DetectChanges on the connection)
  └─ PipelineDeploy .... the pipeline deploys itself, so pipeline changes land on merge too
  └─ BlueprintDeploy ... one CloudFormation action per blueprint stack
```

`Environment` is the branch name and the Source stage tracks the branch of that name, so
`Environment=main` is what makes "merges to main deploy". A `test` branch deployed with
`Environment=test` gets its own pipeline and its own `aidlc-test-*` stacks.

> `Environment` is capped at **four lowercase alphanumerics** (`[a-z0-9]{1,4}`) — it lands in
> stack names and in the IAM scoping prefix. `main`, `test`, `dev` fit; `staging` and anything
> hyphenated are rejected by CloudFormation before the stack is created. So a parallel
> environment needs a short branch name, not just any branch name.

**CodePipeline does not enforce review.** Branch protection on the GitHub side is what makes
"a merge" mean "an approved PR" — see below.

## main is PR-only

Enforced by branch protection, not convention:

- Pull request required; direct pushes rejected, **including for admins**
- One approving review required
- The `validate` check must pass
- Stale approvals dismissed when new commits are pushed
- Force pushes and branch deletion blocked

Long-term this human approval gate becomes an automated reviewer agent. It is deliberately a
human for this workshop.

> Branch protection is why this repo is public. `cu-aaii` is on the GitHub Free plan, where
> branch protection and rulesets are unavailable on private repositories — the API returns
> 403. Public was the only way to enforce PR-only at zero cost on day one. The
> target-state platform generates *private* per-deployment repos that each need protection,
> so `cu-aaii` will need GitHub Team before that ships.

## Setting up a fresh AWS account

Three steps, in order. Only the first two are ever done by hand.

1. **Bootstrap the account** — `bootstrap/README.md`. Creates the deploy role, artifact
   bucket, and GitHub connection.
2. **Complete the GitHub handshake in the console.** CloudFormation creates the connection
   `PENDING`; only a human can authorize it. The pipeline's Source stage fails with an
   unrelated-looking permissions error until it reads `AVAILABLE`.
3. **Deploy the pipeline once** — `pipeline/README.md`. After that it self-updates from git;
   never deploy it by hand again.

## PR checks

The stack-registry check, `cfn-lint`, and the `builder-mcp` test suite. Lint, validate and unit
tests only — no AWS calls, no credentials, so they come back in about a minute.

Run them before you push:

```sh
tools/check
```

CI runs that exact script, so green locally means green on your PR.

**`uv` is the only prerequisite.** It fetches Python, pyyaml, cfn-lint and the `builder-mcp` test
dependencies on demand at pinned versions, so there is nothing to install globally and no venv to
activate:

```sh
brew install uv                                    # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh    # everything else
```

## GitHub MCP server

`.mcp.json` gives Claude Code sessions in this repo GitHub's hosted MCP server, so an agent can
read PRs, issues and repository contents directly instead of being told what they say. It is
optional — nothing in the deploy path depends on it, and declining the server leaves the repo
fully usable.

It authenticates with a **fine-grained personal access token**, which the config reads from
`GITHUB_MCP_PAT` rather than containing. That is not a style choice: this repo is public with no
secret-scanning safety net, and `.mcp.json` is committed, so a literal token here would be a
published credential. Keep it in your environment.

1. Create a token at [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens),
   scoped to this repository. Read-only on Contents, Issues and Pull requests is enough to
   review; add write only if you want the agent opening PRs as you.
2. Export it where your shell will pick it up before Claude Code starts:

   ```sh
   export GITHUB_MCP_PAT=github_pat_...        # macOS / Linux, in your shell profile
   ```

   ```powershell
   [Environment]::SetEnvironmentVariable('GITHUB_MCP_PAT', 'github_pat_...', 'User')
   ```

3. Restart Claude Code, approve the server when prompted, and run `/mcp`. `connected` means it
   worked; `failed` means the token is missing, expired, or not scoped to this repo. The token is
   never validated at config time, so a wrong value fails here rather than earlier.

The token is yours, not the workshop's — everyone sets their own, and it grants exactly the
GitHub access you gave it, entirely separate from the AWS deploy path. VS Code may flag
`${GITHUB_MCP_PAT}` as an unknown variable; that is VS Code checking the file against its own
`mcp.json` schema, and Claude Code expands it correctly.

## Conventions

**Tag every resource** with all four: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. These feed inventory and the cost and
usage dashboard — an untagged resource is invisible to the observability work, which makes it
invisible in the demo.

**Name stacks `<application>-<environment>-<name>`**, e.g. `aidlc-main-hello-world`. Not
cosmetic: the pipeline role scopes its CloudFormation permissions to
`stack/${Application}-${Environment}*`, so a stack named outside the convention cannot be
deployed.

**Register every template** in `pipeline/stacks.yml`, and give every `deployed_by: pipeline`
entry a matching action in `pipeline.yml`. Registering is what makes a template linted, and PR
checks fail on an unregistered template — or on a registered one that no pipeline action
deploys, which would otherwise deploy nothing while reporting success. A `blueprint.yaml` whose
`template:` is unregistered fails too: the manifest is what the Builder offers a builder, so that
one would advertise a blueprint whose deployment PR cannot deploy.

**Pass every parameter explicitly** from the pipeline. Template defaults exist so a stack can
be deployed by hand for debugging, not to be the real values.

**One package per component, under `packages/`.** Code that isn't a blueprint and isn't the deploy
path goes there, self-contained with its own `pyproject.toml` and lockfile. Container images stay
in the one root `Dockerfile` as named targets, because `pipeline/codebuild.yml` builds
`docker build $CODEBUILD_SRC_DIR --target $CONTAINER_TARGET` — repo-root context, default
filename, so per-package Dockerfiles are not an option.

## Not here yet

The deploy path works and the Cornell Builder is written. Still to come, per the workshop spec:
the `course-chatbot` blueprint itself — `blueprints/course-chatbot/` has the Lambda handler and a
README of what's missing, but no template, no image target and no pipeline action, so it deploys
nothing — the managed Bedrock Knowledge Base behind it, the Terraform stage for Azure/Entra
resources, and `observability/`. Each has a scaffolded directory with a README saying what goes in
it and how to wire it.
