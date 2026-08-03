# builder-mcp — Project Knowledge Base

Everything a future agent or teammate needs that is *not* derivable from the code. Written
2026-08-03 (workshop day 1) so no one has to rely on one chat session. Keyword-rich on
purpose — grep this file first.

Companion docs: [SPEC.md](../SPEC.md) (the contracts), [deploy/HANDOFF.md](../deploy/HANDOFF.md)
(deployment runbook), [aidlc-state.md](aidlc-state.md) (AI-DLC stage tracking),
[audit.md](audit.md) (verbatim decision inputs).

---

## 1. What this is, in one paragraph

Track A of Cornell's AI-DLC workshop: the **Cornell Builder MCP server** — the
conversational front door that lets a non-engineer get governed AWS infrastructure by
asking for it. It searches a blueprint catalog, creates deployments (new GitHub repo +
registration PR), and operates them. It can never deploy anything itself: **merge to the
tracked branch is the only deploy trigger**, and a human approval sits in front of every
merge.

## 2. Decision log (searchable: DECISION)

| # | Decision | Choice | Why / provenance |
|---|---|---|---|
| DECISION-01 | Blueprint distribution | Versioned module, referenced not copied; deployment repo is a thin shell | Proposal D1; forty-forks problem |
| DECISION-02 | Intent matching | Whole catalog in model context, server ranks but never filters | Proposal D2; revisit past ~75 blueprints |
| DECISION-03 | Git credentials | Server-side only; GitHub App at P1, org PAT in Secrets Manager this week | Proposal D3; mob P4 |
| DECISION-04 | Deploy trigger | Merge, and nothing else. No deploy tool exists | Proposal D4 |
| DECISION-05 | Created repo location | New repo in cu-aaii org **plus** registration PR to the workshop repo (Q1-A) | Mob 2026-08-03 |
| DECISION-06 | Transport | Streamable HTTP from day one; hosted on **Bedrock AgentCore Runtime** | Mob (Q2, then confirmed explicitly) |
| DECISION-07 | Tool scope | All six mob tools + `spec_export`, same day | Mob (Q3-D) |
| DECISION-08 | deployment_restart semantics | Re-run at current version (retry failed stage / fresh execution) — **assumed ⭐, Q4 never answered** | Flagged for mob confirmation |
| DECISION-09 | Playwright | Dropped from scope | Mob (Q5) |
| DECISION-10 | End-user auth | Blueprint parameters only; enforcement in the blueprint (tentative) | Mob (Q6-A "I think") |
| DECISION-11 | Guardrails | Bind at gate + pipeline, not in the MCP; MCP validates inputs for UX only (tentative) | Mob (Q7-A "I think") |
| DECISION-12 | Stack | Python, official MCP SDK (v2.0), uv toolchain | Mob (Q8-A) |
| DECISION-13 | Export | Spec exports for six audiences: coder, narrative, security, transfer, user, offboarding | Mob (Q9-A, purposes verbatim in audit.md) |
| DECISION-14 | blueprint.yaml | **FROZEN cross-team standard** — no substantive changes | User directive 2026-08-03 |
| DECISION-15 | Deployment executor | **Marty deploys from his account/system; this machine only verifies locally and pushes to GitHub** | User directive 2026-08-03 |
| DECISION-16 | Inbound auth (assumed ⭐) | ~~Cognito client-credentials today, Entra ID at P1~~ **superseded by DECISION-20** | agentcore-productionizing-questions.md |
| DECISION-17 | IaC debt | ~~deployed_by: manual~~ superseded by DECISION-18 | P5-⭐ |
| DECISION-18 | Deploy method | **Pipeline-native**: root `Dockerfile` target `builder-mcp` → ARM CodeBuild project → Build stage exports digest → BlueprintDeploy action deploys `infra/builder-mcp.yml` with it. `deployed_by: pipeline`. Merge deploys, same as every blueprint | User review 2026-08-03: "when you push to github… a webhook will go deploy its contents"; pipeline/README.md "Adding a container image build" |
| DECISION-19 | Tool naming + delete | **noun_verb naming standard** for the whole tool surface (`blueprint_search`, `deployment_create/read/update/restart/health/delete`, `spec_export`; future: `blueprint_create`, ...) and **`deployment_delete` commissioned**: governed deletion = deregistration PR removing the pipeline action, symmetric with creation — never an AWS delete API; the platform removes the stack after merge per its DeletionPolicy (SPEC C3 contract change) | Mob 2026-08-03 |
| DECISION-20 | Inbound auth (supersedes DECISION-16) | **Microsoft Entra ID client-credentials NOW**, Cognito removed from `infra/builder-mcp.yml`. App registration is an Azure resource, hand-created by Marty (no Terraform stage exists); tenant/client ids reach the stack via SSM parameters `/entra/builder-mcp/{tenant-id,client-id}` (the SsmCodeStarConnectionArn precedent); client secret in Secrets Manager `aidlc/main/builder-mcp/entra-client-secret`. Authorizer allows client id + audience `api://<client-id>`. Per-user NetID (auth-code flow) stays P1 (BACKLOG) | Marty via Tim, 2026-08-03 (Cornell is an M365 shop; Entra was the stated P1 end state, pulled forward) |

Open items for the mob: Q4 (DECISION-08), P1/P3/P6 in
[construction/agentcore-productionizing-questions.md](construction/agentcore-productionizing-questions.md)
(P2 answered 2026-08-03 — Entra ID, DECISION-20),
and the five decision asks at the end of
[versioning-releases-and-recovery-options.md](inception/requirements/versioning-releases-and-recovery-options.md).

