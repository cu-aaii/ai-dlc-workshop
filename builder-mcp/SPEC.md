# builder-mcp — Contract Specifications

The system's load-bearing agreements, numbered C1–C7. **A contract change is a cross-team
event**: propose it in a PR that names the contract number, and get agreement from every
consumer listed — never edit one silently. Code and tests implement these; where code and
this document disagree, this document wins and the code is the bug.

Related docs: [aidlc-docs/PROJECT-KNOWLEDGE.md](aidlc-docs/PROJECT-KNOWLEDGE.md) (why
things are the way they are), [deploy/HANDOFF.md](deploy/HANDOFF.md) (how to deploy),
[README.md](README.md) (how to run).

---

## C1 — Blueprint manifest (`blueprints/<name>/blueprint.yaml`) · **FROZEN**

**Consumers**: builder-mcp catalog, every blueprint author, Track E dashboard (cost),
review gate. **Status**: shared cross-team standard as of 2026-08-03 — *no substantive
changes without mob agreement*.

Reference instance: [`blueprints/hello-world/blueprint.yaml`](../blueprints/hello-world/blueprint.yaml).

| Key | Meaning |
|---|---|
| `apiVersion` | `builder.cornell.edu/v1` |
| `kind` | `Blueprint` |
| `metadata.name/version/maintainer/maturity` | identity; semver; `experimental\|supported\|deprecated` |
| `summary` | one paragraph, plain language — shown to builders |
| `matches` | phrases intent-matching ranks against (D2: whole catalog in context) |
| `inputs` | parameter contract: `{type, required, description, values?}`; `enum` type uses `values` |
| `template` | repo-relative CFN template path (registered in `pipeline/stacks.yml`) |
| `pipeline_parameters` | CodePipeline-resolved overrides, e.g. `SourceCommitId: "#{GitRepository.CommitId}"` |
| `singleton` | template hardcodes its identity → one deployment per app/env |
| `cost` | `baseline_monthly_usd`, `scales_with` — feeds pre-deploy cost display |
| `data_classification` | list; the gate blocks anything above it |
| `state` | stateful-resource declarations: `class: stateless\|derived\|authoritative` (see recovery options doc) |

Rules: a manifest is **not** a CloudFormation template and must never contain the CFN
format-version marker string, even in a comment — `validate_stacks.py` detects templates
by text scan. Manifest `metadata.version` stays in lockstep with the template's
`BlueprintVersion` default.

Note: the catalog's home moving to a private repo is an agreed future change (tracked in
BACKLOG.md, Catalog & search) that will change how consumers fetch manifests without
changing the manifest contract itself.

## C2 — Deployment shell (`deployment.yaml` in each deployment repo)

**Consumers**: builder-mcp (`create_deployment` writes it, `export_spec` reads it),
future upgrade-bot (P1). A deployment repo contains identity, not code (D1: reference,
never copy): `metadata.name/owner`, `blueprint.name/version/source` (pinned), `stack`,
`parameters`. Producer: `patching.deployment_repo_files()`.

## C3 — Tool surface (seven tools)

**Consumers**: every builder's Claude client, demo script. Names and semantics are the
API; renaming a tool is a contract change.

| Tool | Reads/Writes | Contract highlights |
|---|---|---|
| `blueprint_search(query)` | read | returns *every* blueprint ranked (never filters), each with full C1 contract |
| `create_deployment(blueprint, deployment_name, owner_netid, parameters?, dry_run=true)` | GitHub writes | dry_run first is mandatory UX; singleton blueprints force `deployment_name = blueprint name`; output = new repo + registration PR; **never deploys** |
| `deployment_status(deployment_name)` | read | chain view: open PRs → pipeline stages → stack status |
| `propose_change(repo, title, description, files, dry_run=true)` | GitHub writes | files map → branch → PR; never a direct push |
| `health_check(deployment_name)` | read | stack status + failure events + cornell-tag inventory audit |
| `restart_deployment(deployment_name, dry_run=true)` | 2 AWS writes | retry failed stage / re-run pipeline **at current version only** |
| `export_spec(deployment_name, blueprint, audience)` | read | audiences: `coder, narrative, security, transfer, user, offboarding` |

Error contract: tools return `{"error": ...}` narratives, never raise to the transport
(NFR7). Governance invariants (hold for every tool, forever): no merge, no push to a
tracked branch, no CloudFormation Create/Update/Delete — merge is the only deploy
trigger (D4). An agreed future guardrail caps `restart_deployment` at 3 restarts
(tracked in BACKLOG.md, Operations & guardrails).

## C4 — Transport & runtime

**Consumers**: AgentCore deployment, local dev, Claude clients, the pipeline Build stage.
MCP over **streamable HTTP**; container contract `0.0.0.0:8000`, path `/mcp`,
`linux/arm64`, **stateless** (`BUILDER_MCP_STATELESS=1`). Stateless ⇒ no MCP elicitation
⇒ the `dry_run` two-step is the confirm UX everywhere. Local dev may run stateful on
`127.0.0.1`; behavior must not differ beyond that. Reference: AWS devguide
`runtime-mcp.html`.

**Build & deploy path**: the image is a named target (`builder-mcp`) in the **repo-root
`Dockerfile`**, built by the pipeline's ARM CodeBuild project on merge and deployed **by
digest** into the stack (`#{BuilderMcpContainer.CONTAINER_DIGEST}`). No local builds, no
private ECR repo — images live in the shared `<app>-<env>` repository. Renaming the
Dockerfile target breaks the pipeline action: both are one contract.

## C5 — Credentials & auth

**Consumers**: platform security review, Marty's deploy system.

- **Inbound**: OAuth client-credentials (Cognito) per `infra/builder-mcp.yml`; JWT
  authorizer on the runtime; scope `cornell-builder/invoke`. Entra ID (NetID identity) is
  the P1 replacement. IAM SigV4 was rejected (puts AWS creds in builders' hands).
- **Outbound GitHub**: server-side token only — env `GITHUB_TOKEN` (local) or Secrets
  Manager secret named by `BUILDER_MCP_GITHUB_TOKEN_SECRET` (deployed; default
  `aidlc/main/builder-mcp/github-token`). No token ⇒ writes degrade to dry-run plans.
  GitHub App installation is the P1 target (D3). **The builder's client never holds any
  credential.**
- **Outbound AWS**: the runtime role in `infra/builder-mcp.yml` — read-mostly; the only
  writes are `codepipeline:StartPipelineExecution` and `RetryStageExecution`.

## C6 — Registration PR shape

**Consumers**: review-gate humans, `validate_stacks.py`, pipeline. A deployment
registers by **adding one action to the BlueprintDeploy stage** of
`pipeline/pipeline.yml` (text insertion before `Outputs:`, so diffs stay reviewable —
`patching.py`). Action name `<PascalCase(deployment)>CloudFormation`; stack name
`<application>-<environment>-<name>` (role-scoping requires it). `stacks.yml` gets a new
entry **only for a new template** — it rejects duplicate template paths, so re-deploying
an existing blueprint touches only `pipeline.yml`.

## C7 — Configuration surface

All env vars, defaults in [README.md](README.md#configuration-all-env-vars-all-optional).
Adding a var: document there + here; never make one required without a default (a bare
`uv run builder-mcp` must always start).
