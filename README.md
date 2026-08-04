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
  notify-topic/               one SNS topic, optional email subscription; no compute
  knowledgebase/              Bedrock managed knowledge base; verifies its own ingestion
  entra-probe/                one Entra app registration; proves the Terraform path
  tiny-chatbot/               canned-response Lambda behind a Function URL; parked
  aisei-site/                 an existing Angular + Hono app as a Lambda container; parked
  course-chatbot/             the workshop MVP — scaffold only, deploys nothing yet
packages/                   components, one package each
  builder-mcp/                the Cornell Builder MCP server (track A)
    Dockerfile                its image — per component, named target, no root Dockerfile
pipeline/                   the deploy path
  pipeline.yml                CodePipeline / CodeBuild / ECR / IAM / TF state / Azure secret
  stacks.yml                  registry of every CloudFormation template in the repo
  validate_stacks.py          enforces registry ↔ filesystem ↔ pipeline ↔ manifest ↔ TF agreement
  codebuild.yml               container image buildspec
  terraform.yml               Azure/Entra Terraform buildspec (wired to the Terraform stage)
bootstrap/                  account baseline — deployed BY HAND, once per account
  account-bootstrap.yml       deploy role, artifact bucket, GitHub connection
observability/              seeing what's running (track E) — scaffold only
demo/                       terminal walkthrough of the builder path; the no-Teams fallback
docs/
  aidlc-rules/                the AI-DLC methodology — vendored from awslabs, do not edit
  aidlc/                      how things here were built — a record, not a backlog
  decisions/                  one file per decision made on purpose
tools/
  check                       the checks that gate a merge; CI runs this exact script
  dev                         start builder-mcp and its local browser console together
.github/workflows/
  pr-checks.yml               runs tools/check. No AWS calls, no credentials.
.mcp.json                   GitHub MCP server for Claude Code — needs one env var, see below
.env.example                template for the gitignored .env that tools/dev sources
```

Most directories have their own README explaining what goes in it. `docs/aidlc-rules/` is the
deliberate exception — see below for why it is left exactly as upstream ships it. `packages/`,
`docs/` and `tools/` have none; their conventions live in `CLAUDE.md`.

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
  └─ Terraform ......... one CodeBuild action per Azure/Entra module; plan, then apply
```

AWS resources are CloudFormation. Terraform exists only because CloudFormation cannot reach an
Entra tenant, and it **applies unattended** — a merge touching `blueprints/*/infra/azure/`
reaches the tenant with no human in the loop.

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

- Pull request required; direct pushes rejected
- **Zero approving reviews required** — you merge your own PR
- Only members of the `ai-dlc-workshop` GitHub team may merge
- The `validate` check must pass
- Force pushes and branch deletion blocked
- Repo admins can bypass (`enforce_admins` is off)

The one-approving-review rule was dropped during the workshop: requiring a second person meant
nobody could merge their own work, which stalled attendees. The trade is real — with zero
approvals, `validate` is the only automated gate between a branch and a deploy into the shared
account, and the `Terraform` stage applies to the Azure tenant unattended. Restore the review
requirement after the workshop.

Long-term the approval gate becomes an automated reviewer agent.

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

The stack-and-module registry check, `cfn-lint`, the `builder-mcp` test suite, and
`terraform fmt`/`validate`. Lint, validate and unit tests only — no AWS calls, no credentials, no
Terraform backend access, so they come back in about a minute.

Run them before you push:

```sh
tools/check
```

CI runs that exact script, so green locally means green on your PR.

**Two prerequisites: `uv` and `terraform`.** uv fetches Python, pyyaml, cfn-lint and the
`builder-mcp` test dependencies on demand at pinned versions, so there is nothing Python to install
globally and no venv to activate. Terraform is a single binary with no uv equivalent:

```sh
brew install uv                                    # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh    # everything else

brew install hashicorp/tap/terraform               # macOS
# other: https://developer.hashicorp.com/terraform/install
```

CI installs Terraform with `hashicorp/setup-terraform` — the one non-github-owned action the org
allowed-actions policy permits, which is why these checks can run there at all.

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
path goes there, self-contained with its own `pyproject.toml` and lockfile — including its
`Dockerfile`. `pipeline/codebuild.yml` builds
`docker build $CODEBUILD_SRC_DIR/${CONTAINER_CONTEXT:-.} --target $CONTAINER_TARGET`, so the Build
stage action names the component's directory as the context and its named target. Keep the two in
step with where the component lives: a stale `CONTAINER_CONTEXT` fails the build on a missing path
and says nothing about the move that caused it.

## The knowledge base, for the teams consuming it

`blueprints/knowledgebase` is deployed and queryable. Two identifiers are all a consumer needs, and
both are in SSM rather than a CloudFormation `Export`, so nothing couples your stack's lifecycle
to ours:

```sh
aws ssm get-parameter --name /aidlc/main/knowledgebase/knowledge-base-id     --query Parameter.Value --output text
aws ssm get-parameter --name /aidlc/main/knowledgebase/retrieval-policy-arn  --query Parameter.Value --output text
```

Attach that managed policy to your role instead of writing your own `bedrock:Retrieve` statement,
then call `bedrock-agent-runtime:Retrieve`. Two shapes to get right on a **managed** knowledge base,
both observed rather than assumed:

- retrieval takes `managedSearchConfiguration`; `vectorSearchConfiguration` is rejected outright;
- **`retrieve-and-generate` is not supported**, whatever your IAM says. Retrieve, then `Converse`
  with the chunks. The policy grants `Retrieve` only, so that limit shows up as a readable denial
  instead of a puzzling service error.

| | |
|---|---|
| Indexed today | One syllabus PDF from `aidlc-kb-ingestion-890349359349`. **One document is not a corpus** — expect mediocre relevance, and scores that don't track it. |
| Freshness | A merge re-ingests and re-verifies. Nothing else does: `EnableScheduledSync` exists and is off, and a scheduled sync cannot report its own result anyway. |
| SharePoint | **On.** The ECE 4960 handouts in `sites/kb` — 25 documents, rehearsed at zero failures before the flag flipped. Every team's merge now depends on the Entra consent, the per-site grant and an unexpired certificate; the platform team manages that side by hand. |
| Proof it works | A green `BlueprintDeploy` asserts the documents are indexed **and** answerable — the stack fails otherwise. `DocumentsIndexed` and `SmokeQueryResult` are stack outputs. |
| Costs while idle | Per-GB stored plus per-retrieve. It does not stop when the workshop ends, and no OpenSearch collection exists to add an hourly floor. |

Changing the corpus means `IngestionBucketName` plus a `SmokeQuery` the new corpus can answer, in
`pipeline/pipeline.yml`, `blueprints/knowledgebase/blueprint.yaml` **and** the template. If that
smoke query stops being answerable, every team's deploy goes red — the verifier is doing its job.
Details in `blueprints/knowledgebase/README.md`.

## Not here yet

The deploy path works, the Cornell Builder is written, and the Terraform stage and the managed
Bedrock Knowledge Base have both landed. Still to come, per the workshop spec: the
`course-chatbot` blueprint itself — `blueprints/course-chatbot/` has the Lambda handler and a
README of what's missing, but no template, no image target and no pipeline action, so it deploys
nothing — its Teams bot and Strands agent, and `observability/`. Each has a scaffolded directory
with a README saying what goes in it and how to wire it.

The Terraform stage exists but only reaches **Entra**. Managing Azure *resources* with `azurerm`
additionally needs an Azure subscription in the tenant and an Azure RBAC role assignment for the
service principal — a Global Administrator directory role grants neither.
