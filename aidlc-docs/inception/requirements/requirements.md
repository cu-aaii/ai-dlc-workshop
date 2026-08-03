# Requirements — Microsoft Teams Chatbot Blueprint (`teams-bot`)

**Generated**: 2026-08-04
**Stage**: INCEPTION - Requirements Analysis
**Depth**: Comprehensive
**Extensions active**: Security Baseline

---

## Intent Analysis

| | |
| --- | --- |
| **User request** | "using the AI DLC start inception for Teams chatbot use information found here: `docs/teams-chatbot-docs`" |
| **Request type** | New Feature — a new blueprint. The n8n prototype is discarded, so no migration. |
| **Scope estimate** | **Cross-system** — AWS, Microsoft Entra ID, Azure Bot Service, Microsoft Teams, and Cornell's LiteLLM gateway |
| **Complexity estimate** | **Complex** |
| **Project type** | Brownfield — an existing, working deploy path gains its first compute-bearing blueprint |

**What makes this complex is not the bot.** It is that this blueprint is the first thing in the repository
to require public HTTPS ingress, deployed compute, a container image, a runtime secret, a non-AWS identity
chain, and an outbound dependency — each a first, in a repository whose `main` branch deploys to a shared
AWS account.

---

## 1. Product Definition

**FR-1. The blueprint is a template, not a bot.** `teams-bot` deploys a *configurable* Teams chatbot. What
any given bot does is determined by parameter values supplied at deployment time, not by this blueprint's
code.

**FR-2. Configuration arrives as CloudFormation parameters.** The `builder-mcp` keystone selects the
blueprint and writes parameter values into a deployment repository; that repository's pipeline deploys the
stack. The MCP is **never in the request path**. The bot's behaviour is therefore a reviewable file in git.

**FR-3. Capability scope is Tier A** — prompt-configured. The parameter surface is:

| Parameter | Purpose |
| --- | --- |
| `SystemPrompt` (or `SystemPromptS3Key`) | The bot's instructions and persona |
| `ModelId` | A model from the LiteLLM gateway catalogue |
| `GreetingText` | Sent on `conversationUpdate` when a human joins |
| `TeamsScopes` | Which conversation scopes are enabled |
| `Owner`, `DeploymentId` | Feed the mandatory tags |

**FR-3a.** `SystemPrompt` values may exceed the CloudFormation 4096-character parameter limit. The blueprint
MUST support supplying the prompt via an S3 object key as an alternative.

**FR-4. Tier B (retrieval) is designed for but not built.** The parameter surface MUST accommodate a future
`KnowledgeBaseId` without redesign. Tier B is a stretch goal, contingent on the Knowledge Base team
producing a knowledge base within the workshop.

**FR-5. Naming.** Blueprint name `teams-bot`; stack name `aidlc-main-teams-bot`; template at
`blueprints/teams-bot/infra/teams-bot.yml`.

---

## 2. Inbound Path — Receiving Activities

**FR-6. Public HTTPS endpoint.** A **Lambda function URL** with `AuthType: NONE`, using the AWS-provided
address. No custom domain, no ACM certificate.

**FR-7. URL stability.** The function's `FunctionName` MUST be deterministic so CloudFormation never
replaces the function, because replacement changes the URL. The URL MUST be a **stack output**, not a value
transcribed by a human.

**FR-7a. REVISED 2026-08-04 — the manual endpoint update is not necessary.** This requirement previously
accepted that recreating the stack meant a human editing the messaging endpoint in Azure. Research in
`docs/teams-chatbot-docs/Entra CLI Automation - Research 2026-08-03.md` establishes that
`az bot update --name <bot> --resource-group <rg> --endpoint <url>` is **fully automatable with a service
principal**, so a post-deploy step SHOULD read the function URL from the stack output and push it to the bot
resource. The stack output requirement above now has a programmatic consumer rather than a human one, and the
accepted click-ops concession is withdrawn.

**FR-8. Inbound JWT validation.** Every inbound request MUST be validated before any action is taken:

| Check | Requirement |
| --- | --- |
| Signature | RS256, verified against `https://login.botframework.com/v1/.well-known/keys` |
| Algorithm | **Pinned to RS256.** `header.alg` MUST NOT be trusted |
| `iss` | Equals `https://api.botframework.com` |
| `aud` | Equals the bot's client ID, supplied as configuration — **never literal in code** |
| `exp` / `nbf` | Within a 300-second skew tolerance |
| **`serviceurl`** | **Lowercase `u`.** MUST equal the normalised `body.serviceUrl`. **Absence of the claim is a FAILURE, not a pass.** |