## 3. Gotchas learned the hard way (searchable: GOTCHA)

- **GOTCHA-SDK**: MCP Python SDK 2.0 renamed things — server class is
  `mcp.server.mcpserver.MCPServer` (old `FastMCP` import kept as fallback in server.py);
  client is `streamable_http_client` (underscores) and yields **2** values, not 3;
  host/port/stateless go as kwargs to `run()`, not `mcp.settings`.
- **GOTCHA-ELICITATION**: `stateless_http=True` (required by AgentCore) has no
  back-channel → `elicitation/create` raises. Hence the dry_run-first pattern. Do not
  "add elicitation later" without checking the transport.
- **GOTCHA-MARKER**: `validate_stacks.py` detects CFN templates by *text-scanning* for the
  format-version marker string. Writing that string in a YAML comment (e.g. in a manifest)
  makes the validator think the file is an unregistered template. Same trap for any doc
  under a scanned directory with a `.yml`/`.yaml` extension.
- **GOTCHA-DUP-TEMPLATE**: `stacks.yml` rejects duplicate template paths → second
  deployment of a blueprint = pipeline.yml action only (see SPEC C6).
- **GOTCHA-SUB-STACKNAME**: existing pipeline actions write stack names as
  `!Sub '${Application}-${Environment}-x'`, so duplicate detection must match the action
  name, not the literal stack name (patching.py does both).
- **GOTCHA-SINGLETON**: hello-world's template hardcodes bucket name + deployment id →
  one deployment per app/env (`singleton: true` in its manifest). Real blueprints need a
  DeploymentName parameter.
- **GOTCHA-CHECK**: only ever run checks via `tools/check` (needs Git Bash on this
  machine: the `bash` command resolves to WSL and fails; the Bash tool works). On this
  Windows machine cfn-lint throws a pre-existing `E0003 ... glob.glob` on
  bootstrap/account-bootstrap.yml — environmental, passes in CI on Linux. Lint a single
  template with `uv run --with cfn-lint cfn-lint --region us-east-1 -- <path>` (the `--`
  is mandatory; `--region` is greedy).
- **GOTCHA-ACCESS**: `timothyfraser` has read-only on cu-aaii/ai-dlc-workshop → all work
  pushes to the fork `timothyfraser/ai-dlc-workshop` branch `builder` (force-with-lease
  after rebases). GitHub write tools in the server dry-run until an org-scoped credential
  exists.
- **GOTCHA-RUNTIME-NAME**: AgentCore runtime names take underscores, not hyphens
  (`aidlc_main_builder_mcp`).
- **GOTCHA-ARM**: the reference `ContainerBuildProject` is x86_64; AgentCore needs
  linux/arm64. Hence `ArmContainerBuildProject` (additive twin, `ARM_CONTAINER` /
  aarch64 image) — don't "simplify" the two projects into one without checking which
  architectures the catalog needs.
- **GOTCHA-ROOT-DOCKERFILE**: `codebuild.yml` runs `docker build $CODEBUILD_SRC_DIR
  --target $CONTAINER_TARGET` — repo-root context, root `Dockerfile`, named targets.
  A per-component Dockerfile in a subdirectory is invisible to it (that mistake was made
  and reverted on day 1). `.dockerignore` at root keeps the context small.
- **GOTCHA-DEPLOY-ROLE**: `cloudformation-deploy-role` (bootstrap) predates AgentCore —
  before first merge, confirm it may call `bedrock-agentcore:*`, else the BuilderMcp
  deploy action fails mid-pipeline. Since the Entra swap (DECISION-20) it no longer needs
  `cognito-idp:*`, but it **does** need `ssm:GetParameters` on `/entra/builder-mcp/*` to
  resolve the `AWS::SSM::Parameter::Value<String>` parameters at deploy time — and those
  two parameters must exist first or the deploy fails at parameter resolution.
- **GOTCHA-JWT-AUTHORIZER**: `CustomJWTAuthorizer` property names are `AllowedClients`
  (plural) but `AllowedAudience` (singular) — both arrays of String; `AllowedScopes` also
  exists. Source: AWS::BedrockAgentCore::Runtime CustomJWTAuthorizerConfiguration CFN
  reference. For Entra client-credentials tokens the `aud` claim is the Application ID
  URI (`api://<client-id>`), not the client id, so both fields are configured.
- **GOTCHA-UV-LOCK**: a running `uv run builder-mcp` holds `builder-mcp.exe` and blocks
  the next `uv sync` (os error 32) — stop the server before re-running uv.

## 4. Current state (as of last push)

- 28 tests green (`uv run pytest -q` in builder-mcp/), local HTTP smoke test green in
  both stateful and **stateless** modes, arm64 Docker image builds, template lints clean.
- Deployed: **nothing**. Deployment is Marty's, from GitHub (DECISION-15).
- Blocked on people: org write access for Tim; mob answers to open items above.

## 5. Glossary (searchable: TERM)

- **Blueprint**: versioned, governed infra module + manifest (SPEC C1). **Deployment**:
  an instance of one, pinned to a version. **Registration PR**: the pipeline.yml action
  PR that makes a deployment real. **The gate**: PR review + branch protection — the one
  governance chokepoint. **Track A/0/B–E**: workshop teams (see participant brief).
  **AI-DLC**: AWS's method (rules vendored at `aidlc-rules/`); phases Inception →
  Construction → Operations. **Mob**: the whole-room elaboration format; questions go to
  the mob as A/B/C docs with `[Answer]:` tags (see `question-format-guide.md` in the
  vendored rules).
