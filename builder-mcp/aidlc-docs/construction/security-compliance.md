# builder-mcp — Security Baseline Compliance Pass

Catch-up audit against the AI-DLC Security Baseline extension
(`aidlc-rules/aws-aidlc-rule-details/extensions/security/baseline/security-baseline.md`),
run 2026-08-03 after the code was written. Scope: `builder-mcp/src/builder_mcp/*.py`,
`builder-mcp/infra/builder-mcp.yml`, the builder-mcp additions to `pipeline/pipeline.yml`
(ArmContainerBuildProject, Build stage, BuilderMcpCloudFormation), the repo-root
`Dockerfile`, and `builder-mcp/deploy/verify.py`. Context: CLAUDE.md hard constraints
(public repo, **no secret scanning**, secrets only in Secrets Manager), SPEC.md C5,
PROJECT-KNOWLEDGE.md.

## Verdict

**NON-COMPLIANT — blocking findings present.** 10 blocking findings across 9 rules
(SECURITY-03, -05, -06, -08, -09, -10, -11, -14, -15), 9 advisory findings, 1 rule fully
compliant (SECURITY-13), 4 rules N/A (SECURITY-01, -02, -04, -07). Per the extension's
own blocking-finding behavior, the stage MUST NOT present "Continue to Next Stage" until
the blocking findings below are resolved, and each blocking finding MUST also be logged
in `aidlc-docs/audit.md` with rule ID and stage context (that logging is a required
follow-up of this pass; this document is the findings register).

The two findings to fix first: **F1** (workflow-file injection via `propose_change` =
pre-review code execution in GitHub Actions) and **F4** (no application logging at all,
which makes every other control unauditable).

## Remediation status (code-level pass, 2026-08-04)

Code-level remediation applied on branch `c/builder/tim`. Central additions:
`src/builder_mcp/validation.py` (path denylist, input caps, NetID pattern, `safe_error`)
and a `_guarded` decorator in `server.py` (per-tool logging + never-raise). Findings that
need infra changes or a mob/platform decision stay open below.