**FR-8a.** The `serviceurl` check MUST have a negative test proving a mismatched value is rejected. This
check was present-but-non-functional in the prototype — the code read `payload.serviceUrl` (camelCase),
which is always `undefined`, and a `&&` guard turned the check into a silent skip. It is the control that
prevents an attacker with a valid token redirecting the bot's replies.

**FR-9. Acknowledge before working.** The endpoint MUST return `200 OK` before performing any work. The
budget is **10–15 seconds depending on channel**; overrun surfaces `504:GatewayTimeout` to the user.

**FR-10. Never return a non-2xx on authentication failure.** A failed validation MUST result in `200 OK`
with no action taken. Returning 4xx causes Azure Bot Service to retry a request that can never succeed.

**FR-11. Idempotency.** Handling MUST be idempotent on the inbound activity `id`, so a retried activity
cannot produce a duplicate reply.

**FR-12. Activity type handling.** The handler MUST dispatch on `body.type` and MUST tolerate activities
with no `text` field:

- `message` — the conversational path
- `conversationUpdate` — greeting/farewell. `membersAdded` and `membersRemoved` MUST be filtered on the
  `28:` bot-ID prefix, or the bot greets itself on install
- `installationUpdate` — accepted and ignored

**FR-13. Both conversation ID formats.** Personal (`a:xxx`) and channel/group (`19:xxx@thread.tacv2`) MUST
both be handled.

**FR-14. `serviceUrl` normalisation.** The base URL MUST be normalised once — trailing slash stripped, then
joined with an explicit `/` — and the same normalised value used for both the `serviceurl` claim comparison
and reply URL construction, so the two cannot disagree. The prototype relied on an undocumented trailing
slash.

**FR-15. JWKS caching.** The key set MUST be cached rather than fetched per request, with refresh triggered
by a `kid` miss rather than by timer alone.

---

## 3. Outbound Path — Replying

**FR-16. Delivery seam.** The agent MUST hand its answer to a single delivery function that dispatches on
`conversation.conversationType`. The agent MUST NOT call delivery APIs directly. The two delivery patterns
differ in shape — many cumulative updates versus one final message — so this seam is what makes the second
path an addition rather than a rewrite.

**FR-17. Personal chat — response streaming.** Deliver via Teams response streaming:

- an **informative** update first (progress bar, ≤1 KB / 1000 characters), then progressive text
- content MUST be **cumulative**, not deltas: `"A brown"` → `"A brown fox"` → …
- `entities.type` is `streamInfo`; `streamId` comes from the first response (`201 Created`)
- `streamSequence` starts at 1 and increases monotonically, and **MUST NOT be set on the final message**
- final message uses `type: "message"` with `streamType: "final"`
- rate limit **1 request/second**; buffer model tokens for **1.5–2 seconds**
- calls MUST be sequential — await success before the next
- attachments, AI labels, feedback buttons and sensitivity labels are available **only on the final message**

**FR-18. Group chat and channel — acknowledge, typing indicator, single reply.** Streaming is unavailable
outside one-on-one chats, so these scopes receive a typing indicator followed by one complete reply.

**FR-19. Reply targets.** Reply-to-activity is `{serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}`;
a new activity omits the trailing `activityId`.

**FR-20. Outbound authentication.** `client_credentials` grant against the single-tenant Entra app, scope
`https://api.botframework.com/.default`. Tokens MUST be cached and reused until near expiry.

---

## 4. Agent and Model Access

**FR-21. AgentCore Runtime is mandated.** The agent runs on `AWS::BedrockAgentCore::Runtime` with
`AWS::BedrockAgentCore::RuntimeEndpoint`. Invoked with **SigV4 from the Lambda, in-account** — not exposed
to Azure Bot Service directly, because AgentCore's `CUSTOM_JWT` authorizer cannot perform the `serviceurl`
correlation in FR-8.

**FR-22. Container contract.** ARM64; port **8080** bound to `0.0.0.0`; `GET /ping` returning
`{"status": "Healthy"}`; `POST /invocations`. FastAPI plus uvicorn, with `opentelemetry-instrument` wrapping
the entrypoint to enable AgentCore Observability.

**FR-23. All model traffic routes through the LiteLLM gateway** at `https://api.ai.it.cornell.edu`. This is
a hard constraint: it is how Cornell permits medium-risk data, in both directions. No direct Bedrock
inference.

