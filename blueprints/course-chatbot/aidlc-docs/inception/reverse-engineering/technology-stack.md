# Technology Stack

## Programming Languages

| Language | Version | Usage |
| --- | --- | --- |
| YAML (CloudFormation) | `AWSTemplateFormatVersion: 2010-09-09` | The bulk of the repository. Four documents: `account-bootstrap.yml`, `pipeline.yml`, `hello-world.yml`, and `codebuild.yml` (a buildspec rather than a template). |
| Python | `>=3.11` (declared as `requires-python` in PEP 723 inline metadata) | One file: `pipeline/validate_stacks.py`. |
| Bash | POSIX-ish shell | One file: `tools/check`. |
| YAML (GitHub Actions) | — | One workflow: `.github/workflows/pr-checks.yml`. |
| Markdown | — | READMEs, `CLAUDE.md`, and the 34 vendored rule files. |

No compiled language, no TypeScript, no JavaScript, no Dockerfile.

## Frameworks

**None.** There is no web framework, no application framework, no test framework, and no
infrastructure framework such as CDK, SAM, Serverless Framework or Pulumi. Infrastructure is
raw CloudFormation YAML.

This is a deliberate simplicity, and it is worth noting before the design stages: adding a
framework is a real decision with real consequences for who can read and review the
repository, not a neutral convenience.

## Infrastructure

All AWS, region `us-east-1`. The intent is serverless-first, and in this repository **Lambda
means container images**.

### In use today

| Service | Purpose |
| --- | --- |
| **AWS CodePipeline** | Orchestrates the three-stage deploy path. One pipeline per tracked branch. |
| **AWS CodeConnections** | GitHub source integration. Connections are per-account, cannot be shared across accounts, and are created `PENDING` — a human must complete a browser handshake before the Source stage can read the repository. |
| **AWS CloudFormation** | Every deployment, including the pipeline's deployment of itself. |
| **AWS IAM** | `cloudformation-deploy-role` (AdministratorAccess, referenced by name from the pipeline), `BuildPipelineRole` (CloudFormation permissions scoped to `stack/${Application}-${Environment}*`), `ContainerBuildRole`. |
| **Amazon S3** | The versioned, SSE-encrypted `deployment-artifacts-${AWS::AccountId}-${AWS::Region}` bucket with public access blocked; plus the reference blueprint's own bucket. |
| **AWS Systems Manager Parameter Store** | The CodeConnections ARN at `/code-connections/${GitConnectionName}`, and the reference blueprint's deployed-commit marker. Note that `AWS::SSM::Parameter` takes `Tags` as a **map**, unlike every other resource here. |

### Defined but not yet invoked

| Service | Purpose |
| --- | --- |
| **Amazon ECR** | `ContainerRepository`, with `ScanOnPush` enabled and a lifecycle policy expiring untagged images after one day and retaining at most three `commit-` tagged images. |
| **AWS CodeBuild** | `ContainerBuildProject`, `PrivilegedMode: true`, buildspec `pipeline/codebuild.yml`. |
| **Amazon CloudWatch Logs** | `ContainerBuildLogs`. |

No stage invokes these because nothing needs an image yet. Wiring the first one is a Build
stage action plus a Dockerfile.

### Absent

Named explicitly because their absence shapes the Teams chatbot design.

- **No compute has ever been deployed.** No Lambda function, no ECS service, no EC2 instance.
- **No HTTPS ingress.** No API Gateway, no Application Load Balancer, no Lambda function URL,
  no CloudFront distribution. Nothing terminates TLS or accepts an inbound request. A Teams
  bot needs a public HTTPS messaging endpoint for Azure Bot Service to POST activities to.
- **No secret is consumed anywhere.** The policy is Secrets Manager only, but no stack reads a
  secret, so there is no worked example to copy.
- **No database.** No DynamoDB, no RDS, no ElastiCache. Persistent state is an S3 bucket, an
  SSM parameter, and CloudFormation stack state.
- **No networking.** No VPC, no subnets, no security groups. Every component is a regional
  service reached over public endpoints with IAM authorization.
- **No Terraform.** `CLAUDE.md` designates Terraform-from-CodeBuild as the mechanism for
  non-AWS (Azure/M365) resources and lists that stage under "deliberately not built". The
  Teams bot's identity chain lives entirely there.

## Build Tools

| Tool | Version | Purpose |
| --- | --- | --- |
| **`uv`** | Unpinned | The **only** prerequisite for `tools/check`. Runs `cfn-lint` and executes `validate_stacks.py` with its PEP 723 dependencies resolved on the fly. Removes any need for a lockfile, virtualenv or install step. |
| **PEP 723 inline script metadata** | — | Dependency declaration lives in a comment block at the top of `validate_stacks.py`. There is no `pyproject.toml`, no `requirements.txt`, and no lockfile. |
| **`tools/check`** | — | The single build/test entry point, identical locally and in CI. |
| **GitHub Actions** | — | Runs `tools/check` per pull request. The org allowed-actions policy permits only github-owned actions plus `hashicorp/setup-terraform@*`; any other `uses:` fails the entire run as `startup_failure` with no job logs, which reads like a broken workflow file. Install tools via `pip`/`run:` instead of reaching for a marketplace action. |
| **CodeBuild buildspec** | `pipeline/codebuild.yml` | Container image builds. Not yet invoked. |