| # | Status | Detail |
|---|---|---|
| F1 | **Fixed (code)** | `validation.file_path_problem` refuses `.github/` (incl. workflows), `..`, leading `/`\|`\` , Windows-drive absolutes, and non-`[A-Za-z0-9._/-]` characters; enforced on every path `deployment_update` writes and on `deployment_create`'s shell files. `deployment_update` additionally allowlists target repos to the workshop repo and `<org>/deploy-*`. Org-level Actions policy on `deploy-*` repos and the GitHub App migration remain platform follow-ups. |
| F2 | **Open — superseded in part** | The Cognito-specific aspects (shared `BuilderClient` credential; client secret retrievable via `DescribeUserPoolClient`) are superseded by the Entra ID authorizer swap now in flight (separate agent owns it). Object-level authorization (verify caller vs `deployment.yaml` owner) still needs that identity to exist first — open. |
| F3 | **Fixed (code)** | `owner_netid` validated against `^[a-z]{2,4}[0-9]{1,5}$`; `title` ≤ 200, `description` ≤ 10000; `files` capped at 50 entries / 512 KB total; every path through the F1 denylist. |
| F4 | **Fixed (code)** | Stdlib logging, module-level loggers; one structured INFO line per tool call (tool, subject, dry_run, outcome incl. error class) via `_guarded`; details at DEBUG; secret-fetch failure now logs at WARNING (`config.py`). Configured only in `server.main()`, level from `BUILDER_MCP_LOG_LEVEL` (default INFO). No secrets or file contents logged. |
| F5 | **Fixed (code)** | `_guarded` guarantees no tool ever raises to the transport (C3). `catalog._load_remote`/`_load_local` raise a caller-safe `CatalogError` instead of a silent empty catalog or a naked `httpx` exception. `deployment_create`/`deployment_update`/`deployment_delete` execute paths report `completed_steps` + `cleanup` guidance on partial failure. |
| F6 | **Fixed (code)** | `validation.safe_error` used everywhere (incl. `aws_ops._friendly`): exception class + one-line summary, redacting tokens/bearer values, ARNs, 12-digit account ids, and URL query strings; full detail goes to the DEBUG log instead. |
| F7 | **Deferred** | Rate limiting / restart cap needs an infra + mob decision (token bucket vs AgentCore quota). |
| F8 | **Deferred** | Alarms, dashboards, log retention are infra-template work (reassigned with the infra freeze). |
| F9 | **Partially fixed** | Base image now pinned by digest (`sha256:531f855b…`, multi-arch index digest of `python3.13-bookworm-slim`, captured 2026-08-03) and the runtime stage runs as non-root `app` (also closes advisory F15). `pip-audit` in `tools/check` and SBOM generation remain open (CI/pipeline work). |
| F10 | **Reassigned** | `infra/builder-mcp.yml` is frozen for the Entra ID swap; the wildcard-exception comments move to the agent owning that template. |
| F16 | **Fixed (code)** | Branch is `propose/<uuid4-hex[:8]>` — no `PYTHONHASHSEED` dependence, no cross-title collisions by construction. |
| F17 | **Fixed (code)** | `GitHubOps` is a context manager with `close()`; all `server.py` call sites use `with GitHubOps(...)`. |
| F13 | **Partially fixed** | Remote catalog load now surfaces a clear narrative on non-200 (403 hints at the anonymous rate limit) instead of raising/going silently empty. Ref pinning and size caps remain open. |

Blocking findings not listed above (none) — all ten are Fixed, Partially fixed,
Deferred, Reassigned, or Superseded as annotated. Deferred/Reassigned/Open items block
per the extension until their owning track closes them.

## Findings

Severity: **BLOCKING** = a verification criterion of the rule is not met (the extension
makes every rule blocking by default). **Advisory** = defense-in-depth gap or documented,
time-boxed debt that does not fail a verification criterion outright.

| # | Rule | Severity | Location | Finding and remediation |
|---|---|---|---|---|
| F1 | SECURITY-08 (also -13 CI/CD integrity) | **BLOCKING** | `builder-mcp/src/builder_mcp/server.py:189-226` (esp. 202, 214-226); `builder-mcp/src/builder_mcp/github_ops.py:95-109` | `propose_change` accepts an arbitrary `repo` (any `org/name` if the string contains `/` — not even confined to `cu-aaii`) and an arbitrary `files` map, and pushes those files to a branch **in the target repo itself** with the server's org PAT. A file at `.github/workflows/*.yml` with an `on: push` trigger executes in GitHub Actions the moment `put_file` lands it on the branch — with that repo's Actions `GITHUB_TOKEN` — **before any human reviews the PR**. "Merge is the only deploy trigger" does not hold for Actions execution. Remediation: in `propose_change`, (a) allowlist target repos to `settings.workshop_repo_full` and `settings.github_org/deploy-*`; (b) reject any path matching `^\.github/` (and symlink-ish paths, see F3); (c) at the org level, disable Actions on `deploy-*` repos or require approval for all workflow runs; (d) accelerate the C5 GitHub App migration with fine-grained per-repo permissions excluding `workflows` scope. |
| F2 | SECURITY-08 | **BLOCKING** | `builder-mcp/src/builder_mcp/server.py:77-95, 171-185, 244-250`; `builder-mcp/infra/builder-mcp.yml:91-102` | No object-level or function-level authorization exists anywhere in the application. One shared Cognito client-credentials pair (`BuilderClient`) is the identity for **every** builder; any token holder can `create_deployment` with any `owner_netid` (caller-asserted, never verified), open PRs against anyone's deployment repo, and `restart_deployment` the shared pipeline. There is no per-builder attribution and no IDOR protection — ownership recorded in tags/PRs is whatever the caller typed. Remediation: short-term, verify `owner_netid` against a claim in the JWT (custom scope/client per builder) and check the caller against `deployment.yaml` `metadata.owner` before mutating a deployment; target state, the Entra ID authorizer (SPEC C5 P1) with NetID as the token subject. Record the token's client id in every PR body and log line (needs F4). |
| F3 | SECURITY-05 | **BLOCKING** | `builder-mcp/src/builder_mcp/server.py:60, 77-95 (owner_netid), 189-195 (title/description/files)`; `builder-mcp/src/builder_mcp/github_ops.py:45, 107` | Input validation is partial. `deployment_name` has a regex (good); everything else does not: `owner_netid` is unvalidated free text that flows into the org repo description, README, PR title/body, and pipeline `ParameterOverrides`; `title`/`description`/`query` have no max length; `files` has no cap on count, per-file size, or total payload; file **paths** are unvalidated and are interpolated into the GitHub API URL (`/repos/{repo}/contents/{path}`), so `..`/`%2e` sequences and `.github/` targets are accepted. Remediation: validate `owner_netid` against a NetID allowlist regex (e.g. `^[a-z]{2,3}[0-9]{1,4}$`), cap `title` ≤ 120 / `description` ≤ 5000 / `query` ≤ 500 chars, cap `files` at e.g. 20 entries / 100 KB each, and validate each path against `^[A-Za-z0-9._/-]+$` with `..` segments and a leading `.github/` rejected. |
| F4 | SECURITY-03 | **BLOCKING** | entire `builder-mcp/src/builder_mcp/` package (grep confirms zero `import logging`); `builder-mcp/src/builder_mcp/config.py:77-85` | No logging framework is configured anywhere: no logger at the entry point (`server.py:285-298`), no per-tool-call log, no correlation ID, no timestamp/level structure. `config._resolve_github_token` swallows every Secrets Manager failure silently (`except Exception: return None`), so the server degrades to read-only with no operator-visible signal. Security-relevant events (who created what deployment, who restarted the pipeline) leave no trace beyond GitHub artifacts. Remediation: configure stdlib `logging` with a JSON formatter to stdout in `main()` (AgentCore forwards stdout to the `/aws/bedrock-agentcore/*` log groups the role already permits); log every tool invocation with a generated request ID, tool name, caller client-id, and non-secret parameters; log the secret-fetch failure path at WARNING. Never log the token or file contents. |
| F5 | SECURITY-15 (also -09 error handling) | **BLOCKING** | `builder-mcp/src/builder_mcp/server.py:136-167 (create_deployment), 214-226 (propose_change)`; `builder-mcp/src/builder_mcp/github_ops.py:47, 81, 92, 108, 118` (`raise_for_status`); `builder-mcp/src/builder_mcp/catalog.py:89` | The execute (`dry_run=False`) paths have **no** error handling: any GitHub API failure raises `httpx.HTTPStatusError` straight out of the tool, violating the SPEC C3 error contract ("tools return `{"error": ...}`, never raise") and leaking the full API URL in the exception text. Worse, `create_deployment` is not atomic: if `put_file` or `create_pull` fails after `create_org_repo` succeeded, an orphaned org repo remains with no cleanup and no report of partial state. `catalog._load_remote` likewise raises through `blueprint_search`/`create_deployment` on any GitHub outage. Remediation: wrap each execute path in try/except returning `{"error": <generic>, "completed_steps": [...]}` so partial state is visible; catch in `load_catalog`; add a module-level guard (decorator) so no tool can ever propagate an exception to the transport. |
| F6 | SECURITY-09 | **BLOCKING** | `builder-mcp/src/builder_mcp/aws_ops.py:35-36`; `builder-mcp/src/builder_mcp/server.py:179` | Error narratives echo raw internals to the caller: `_friendly` returns `f"...{error.__class__.__name__}: {error}"` — boto exception text includes ARNs, the account ID, and internal resource names; `deployment_status` embeds the raw exception from the PR listing. Combined with F4 (nothing logged server-side) the current design *has* to leak to be debuggable. Remediation: return generic messages ("AWS call failed while describing the stack; the platform team can see request id X") and move the detail into server-side logs (F4). |
| F7 | SECURITY-11 | **BLOCKING** | `builder-mcp/infra/builder-mcp.yml:204-206` (`NetworkMode: PUBLIC`, no throttling resource anywhere); `builder-mcp/src/builder_mcp/server.py:244-250` | No rate limiting or throttling exists on the public MCP endpoint, and `restart_deployment` has no cap — a token holder (or a runaway agent loop) can hammer `StartPipelineExecution` on the **shared** pipeline, starving every other track's deploys. The 3-restart cap is acknowledged in BACKLOG but not implemented. Remediation: implement the restart cap now (count recent executions via `list_pipeline_executions` or a simple in-container token bucket keyed by tool); document AgentCore's built-in invocation quotas as the transport-level throttle, or front with a quota if none apply. |
| F8 | SECURITY-14 | **BLOCKING** | `builder-mcp/infra/builder-mcp.yml:142-150` (role creates its own log groups, no retention set anywhere); `pipeline/pipeline.yml:241-255` (`ArmContainerBuildLogs` has no `RetentionInDays`); no alarm/dashboard resource in either template | No alerting, no dashboards, no explicit retention. Runtime log groups are created ad hoc by the role (`logs:CreateLogGroup`) so no `RetentionInDays` is ever applied; there is no alarm on runtime errors, Cognito token failures, or authorization denials. (Credit: the role cannot delete logs — append-only holds.) Remediation: predeclare the `/aws/bedrock-agentcore/...` log group in `infra/builder-mcp.yml` with `RetentionInDays: 90` and drop `logs:CreateLogGroup` from the role; set `RetentionInDays: 90` on `ArmContainerBuildLogs`; add CloudWatch alarms on runtime 5xx/error metric and Cognito `ThrottleCount`/`FederationThrottle`, wired to the platform team's notification target. |
| F9 | SECURITY-10 | **BLOCKING** | `Dockerfile:8`; `tools/check:29-40`; `.github/workflows/pr-checks.yml`; `pipeline/codebuild.yml` | Supply chain gaps: (a) base image `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` is a mutable tag, not digest-pinned — the production image can silently change between builds; (b) no dependency vulnerability scanning step exists anywhere (`tools/check` runs only the stack registry and cfn-lint; ECR `ScanOnPush` covers the final image but not PR-time Python deps); (c) no SBOM is generated. `uv.lock` + `--frozen` are in place (good). Remediation: pin the base image by `@sha256:` digest; add `uvx pip-audit` (or `uv run --with pip-audit pip-audit`) against `builder-mcp/uv.lock` to `tools/check`; generate an SBOM (`syft` or `docker sbom`) in the ARM build and store it as a build artifact. |
| F10 | SECURITY-06 | **BLOCKING** (trivial fix) | `builder-mcp/infra/builder-mcp.yml:137-141` (`ecr:GetAuthorizationToken` on `*`), `165-169` (`tag:GetResources` on `*`) | Two wildcard-resource statements with **no documented exception**. Both are legitimately un-scopeable — neither API supports resource-level permissions — but the rule explicitly requires the exception documented, and `tag:GetResources` on `*` deserves the note: it lets the runtime enumerate the tags of **every resource in the shared account**, not just builder-mcp's, which is intentional (health_check inventory mirrors the Track E dashboard query) but is currently invisible to a reviewer. Remediation: add a template comment on each statement stating the API's lack of resource-level permission support and the accepted account-wide read scope; optionally add an `aws:ResourceTag` condition guard where the tag API honors it. |
| F11 | SECURITY-08 / SPEC C5 | Advisory | `builder-mcp/src/builder_mcp/config.py:64-85`; `builder-mcp/infra/builder-mcp.yml:40-44`; secret `aidlc/main/builder-mcp/github-token` | GitHub token blast radius: the credential is an org (in practice personal, per github_ops.py docstring "the presenter's") PAT — classic PATs are account-wide, so the runtime's effective GitHub reach is every repo the presenter can write, far beyond the C5 story. This is documented debt (D3, GitHub App at P1), so advisory rather than blocking — but it compounds F1/F2. Remediation: if App migration slips past the workshop, at minimum use a fine-grained PAT scoped to `cu-aaii` with contents+PR permissions only and no `workflows` permission, and set an expiry. |
| F12 | SECURITY-12 | Advisory | `builder-mcp/infra/builder-mcp.yml:91-102`; `builder-mcp/deploy/verify.py:28-31` | Who can mint tokens: anyone holding the one client id+secret, and — as verify.py itself demonstrates — anyone with `cognito-idp:DescribeUserPoolClient` in the AWS account can *retrieve* the secret and mint tokens. One shared credential means revocation is all-or-nothing and there is no per-builder audit trail (see F2). Remediation: one app client per builder (cheap in CFN or via admin API), treat the secret as workshop-scoped and rotate after; restrict `DescribeUserPoolClient` in human IAM policies. |
| F13 | SECURITY-10/-05 | Advisory | `builder-mcp/src/builder_mcp/catalog.py:83-100` | `_load_remote` fetches manifests from the GitHub contents API — unauthenticated when no token is configured. Supply-chain integrity is acceptable (TLS to api.github.com, default branch = the PR-gated tracked branch, `yaml.safe_load`), but: anonymous calls hit the 60 req/h/IP limit (availability: catalog goes dark mid-demo), there is no ref pinning (TOCTOU: catalog can change between `blueprint_search` and `create_deployment`), and no response size bound. Remediation: pin `ref=<settings.environment>` on both requests, surface a clear error on 403 rate-limit, cap manifest size (e.g. 256 KB). |
| F14 | SECURITY-06 | Advisory | `pipeline/pipeline.yml:68-80` (ContainerBuildRole), `257-300` (ArmContainerBuildProject reuses it) | The pre-existing `ContainerBuildRole` grants `ecr:PutImage`/`Initiate/Upload/CompleteLayerUpload` on Resource `*`; the builder-mcp Build stage is the **first thing to actually exercise it**, so the build can now push to any ECR repo in the account. Pre-existing reference-pipeline shape ("preserve the pipeline's mechanics"), hence advisory. Remediation: scope the push actions to `!GetAtt ContainerRepository.Arn`, leaving only `ecr:GetAuthorizationToken` on `*`. |
| F15 | SECURITY-09 | Advisory | `Dockerfile:8-27` | No `USER` directive — the MCP server runs as root inside the container. AgentCore's microVM isolation mitigates, but root + an HTTP-exposed process is unnecessary. Remediation: add a non-root user (`RUN useradd -m app` … `USER app`) after the `uv sync` layers. |
| F16 | SECURITY-15 | Advisory | `builder-mcp/src/builder_mcp/server.py:203` | `branch = f"propose/{abs(hash(title)) % 100000}"` — `hash()` is randomized per process (PYTHONHASHSEED), so the branch shown in the dry-run plan differs from the branch used at execute time if the (stateless, restartable) container recycles between calls, and collisions across titles yield an unhandled 422 from `create_branch`. Remediation: derive from a slugified title + UTC timestamp, or `hashlib.sha256(title).hexdigest()[:8]`. |
| F17 | SECURITY-15 | Advisory | `builder-mcp/src/builder_mcp/github_ops.py:34` | `httpx.Client` is created per `GitHubOps` and never closed — connection/file-handle leak on every tool call in a long-lived container. Remediation: use the client as a context manager per operation, or add `close()`/`__exit__` and call it from the tools. |
| F18 | SECURITY-06 | Advisory | `builder-mcp/infra/builder-mcp.yml:112-123` | Runtime role trust policy conditions on `aws:SourceAccount` only. Add `aws:SourceArn` (the runtime ARN pattern) to prevent any other AgentCore runtime in the same account assuming this role (confused deputy within the shared workshop account — relevant precisely because everyone deploys into one account). |
| F19 | SECURITY-07 | Advisory | `builder-mcp/infra/builder-mcp.yml:204-206` | `NetworkMode: PUBLIC` exposes the MCP endpoint to the internet, gated only by the JWT authorizer (single layer — see F7, F12). Acceptable for the workshop, but the justification lives in nobody's head but the template author's. Remediation: add a template comment justifying PUBLIC and noting the VPC/PrivateLink alternative for P1. |

## Compliant (checked and passed)

Auditable list of verification criteria that were checked and hold:

- **SECURITY-13 — Software and data integrity (fully compliant).** Only `yaml.safe_load` /
  `safe_dump` are used (`catalog.py:80,99`, `patching.py:128`) — no unsafe
  deserialization of untrusted input. The runtime image is deployed **by digest**
  (`pipeline/pipeline.yml:522` `#{BuilderMcpContainer.CONTAINER_DIGEST}`), so the running
  artifact is exactly what the merged commit built. Pipeline-definition changes are
  access-controlled: `pipeline.yml` edits deploy only via PR-gated merge with a mandatory
  second-person approval (branch protection; nobody can approve their own PR), giving
  author/approver separation of duties. No external CDN scripts exist (no SRI needed).
  Data-modification auditability exists at the Git layer (every mutation is a commit +
  PR) — the application-layer half of the audit trail is the F4 remediation.
- **SECURITY-12 — no-hardcoded-credentials clause.** No secret, token, or key appears in
  any audited source or template (checked all seven Python modules, both templates, the
  Dockerfile, verify.py). The GitHub token arrives via env or Secrets Manager by *name*
  (`config.py:64-85`, `infra/builder-mcp.yml:40-44`); the template comment correctly
  states the secret never appears in the repo — load-bearing given the public repo with
  secret scanning disabled. `verify.py` prints the endpoint and status lines, never the
  token or client secret.
- **SECURITY-06 — runtime role, scoped statements.** ECR image pulls scoped to the one
  shared repository ARN; logs scoped to `/aws/bedrock-agentcore/*`; CloudFormation reads
  scoped to `stack/${Application}-${Environment}*`; CodePipeline actions scoped to the
  one pipeline; `secretsmanager:GetSecretValue` scoped to the single token secret
  (`infra/builder-mcp.yml:129-174`). Only two writes exist
  (`StartPipelineExecution`, `RetryStageExecution`) — matching exactly what the code
  calls (`aws_ops.py:139-146`). Trust policy is service-scoped with a SourceAccount
  condition. (Exceptions: F10, F18.)
- **SECURITY-08 — transport authentication.** Every request to the runtime is
  JWT-validated server-side by the AgentCore `CustomJWTAuthorizer` against the Cognito
  issuer with `AllowedClients` pinned to the one app client
  (`infra/builder-mcp.yml:207-211`); scope `cornell-builder/invoke` is the only grant.
  Deny-by-default holds at the transport: no unauthenticated route exists. (The
  application-layer half is F2.)
- **SECURITY-05 — the validated subset.** `deployment_name` enforced against
  `^[a-z0-9][a-z0-9-]{0,28}[a-z0-9]$` (`patching.py:17`, `server.py:100-103`);
  required/enum/unknown-input checks against the manifest contract
  (`catalog.py:122-135`); `ParameterOverrides` built with `json.dumps`
  (`patching.py:32`) so values cannot break out of the JSON or the YAML block scalar; no
  SQL, no OS command construction anywhere in the package.
- **SECURITY-10 — the satisfied subset.** `builder-mcp/uv.lock` is committed and enforced
  with `uv sync --frozen` (`Dockerfile:14,18`); dependencies come from PyPI/ghcr official
  registries; CodeBuild images use pinned version tags
  (`amazonlinux2-aarch64-standard:3.0`); ECR `ScanOnPush: true` scans every pushed image
  (`pipeline/pipeline.yml:108-109`); the org allowed-actions policy confines CI to
  github-owned actions.
- **Governance invariants (SPEC C3/D4), verified in code.** `github_ops.py` contains no
  merge call and no push to any pipeline-tracked branch (`put_file` to `main` occurs only
  in the just-created deployment shell repo, which no pipeline tracks); `aws_ops.py`
  contains no CloudFormation Create/Update/Delete. Created deployment repos default to
  `visibility: private` (`github_ops.py:79`). Merge remains the only deploy trigger.

## N/A rules

Per the extension's compliance-summary requirement:

- **SECURITY-01 (Encryption at rest/in transit)** — N/A: builder-mcp is stateless and
  owns no data store; the stores it touches (Secrets Manager, CloudWatch Logs, ECR, the
  pipeline's artifact bucket) are platform-owned, AWS-default-encrypted at rest, and all
  client traffic (GitHub API, AWS APIs, MCP endpoint) is TLS.
- **SECURITY-02 (Access logging on network intermediaries)** — N/A: no load balancer, API
  gateway, or CDN resource is defined; ingress is the managed AgentCore endpoint
  (invocation auditing via CloudTrail is worth confirming with the platform team, but no
  in-scope resource carries an access-logging property).
- **SECURITY-04 (HTTP security headers)** — N/A: no HTML-serving endpoint exists; the
  server speaks MCP JSON only, consumed by MCP clients, not browsers.
- **SECURITY-07 (Restrictive network configuration)** — N/A as written: no security
  groups, NACLs, subnets, or route tables are defined in any audited template (the
  `NetworkMode: PUBLIC` posture is tracked as advisory F19).
- **SECURITY-12 (password/MFA/session/brute-force clauses)** — N/A: authentication is
  machine-to-machine client-credentials; the Cognito pool contains no human users, no
  passwords, no sessions (stateless transport). The applicable clause (no hardcoded
  credentials) is compliant; the shared-credential weakness is F12.

---
*Pass executed 2026-08-03 against branch `c/builder/tim` working tree. Findings without
remediation applied; blocking findings must also be appended to `aidlc-docs/audit.md`
per the extension's blocking-finding behavior.*