**FR-23a.** The gateway API key MUST be a **service key issued for this bot**, never a person's key, and
MUST be read from Secrets Manager at runtime.

**FR-24. Conversation state** via `AWS::BedrockAgentCore::Memory`. Each AgentCore session runs in a
dedicated microVM for up to 8 hours, giving per-user isolation by construction.

**FR-25. Retrieval (Tier B, deferred).** If enabled, the blueprint MUST call **`Retrieve`** on the Knowledge
Base team's managed knowledge base — **not `AgenticRetrieveStream`**, which makes multiple Bedrock
foundation-model calls and would place generative inference outside the gateway. (`RetrieveAndGenerate` is
unavailable for managed knowledge bases.) The blueprint MUST NOT access the knowledge base's S3 bucket
directly; ingestion belongs to their blueprint. Retrieval queries are capped at 10,000 characters, so any
concatenation of history MUST be truncated deliberately.

---

## 5. Deployment and Repository Requirements

**FR-26. Container build stage.** `pipeline/pipeline.yml` MUST gain a `Build` stage between
`PipelineDeploy` and `BlueprintDeploy`, invoking the existing `ContainerBuildProject`, namespaced so its
exported variable is referenceable. It MUST supply `CONTAINER_TARGET` and `DATE_TAG`
(`#{GitRepository.AuthorDate}`), neither of which the buildspec provides itself.

**FR-27. Build architecture.** `ContainerBuildProject` MUST change from `Type: 'LINUX_CONTAINER'` with
`aws/codebuild/amazonlinux2-x86_64-standard:4.0` to an **ARM container type with an aarch64 image**, because
AgentCore requires ARM64. Cross-building with buildx/QEMU is rejected as too slow.

**FR-28. Digest pinning.** The image MUST be referenced by the `CONTAINER_DIGEST` immutable digest
(`<repo-uri>@sha256:…`) passed via `ParameterOverrides`, never by a mutable tag.

**FR-29. Registration in both places.** The template MUST be registered in `pipeline/stacks.yml` **and**
have a matching action in `pipeline/pipeline.yml`. `validate_stacks.py` fails the build in both directions.