## Testing Tools

| Tool | Version | Purpose |
| --- | --- | --- |
| **`cfn-lint`** | Unpinned; resolved by `uv` at invocation | Lints every CloudFormation template. **Gotcha**: `--region` takes `nargs='+'`, so `cfn-lint --region us-east-1 <paths>` parses the template paths as region names, lints nothing, and exits 0 — a silent pass. A literal `--` before the paths is mandatory; `tools/check` handles it. |
| **`pipeline/validate_stacks.py`** | — | Reconciles the template registry against the filesystem and against `pipeline.yml` in both directions. |

**No unit test framework** — no pytest, no unittest suite, no jest. **No integration or
end-to-end tests.** **No coverage tooling.** **No general-purpose linter or formatter** — no
ruff, black, flake8, mypy, shellcheck, yamllint, or pre-commit configuration. Validation is
entirely static and entirely about CloudFormation.

## External Dependencies (build time only)

| Dependency | Version | Source | Purpose |
| --- | --- | --- | --- |
| `cfn-lint` | Unpinned | PyPI, via `uv` | Template linting. |
| `pyyaml` | Unpinned | PyPI, declared in inline metadata | Parsing `pipeline/stacks.yml`. The only third-party import in the repository. |

Nothing is vendored, pinned, or lockfile-managed. Both resolve to whatever is current at
invocation, which means CI is reproducible only to the extent that upstream is stable.

## Technologies Required By The Teams Chatbot But Absent Here

From the research documents in `docs/teams-chatbot-docs/`. Every item is new to this
repository — none has an existing pattern to copy.

| Technology | Role | Notes |
| --- | --- | --- |
| **Microsoft Entra ID app registration** | Bot identity: application ID plus client secret, or a user-assigned managed identity | Any Cornell tenant member can create one — `allowedToCreateApps: true` is confirmed in both the Cornell and dev tenants. Requires no admin unless the bot calls Microsoft Graph. |
| **Azure Bot Service** (`Microsoft.BotService/botServices`) | Registers the bot and routes activities to its messaging endpoint | Requires **Azure Contributor on the resource group** — an Azure RBAC role, distinct from any Entra or Teams role. Multi-tenant bot creation is unavailable after 31 July 2025; single-tenant or user-assigned managed identity is required. |
| **`MsTeamsChannel`** | Connects the bot to Teams | Part of the Azure Bot Service resource. |
| **Teams app manifest** (Developer Portal) | Declares the app and its bot to Teams | Any tenant member with a Teams license can author one. Manifest v1.25 requires top-level `"supportsChannelFeatures": "tier1"` when `team` scope is used — the portal GUI does not expose it and the portal validator wrongly rejects it inside the `bots` object. The Basic-information "Application (client) ID" field maps to `webApplicationInfo.id` (single sign-on) and must be left blank, or the Teams install fails silently. |
| **Bot Framework Activity protocol** | The wire format | JSON POSTed over HTTPS. The endpoint must return `200 OK` quickly or Teams retries. Inbound JWTs must be validated: RS256 against the JWKS at `https://login.botframework.com/v1/.well-known/keys`, `iss` of `https://api.botframework.com`, `aud` equal to the bot client ID, `exp`/`nbf` within five minutes, and the `serviceurl` claim (lowercase `u`) matching the body's `serviceUrl`. Outbound calls use the `client_credentials` grant with `scope: https://api.botframework.com/.default`. |
| **Resource-specific consent** (`ChannelMessage.Read.Group`) | Thread replies without an `@mention` | Declared in the manifest via `webApplicationInfo` with `resource: "https://AnyString"` plus `authorization.permissions.resourceSpecific`. Consented by a team owner at install; needs no Entra admin consent; **requires reinstalling the app** in the team. |
| **Microsoft Graph change notifications** | The alternative to resource-specific consent | Maximum subscription lifetime 4,320 minutes (three days); `lifecycleNotificationUrl` required beyond one hour; a synchronous `validationToken` echo within ten seconds; optionally an RSA certificate for `includeResourceData: true`. The research recommends resource-specific consent with Bot Framework delivery instead. |
| **Microsoft 365 Agents SDK** | Successor to Bot Framework SDK v4 | v4 support ended 31 December 2025. `dev.botframework.com` is legacy; Azure Bot Service is the supported path. |
| **Terraform** | The designated mechanism for the Azure/Entra half | No `.tf` file and no Terraform pipeline stage exist. `hashicorp/setup-terraform@*` is pre-approved in the org allowed-actions policy, which suggests this was anticipated. |
| **n8n** | The prototype backend actually used in the research | Self-hosted, holding credentials in its own store. Conflicts with the repository's hard constraints (AWS serverless, CloudFormation via CodePipeline, secrets only in Secrets Manager). Whether it is the target, a bridge, or discarded is a requirements decision, not an assumption. |