**FR-30. All four tags on every resource** — `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. Observed convention: `cornell:deployment-id` is the
stack name. `AWS::SSM::Parameter` takes `Tags` as a **map**, unlike every other resource.

**FR-31. Every parameter passed explicitly from the pipeline.** Template defaults exist only so a stack can
be hand-deployed for debugging.

**FR-32. Delivery mechanism.** One PR to `main`, reviewed by Marty. No parallel environment. The Build stage
MUST be called out explicitly in the PR description, since another team may add one concurrently.

**FR-33.** `tools/check` MUST pass before the PR is opened.

---

## 6. Non-Functional Requirements

**NFR-1. Region** `us-east-1`. **NFR-2.** CloudFormation only — no CDK, SAM or Terraform for AWS resources.
**NFR-3.** Serverless; Lambda means container images.

**NFR-4. Latency.** No SLA. Streaming removes the latency constraint, so model choice is a quality decision
rather than a speed one. First visible response SHOULD appear within roughly a second via the informative
update.

**NFR-5. Availability.** No SLA for v1.

**NFR-6. Scale.** Workshop scale — tens of users. Teams rate limits per thread and globally per app per
tenant apply, and streaming's 1/second cap consumes part of that budget.

**NFR-7. Cold starts.** Acceptable, because streaming decouples them from the acknowledgement deadline. The
container image SHOULD be kept small.

**NFR-8. Network.** Public egress; no VPC. Requires reachability to `login.botframework.com`,
`login.microsoftonline.com`, `*.smba.trafficmanager.net`, and `api.ai.it.cornell.edu`. **This assumption is
unconfirmed** — see §8.

**NFR-9. Portability.** The blueprint MUST deploy identically by hand and by pipeline.

---

## 7. Security Compliance — Security Baseline Extension

Evaluated against the artifacts produced at this stage (requirements). Each rule is satisfied by a
requirement above, marked N/A, or satisfied with a documented exception.

| Rule | Status | Basis |
| --- | --- | --- |
| **SECURITY-01** Encryption at rest/transit | **Compliant** | Secrets Manager and AgentCore Memory are encrypted by default. All external calls are HTTPS/TLS 1.2+. Any store this blueprint creates MUST declare encryption. |
| **SECURITY-02** Access logging on intermediaries | **Compliant with compensating control** | A Lambda function URL has no separate access log, unlike API Gateway. **REQUIREMENT: the handler MUST log every inbound request** — timestamp, correlation ID, activity type, conversation type, validation outcome — as the compensating control. Documented exception to the preference for a gateway. |
| **SECURITY-03** Application-level logging | **Compliant** | Structured logging to CloudWatch, with timestamp, correlation/request ID, level and message. `PYTHONUNBUFFERED=1` so logs stream. **No secrets, tokens or message bodies logged by default.** |
| **SECURITY-04** HTTP security headers | **N/A** | No HTML is served. The endpoint returns status codes and JSON to a service client. |
| **SECURITY-05** Input validation | **Compliant** | FR-8 (JWT), FR-12 (type dispatch, absent `text`), FR-25 (query length cap). **REQUIREMENT: an explicit request body size limit and schema validation of the Activity before use.** |
| **SECURITY-06** Least privilege | **Compliant** | **REQUIREMENT: no wildcard actions or resources.** Scope to specific ARNs — `bedrock-agentcore:InvokeAgentRuntime` on the runtime, `secretsmanager:GetSecretValue` on the named secret, `Retrieve` on the knowledge base. Read and write separated. Inherited exception noted: the pre-existing `cloudformation-deploy-role` holds `AdministratorAccess`, which is bootstrap scope, not this blueprint's. |
| **SECURITY-07** Restrictive network config | **Compliant with documented exception** | No VPC, no security groups. The public function URL is required by design — Azure Bot Service must reach it and its source addresses are not fixed. This is the rule's own public-facing 443 exception. Authorisation is enforced at the application layer per FR-8. |
| **SECURITY-08** Application-level access control | **Compliant** | Deny by default; token validated server-side on **every** request for signature, expiry, audience and issuer, plus the Bot Framework `serviceurl` correlation. CORS N/A — no browser origin. |
| **SECURITY-09** Hardening | **Compliant** | No default credentials; no secret in any file; error responses carry no internal detail (a bare `200`); base image current and supported. |
| **SECURITY-10** Supply chain | **Compliant — and this is new work** | **REQUIREMENT: a committed `uv.lock`.** AgentCore's `uv sync --frozen` pattern requires it, and the repository currently pins nothing (Reverse Engineering technical debt item 4 — this requirement closes it). **No `latest` or unpinned base image tags.** A dependency vulnerability scanning step MUST be added or documented. An SBOM SHOULD be produced. |
| **SECURITY-11** Secure design | **Compliant with a noted limitation** | JWT validation MUST live in a dedicated module, not be scattered. Defense in depth: validation plus authorisation plus TLS. **Rate limiting is a genuine gap** — a Lambda function URL has no built-in throttling. **REQUIREMENT: set reserved concurrency as a blast-radius control**, and record that this bounds cost and impact rather than preventing abuse. Misuse case addressed: forged activity with a valid token and attacker-controlled `serviceUrl` (FR-8). |
| **SECURITY-12** Authentication and credentials | **Largely N/A; the applicable part is compliant** | This blueprint has no user authentication of its own — identity comes from Teams. Password policy, hashing, MFA and session cookies are N/A. **The applicable clause — no hardcoded credentials — is mandated absolutely.** The Entra client secret and gateway key live only in Secrets Manager. |
| **SECURITY-13** Integrity verification | **Compliant** | Untrusted JSON parsed safely with schema validation, never deserialised into arbitrary types. **Container image pinned by digest (FR-28).** CI/CD integrity: `main` is PR-only with one human approval and nobody may approve their own PR. SRI N/A. |
| **SECURITY-14** Alerting and monitoring | **Compliant** | **REQUIREMENT: CloudWatch log retention of at least 90 days** on every log group this blueprint creates. Alerting on repeated JWT validation failures. The execution role MUST NOT have permission to delete its own log groups or streams. |
| **SECURITY-15** Exception handling and fail-safe defaults | **Compliant** | Every external call (JWKS, Entra, gateway, AgentCore, Bot Framework) MUST have explicit error handling. **Fail closed** — FR-8's absent-claim-is-failure rule is exactly this, and the prototype's bug was a fail-open. A global error handler MUST return `200` with no detail while logging the failure. |

**No blocking security findings.** Three items are compliant by way of a compensating control or documented
exception rather than direct satisfaction — SECURITY-02, SECURITY-07 and SECURITY-11 — and each carries an
explicit requirement above. They are called out because they follow from choosing a Lambda function URL over
API Gateway, and are worth conscious acceptance rather than silent inheritance.

---

## 8. Assumptions, Open Dependencies and Risks

**Assumptions on record:**

| # | Assumption | If wrong |
| --- | --- | --- |
| A-1 | Public egress; no VPC required | A VPC adds subnets, NAT with standing cost, security groups, endpoints — roughly doubles the template |
| A-2 | ~~The LiteLLM gateway is reachable from an AWS account~~ | **CONFIRMED 2026-08-04 by the user. No longer an assumption.** |
| A-3 | Demo configuration values are chosen at deploy time | None — they are parameters |

**Open dependencies:**

| # | Item | Owner | Blocks |
| --- | --- | --- | --- |
| ~~D-1~~ | ~~Gateway reachable from AWS?~~ | — | **CLOSED 2026-08-04 — confirmed reachable. Nothing blocked.** |
| D-2 | A service key for the bot, scoped for chat | Gateway operator | Deployment |
| D-3 | **Tagging guidance document** | The user | Q19 is deferred pending it; the four tags stand meanwhile |
| D-4 | `KnowledgeBaseId` and timeline | Knowledge Base team | Tier B only |
| D-5 | Does another team also need the Build stage? | Marty | Merge conflict risk |
| D-6 | VPC requirement; cost guardrails | Dan Klinger | Confirms A-1 |

### A-2 investigated 2026-08-04 — network findings

Checked read-only from this machine. No AWS resources touched.

| Check | Result |
| --- | --- |
| Public DNS (Google DoH, `Status: 0`) | **Resolves publicly.** No split-horizon or internal-only DNS |
| CNAME chain | `api.ai.it.cornell.edu` → `litellm-production.lcmain.aaii.cucloud.net` |
| A records | `18.215.4.226`, `98.88.164.16` — two addresses, consistent with a load balancer |
| IP ownership (AWS published ranges) | **Both are AWS `us-east-1`** — prefixes `18.208.0.0/13` and `98.88.0.0/13`, service `EC2` |
| Unauthenticated request | **`HTTP/2 401`**, `server: uvicorn` |

**What this establishes:**

- **No VPN, Direct Connect or private networking is required.** The hostname resolves on public
  resolvers to public addresses. This was the failure mode that would have forced a VPC and invalidated
  NFR-8; it is ruled out.
- **The gateway is itself hosted in AWS `us-east-1`** — the same region as the workshop account. Traffic
  would stay inside AWS's network, so latency should be *better* than from campus, not worse.
- **The full path completes to the application layer.** A `401` rather than a timeout or connection reset
  means TCP, TLS and HTTP all succeeded and the service answered — it declined only because no key was
  presented. There is no network-layer block on this source.

**CONFIRMED 2026-08-04 by the user: the gateway is reachable from AWS. Treated as settled — no further
verification required, and no allowlist request needed.**

The findings above are retained because two of them remain useful design inputs regardless: the gateway
runs in **AWS `us-east-1`**, the same region as the workshop account, so calls stay inside AWS's network;
and the endpoint is plain public HTTPS on a resolvable name, so **NFR-8 (public egress, no VPC) stands
unqualified.**

**Risks:**

| # | Risk | Mitigation |
| --- | --- | --- |
| R-1 | The container build path has **never executed** — ECR holds zero images and the digest contract is unproven | Prove it with a trivial container before wiring the real agent |
| R-2 | `pipeline.yml` is high-contention and **self-deploying**; a bad merge can leave the pipeline unable to deploy its own fix, and the recovery path is undocumented | Review; someone should know the manual deployment procedure |
| R-3 | Entra client secrets expire | Rotation out of scope for v1; expiry tracked by a person. **A certificate instead of a secret would remove this risk entirely** — cost is that `TokenProvider` must sign a client assertion rather than send a secret. Worth an explicit decision at Infrastructure Design rather than defaulting to a secret because that is what the prototype used. |
| R-4 | Four live credentials remain exposed in the working tree and one config file | Rotate; gitignore `.mcp.json`; scrub the research document |
| R-5 | AgentCore JWT inbound auth writes claims including Subject to CloudTrail | Not applicable here — inbound auth to AgentCore is SigV4, not JWT (FR-21) |

---

## 9. Out of Scope for v1

- Retrieval (Tier B) and tools/agentic behaviour (Tier C)
- Thread replies without `@mention` (RSC) — carries an untested install risk
- Group chats without `@mention` — unresearched
- **Manual provisioning of the Microsoft side — but for a sharper reason than originally recorded.**
  Revised 2026-08-04 following `docs/teams-chatbot-docs/Entra CLI Automation - Research 2026-08-03.md`.
  The original rationale ("Terraform out of scope for time") was weaker than the truth. The actual boundary:

  **REVISED AGAIN 2026-08-04** after `docs/teams-chatbot-docs/Teams Admin CLI Automation - Findings
  2026-08-03.md`, which **live-tested** the steps the previous document could only reason about. The picture
  is materially better. "Manual runbook" now understates it — the honest description is **fully scripted,
  with one interactive OAuth consent.**

  | Step | Automatable? | Evidence |
  | --- | --- | --- |
  | Entra app registration + secret | **Yes**, app-only | documented |
  | Azure Bot Service + MsTeams channel + endpoint | **Yes**, service principal | `az bot`, read-tested |
  | Teams app package (the zip) | **Yes** | **hand-authored live, zero Developer Portal use** |
  | **Publish to the tenant catalog** | **Yes — CONFIRMED LIVE** | Graph `POST /appCatalogs/teamsApps`, zip body, `201 Created` |
  | Delete from catalog | **Yes — confirmed live** | Graph `DELETE`, `204` |
  | Tenant-wide app settings | **Yes — confirmed live** | Graph `GET`/`PATCH /teamwork/teamsAppSettings` |
  | **Availability scoped to an Entra group** | **Yes — CONFIRMED LIVE** | Teams PowerShell `Update-M365TeamsApp -Groups`, full add/remove round trip |
  | Push-install for users/teams | Yes, documented | Graph `POST .../installedApps` |
  | Approve a pending-review submission | Documented, not tested | Graph `PATCH` + `If-Match` etag |
  | Grant sideloading (Setup Policy) | Teams PowerShell only, untested | no Graph equivalent |

  **The only irreducibly human step is a one-time interactive OAuth consent** for whichever client is doing
  the scripting — an OAuth property, not a Teams limitation. Everything after that is `curl` and `pwsh`.

  **Two corrections to what this document previously recorded**, both in the favourable direction:

  1. **Catalog publish is not blocked.** The prior entry said "delegated-only by documented design" and
     treated that as disqualifying. Delegated *is* required — but a delegated token obtained once via
     **device-code flow** drives the whole thing for a ~70-minute session. Confirmed live, not inferred.
  2. **Availability scoping is automatable.** The prior entry said `Update-M365TeamsApp` was on the
     app-auth exclusion list, so scoping was manual. It is excluded from *app-only* auth — but works fine
     with a delegated token, and `-Groups` takes Entra group IDs with **live membership evaluation**, not a
     per-user snapshot. Confirmed live with a full add-then-remove round trip.

  **Still true and still the reason this is out of scope for v1**: none of it is *per-deployment*. It is
  one-time-per-bot onboarding, and it needs a human at a browser once. Building it into the pipeline would
  mean smuggling a user identity into CI, which is a worse posture than a scripted runbook run by a person.

- **A Terraform stage, specifically.** The automatable Microsoft surface is ~4 resources created **once**. A
  small idempotent script invoked from CodeBuild is a better fit than standing up Terraform with remote state
  — particularly because `azuread_application_password` writes the generated secret into Terraform **state**,
  which collides directly with "secrets live only in AWS Secrets Manager". The script approach generates the
  secret and writes it straight to Secrets Manager without it ever landing in state. No Terraform provider
  covers the catalog publish step in any case.
- Secret rotation
- Automated tag validation — deferred pending D-3
- `observability/`, `builder-mcp/`, and the production Cornell tenant

---

## 10. Summary

`teams-bot` is a **parameterised blueprint** that deploys a Microsoft Teams chatbot into a governed AWS
account through the existing PR-to-`main` pipeline. A builder describes what they want, the `builder-mcp`
keystone writes parameter values into a deployment repository, and the pipeline deploys a working bot.

The bot receives Bot Framework activities at a public Lambda function URL, validates every request against
the Bot Framework JWKS — including the `serviceurl` correlation that was silently broken in the prototype —
acknowledges within milliseconds, and streams its answer back into Teams. The thinking happens in a Bedrock
AgentCore Runtime container on ARM64, and every model call goes through Cornell's LiteLLM gateway, which is
what makes medium-risk data permissible.

Three things make this more than a bot: it is the first blueprint here to expose a public endpoint, the
first to run deployed compute, and the first to read a secret at runtime. The container build path it
depends on exists in the repository and has never once run.

**Capability is Tier A** — prompt and model configurable — deliberately, because Tier A already exercises
every one of those firsts, and none of them becomes easier by adding retrieval on day one.
