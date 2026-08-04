# Unit of Work — Track C, the Teams front end of `course-chatbot`

**Generated**: 2026-08-04
**Stage**: INCEPTION — Units Generation (Part 2: Generation)
**Source plan**: `aidlc-docs/inception/plans/unit-of-work-plan.md`
**Gate answers**: `aidlc-docs/inception/plans/units-generation-gate-questions.md` — 1=C, 2=A, 3=A, 4=A

---

## What this document is, and what it is not

Ten units, ordered. **They are sequencing and review guidance, not PR boundaries** — that follows from
the Part 1 answers: mob-style execution (whole cross-functional team, serial) and **one PR**. A unit is
"done" when its completion criteria are met, not when something is merged.

Each unit therefore carries explicit completion criteria rather than a story list, and a note on whether
a non-engineer can see it working. That second column exists because the mob includes product owners, IT
service management, security, analysts, designers and business stakeholders — a unit whose only evidence
is "a lint rule passes" cannot be validated by the room.

---

## Amendments to earlier artifacts, forced by the gate answers

Recorded here rather than silently applied, because these were user decisions in earlier stages.

| Earlier record | Amendment | Authority |
| --- | --- | --- |
| **FR-5** — blueprint `teams-bot`, stack `aidlc-main-teams-bot`, template `blueprints/teams-bot/infra/teams-bot.yml` | **Amended, not deleted.** Deliverable is Track C's slice of `blueprints/course-chatbot/`. Template `blueprints/course-chatbot/infra/course-chatbot.yml`, stack `aidlc-main-course-chatbot`. The reusable-block intent survives as a roadmap item (below). | Gate Q1 = C |
| **Application Design Q11** — one multi-stage Dockerfile, two named targets (`lambda`, `agent`) | **Superseded.** One Dockerfile per component, each in its own directory, each with its own `CONTAINER_CONTEXT` and named target. | Gate Q2 = A |
| **`components.md` package layout** — `blueprints/teams-bot/` with a single root `Dockerfile` | **Superseded** by the layout below. Component responsibilities and interfaces in that document are **unchanged and still authoritative.** | Gate Q1 + Q2 |
| **PR #21 Question 3** — "A) Inside the Bot Framework Lambda handler. One Lambda handles Teams auth, agent execution, and the KB call." | **Overridden.** The agent runs on AgentCore. `requirements.md` FR-21 records AgentCore as *mandated* by Team E, and a mandate is not Track C's to set aside on time grounds. Pete's file is left byte-identical so PR #21 merges cleanly. | Gate Q3 = A |
| **`upstream-reconciliation-2026-08-04.md` §2a** — "Q3 versus the AgentCore mandate is unresolved… Raised with Marty rather than decided" | **Now decided**, in the direction of the standing mandate. Still owes Marty a sentence today — see the open item at the end. | Gate Q3 = A |

### The roadmap item Q1=C preserves

The Q2 requirements decision — *"generic and reusable, not course-specific"* — is sound and outlives this
week. It is recorded as a **follow-up, not a discard**:

> **Extraction candidate.** Everything in `src/frontdoor/`, `src/worker/` and `src/shared/` is
> Teams-specific but course-agnostic; everything in `src/agent/` is both channel-agnostic *and*
> course-agnostic. A future `teams-bot` blueprint is a directory move plus a template split, not a
> rewrite — **provided the units below do not introduce a course-specific dependency into
> `src/shared/`**. That is a design constraint on U3–U7, not a task in U8.

This is also what makes the channel-agnostic Agent decision pay off twice: it is already extractable.

---

## Decomposition principle — risk retirement, with one large revision

Units are ordered so each retires the largest remaining risk. **The single largest risk that justified
this ordering is gone**, and saying so plainly matters more than preserving the original narrative:

> **R-1 is retired.** The container build path *has* executed. Upstream wired a `Build` stage with
> `ARM_CONTAINER` / `amazonlinux2-aarch64-standard:3.0`, added `CONTAINER_CONTEXT` alongside
> `CONTAINER_TARGET`, and both `tiny-chatbot` and `builder-mcp` build through it. `builder-mcp` is an
> **arm64 AgentCore runtime deployed by digest from CloudFormation** — which is precisely U6's shape.

So **U1 changes character**: from *"prove an unproven path with a throwaway container"* to *"add two
actions modelled on an existing one."* It stays first because the two images still gate everything that
runs, but it is now hours-not-days and the project's HIGH risk rating should be re-assessed on that basis.

**What is still genuinely unretired**, and therefore what the ordering is now optimising against:

| Risk | Retired by | Note |
| --- | --- | --- |
| `azurerm` cannot reach the tenant — no Azure subscription RBAC for the service principal | **Nothing in this plan.** U0 routes around it | An approval, not code. Global Administrator is a directory role and grants no resource-plane access |
| The `serviceurl` correlation is easy to reintroduce broken | **U3**, with a mandatory negative test | The prototype's check was present-but-non-functional; this is the highest-value test in the blueprint |
| Two independent duplicate-delivery sources | **U4** | Azure retries *and* Lambda async retries twice on error |
| Teams streaming has six rules that each silently break it | **U7** | Cumulative not deltas; `streamSequence` absent on the final message; 1 req/s; sequential |
| `pipeline.yml` is high-contention and self-deploying, recovery undocumented | **Nothing.** R-2 stands | One PR reduces the number of times we touch it, which is the only mitigation available |

---

## Execution model

| | |
| --- | --- |
| **Mode** | Mob-style — whole cross-functional team, **serial**, one unit at a time |
| **Parallelism** | **None.** Every "Parallel? Yes" in the Part 1 proposal is withdrawn. U0 is the one exception: non-AWS, needs admin credentials, cannot usefully be mobbed |
| **PRs** | One, cross-fork from `ferminromeroiii/ai-dlc-workshop`, merged by an `ai-dlc-workshop` team member |
| **Deployment feedback** | First arrives **on merge** — `Environment` is the branch name and Source tracks `BranchName: !Ref Environment`, so a PR branch does not trigger the pipeline. Expect one corrective merge and plan for it |
| **Local pre-merge proof** | `docker buildx build --platform linux/arm64` for both images, plus `tools/check` |
| **Mob checkpoints** | **U5** (the bot says hello) and **U7** (text appears progressively). U1–U4 are one continuous stretch of plumbing, not four celebrations |

---

## Code organisation strategy

The Part 1 plan calls for this explicitly. Note that `units-generation.md` Step 2 marks code
organisation as *"Greenfield only"* — this project is **Brownfield**, but the blueprint directory is new
and shared with two other tracks, so the layout is a real decision rather than an inherited one. It is
recorded for that reason.

```
blueprints/course-chatbot/
  infra/
    course-chatbot.yml          Track C's CloudFormation: Lambdas, function URL, DynamoDB,
                                AgentCore Runtime + Endpoint + Memory, roles, SSM, log groups
    azure/                      Track C's Terraform (azuread only — see U0)
      main.tf  versions.tf  .terraform.lock.hcl
  src/
    handler.py                  PRE-EXISTING scaffold stub. Not Track C's. See the note below
    frontdoor/                  entry point A — Lambda handler
      Dockerfile                target: course-chatbot-lambda
    worker/                     entry point B — async-invoked Lambda handler
    agent/                      FastAPI app for AgentCore Runtime
      Dockerfile                target: course-chatbot-agent
    shared/                     imported by frontdoor, worker and agent
  teams-app/
    manifest.json  color.png  outline.png
  scripts/                      Microsoft-side provisioning that Terraform cannot reach
  pyproject.toml
  uv.lock                       required by uv sync --frozen (SECURITY-10)
  blueprint.yaml                the Builder MCP manifest — added in the same PR as the template
```

**Two images, two Dockerfiles, two contexts.** `src/frontdoor/Dockerfile` builds the Lambda image that
*both* Lambdas run — Front Door and Worker share one image with different handlers, which is unchanged
from Application Design. `src/worker/` therefore has no Dockerfile of its own; it is a second entry
point into the same image, and the `CONTAINER_CONTEXT` for that build is `blueprints/course-chatbot/src`
so both packages and `shared/` are in scope. `src/agent/Dockerfile` builds the arm64 AgentCore image.

**`CONTAINER_CONTEXT` and the target must agree with where the component actually lives.** A stale
context fails the build with a missing-path error that says nothing about the move that caused it.

### The pre-existing `src/handler.py`

Ernest's scaffold stub. It constructs `AnthropicBedrock`/`AnthropicBedrockMantle` and reaches Bedrock
with the execution role, which **violates FR-23** — all model traffic must route through Cornell's
LiteLLM gateway.

**Track C adds alongside it and does not depend on removing it.** Recorded as a finding against the
scaffold, not adopted as Track C debt:

- Track B, whom the blueprint README nominally assigns `src/`, has moved to
  `blueprints/knowledgebase/`, so it may already be dead code.
- Deleting another track's file on demo day is not a risk worth taking for tidiness, and retirement is
  Track B's and Track D's call.
- **No Track C unit reads, imports or extends it.** If it survives to deployment it must not be given a
  Lambda function or an execution-role Bedrock grant, or FR-23 is violated by something Track C shipped.

---

## The ten units

### U0 — Microsoft identity chain

| | |
| --- | --- |
| **Delivers** | Entra app + service principal + credential; Azure Bot Service with the MsTeams channel; messaging endpoint pointed at the function URL; Teams app package sideloaded into the dev tenant |
| **Proves** | The bot exists in Teams and has somewhere to point |
| **Demoable** | Moderately — the bot appears in a Teams client, greyed out until there is an endpoint |
| **Components** | none (no application code) |

**Split by what each mechanism can actually reach**, which is now well evidenced rather than assumed:

| Step | Mechanism | Where it lives |
| --- | --- | --- |
| Entra app, service principal, credential resource | `azuread` Terraform | `infra/azure/` — the repo's required path for Entra |
| Azure Bot Service + MsTeams channel + endpoint | **script** (`az bot`) | `scripts/` — `azurerm` is blocked, see below |
| Sideload grant (Setup Policy) | script, **app-only, confirmed live** | `scripts/` |
| App package zip + sideload | script | `scripts/` |

**`azurerm` is blocked and this is an approval, not a coding problem.** It needs an Azure subscription in
the tenant *and* an Azure RBAC assignment for the service principal. A Global Administrator directory
role grants neither. Compounding it, the existing Bot Service resource lives in **Cornell's** tenant
under the *JCB IT NSS* subscription while the Entra app is pinned to the **dev** tenant — two tenants,
one stored service principal. So the Bot Service half stays scripted until that clears.

**The first `.tf` file here must arrive in the same PR as its `Terraform` action.** `validate_stacks.py`
cross-checks `blueprints/*/infra/azure/` directories holding `.tf` files against the `TF_WORKING_DIR`
values in `pipeline.yml`, in both directions — but a directory only counts as a module once it holds a
`.tf` file. **And the `Terraform` stage applies unattended**: no approval action, so a merge reaches the
tenant with whatever rights the stored principal holds. Treat a change here as taking effect on merge.

**Sideload, not catalog publish** (PR #21 Q6). This **dissolves the one interactive login for v1** —
catalog publish and availability scoping were the only steps requiring a delegated device-code token,
and both are out. Their un-automatability is settled rather than untested, so **do not design U0
expecting to add them later cheaply**: app-only 401s on the scoping cmdlet, Teams Administrator
escalation changes nothing, and `Connect-MicrosoftTeams -AccessTokens` fails structurally because the
module needs a third resource token (`https://substrate.office.com`) and the parameter hard-validates
for exactly two.

**Secret handling.** The Entra client secret's *resource* is declared in CloudFormation with
`GenerateSecretString` and `DeletionPolicy: Retain`; the value is injected once by CLI with
`put-secret-value`. **Never `SecretString`** — that property is enforced on every stack update and
`PipelineDeploy` redeploys on every merge, so a placeholder in the template resets the live credential
several times a day. Never generate the secret in Terraform: `azuread_application_password` writes it
into state.

**Completion criteria**

- [ ] `az ad app create` **and `az ad sp create`** both run — two distinct directory objects. The Portal
      does both when you click through the blade; the CLI does not. Omit the second and everything looks
      fine until the bot's **first outbound token call** fails with nothing pointing back at the cause.
      This is the single most likely way to lose an afternoon in U0
- [ ] Script is idempotent and safely re-runnable from any point
- [ ] Bot resource's messaging endpoint set from the stack output via `az bot update --endpoint`, not
      transcribed by a human (FR-7a)
- [ ] App package zip has `manifest.json` + `color.png` + `outline.png` **at the zip root**, no subfolder
- [ ] Manifest carries top-level `"supportsChannelFeatures": "tier1"` — authored as a file because the
      Developer Portal's validator wrongly rejects it inside the `bots` object
- [ ] No credential in any file. This repository is public and has **no secret scanning**
- [ ] Terraform module registered as a `TF_WORKING_DIR` action in the same PR as its first `.tf`

---

### U1 — Build capability

| | |
| --- | --- |
| **Delivers** | Two `Dockerfile`s with named targets; two `Build` stage actions; `pyproject.toml` + `uv.lock` |
| **Proves** | Both images build for arm64, satisfy their runtime contracts, and export digests |
| **Demoable** | Weakly — two images exist in ECR |
| **Components** | none yet; this is the substrate |

**Changed character, as noted above**: the path is proven, so this is "add an action modelled on
`builder-mcp`". `packages/builder-mcp/infra/builder-mcp.yml` plus its Build action is the worked example
for the agent image; `blueprints/tiny-chatbot` is the simpler one for the Lambda image.

**`uv.lock` is inline here, not deferred to U9** (Part 1 Q3 = C). Two reasons: AgentCore's
`uv sync --frozen` will not run without it, and it closes Reverse Engineering technical-debt item 4 and
SECURITY-10 at the same time.

**Completion criteria**

- [ ] `docker buildx build --platform linux/arm64` succeeds for both targets **locally**, before merge —
      this is most of the risk and needs no AWS at all
- [ ] Agent image satisfies FR-22: arm64, port **8080** bound to `0.0.0.0`, `GET /ping` returning
      `{"status": "Healthy"}`, `POST /invocations`, `opentelemetry-instrument` wrapping the entrypoint
- [ ] Lambda image builds on the AWS Lambda Python base image
- [ ] No `latest` or unpinned base image tags (SECURITY-10)
- [ ] `uv.lock` committed
- [ ] Each action's `CONTAINER_CONTEXT` matches where the component actually lives, and
      `CONTAINER_TARGET` matches the `Dockerfile`'s named target
- [ ] `DATE_TAG` supplied as `#{GitRepository.AuthorDate}` — the buildspec does not provide it

---

### U2 — Blueprint skeleton

| | |
| --- | --- |
| **Delivers** | `infra/course-chatbot.yml` with the Lambda pair, function URL, roles, log groups, SSM parameters, tags and outputs; `pipeline/stacks.yml` entry; `BlueprintDeploy` action; `blueprint.yaml` |
| **Proves** | A public URL exists, `tools/check` passes, all four tags land, config is readable at runtime |
| **Demoable** | Weakly — a URL returns `200` |
| **Components** | `ConfigProvider` |

**Shared blueprint, so this unit is not solely Track C's.** Track B's retrieval and Track D's seam land
in the same template. Coordinate before merging: a second track editing `infra/course-chatbot.yml` in
the same window is a merge conflict in a file that deploys on merge.

**Configuration comes from SSM at runtime, not from `inputs` parameters** (PR #21 Q5). This works around
an open defect, and the defect is silent: `deployment_create` passes only `Application`, `Environment`,
`Owner` and the manifest's `pipeline_parameters`, so values declared under `inputs` are collected from
the builder and then **dropped**. `SystemPrompt`, `ModelId`, `GreetingText` and `TeamsScopes` would all
have arrived empty — green plan, wrong stack (#15 finding 2). If Track A fixes the defect, this becomes
a temporary workaround rather than the design.

**Completion criteria**

- [ ] Stack name `aidlc-main-course-chatbot` — `<application>-<environment>-<name>`. Outside the
      convention, `BuildPipelineRole` refuses it with an opaque authorization error, not a naming complaint
- [ ] `Environment` declared as `[a-z0-9]{1,4}` — four characters, no hyphens
- [ ] **All four `cornell:*` tags on every resource.** `AWS::SSM::Parameter` takes `Tags` as a **map**,
      unlike every other resource here
- [ ] `DeploymentName` is a parameter, not a hardcoded name
- [ ] `FunctionName` deterministic so CloudFormation never replaces the function — replacement changes
      the URL (FR-7)
- [ ] Function URL exported as a stack output (FR-7), consumed by U0's endpoint push (FR-7a)
- [ ] **Log retention ≥ 90 days** on every log group — inline here per Part 1 Q3, not deferred
      (SECURITY-14)
- [ ] Execution role **cannot delete its own log groups or streams** (SECURITY-14)
- [ ] No wildcard actions or resources anywhere in the role (SECURITY-06)
- [ ] Every parameter passed **explicitly** from the pipeline; template defaults are for hand-debugging only
- [ ] Registered in `pipeline/stacks.yml` **and** given a matching action — `validate_stacks.py` fails in
      both directions, and a registered template with no action deploys nothing while every stage
      reports success
- [ ] `blueprint.yaml` names the registered template, in the same PR as the template
- [ ] `tools/check` passes

---

### U3 — Inbound trust

| | |
| --- | --- |
| **Delivers** | `JwtValidator`, `ActivityNormalizer`, `Logger`; Front Door validates, logs and acknowledges |
| **Proves** | **Forged requests are rejected**, and the `serviceurl` negative test passes |
| **Demoable** | Poorly — "forged requests are rejected" is hard to show a non-engineer |
| **Components** | `FrontDoor`, `JwtValidator`, `ActivityNormalizer`, `Logger` |

**This unit carries the blueprint's most important test.** The prototype's `serviceurl` check was
*present and non-functional*: the claim is `serviceurl` (lowercase `u`), the code read
`payload.serviceUrl` (camelCase) which is always `undefined`, and a `&&` guard turned the check into a
silent skip. It is the control that stops an attacker with a valid token redirecting the bot's replies.

**Completion criteria**

- [ ] Signature verified RS256 with the algorithm **pinned** — `header.alg` never trusted
- [ ] `iss`, `aud`, `exp`/`nbf` checked with 300s skew. `aud` from configuration, **never literal in code**
- [ ] `serviceurl` claim compared against the normalised `body.serviceUrl`, and **absence of the claim
      is a FAILURE, not a pass** (fail closed — SECURITY-15)
- [ ] **Negative test proving a mismatched `serviceurl` is rejected** (FR-8a) — mandatory
- [ ] `serviceUrl` normalised **once**: trailing slash stripped, then joined with an explicit `/`, and
      the same value used for both the claim check and reply URLs (FR-14). The prototype relied on an
      undocumented trailing slash
- [ ] JWKS cached, refreshed on **`kid` miss**, not on a timer alone (FR-15)
- [ ] `200 OK` returned on validation failure with no action taken (FR-10). A 4xx makes Azure retry a
      request that can never succeed
- [ ] Every inbound request logged — timestamp, correlation ID, activity type, conversation type,
      validation outcome. This is the **SECURITY-02 compensating control**; a function URL has no access log
- [ ] **No secrets, tokens or message bodies logged** (SECURITY-03)
- [ ] Request body size limit and schema validation before use (SECURITY-05)
- [ ] Dispatch on `body.type`, tolerating activities with no `text` (FR-12)
- [ ] `membersAdded`/`membersRemoved` filtered on the `28:` bot prefix, or the bot greets itself
- [ ] `JwtValidator` has **no blueprint-specific imports**, so extraction later is a file move
      (SECURITY-11, Q9)

---

### U4 — Idempotency and hand-off

| | |
| --- | --- |
| **Delivers** | DynamoDB table, `IdempotencyStore`, async invoke, Worker skeleton |
| **Proves** | The same activity arriving twice produces one unit of work |
| **Demoable** | Poorly |
| **Components** | `IdempotencyStore`, `Worker` (skeleton) |

**Two guards, because there are two independent duplicate sources** — and only one of them is
Microsoft's. Azure Bot Service retries when it does not get a fast `200`; Lambda async invocation
**retries twice on error**, which is internal. Streaming raises the stakes: Teams permits one concurrent
stream per chat, so a duplicate produces a visible error rather than a repeated answer.

**Completion criteria**

- [ ] Table with partition key `activity_id`, a TTL attribute, and encryption declared (SECURITY-01)
- [ ] `FrontDoor.claim()` succeeds only if the item is absent → catches **Azure** retries
- [ ] `Worker.begin_delivery()` succeeds only if status is `claimed` → catches **Lambda async** retries
- [ ] All three transitions are conditional writes; a duplicate arriving at a state it cannot legally
      leave aborts quietly without raising
- [ ] **Worker timeout set explicitly** — the 3-second default would truncate every reply. Order of 5 minutes
- [ ] Test: the same activity `id` submitted twice yields one downstream invocation

---

### U5 — First reply · **MOB CHECKPOINT**

| | |
| --- | --- |
| **Delivers** | `TokenProvider`, `BotFrameworkClient`, `SingleReplyDelivery`, `conversationUpdate` greeting |
| **Proves** | **A human sees the bot say hello in Teams** |
| **Demoable** | **Yes — this is the first one the whole room can judge** |
| **Components** | `TokenProvider`, `BotFrameworkClient`, `DeliveryDispatcher` (single-reply strategy) |

**Deliberately requires neither the agent nor the gateway.** A `conversationUpdate` greeting is a
configured constant. **If the workshop runs short, U0–U5 is a demonstrable Teams bot deployed through the
governed pipeline** — which proves the platform thesis even with no model in the loop. That is why U5 is
placed before U6 despite the agent being the more interesting engineering.

**Completion criteria**

- [ ] `client_credentials` grant against the single-tenant Entra app, scope
      `https://api.botframework.com/.default`; token cached until near expiry (FR-20)
- [ ] Entra client secret read from Secrets Manager at runtime — `secretsmanager:GetSecretValue` scoped
      to the **named secret**, no wildcard (SECURITY-06)
- [ ] Reply URL built from the normalised `service_url`:
      `{serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}` (FR-19)
- [ ] Typing indicator then one complete reply (FR-18)
- [ ] Rate-limit and error responses surfaced to the caller, not swallowed
- [ ] On failure, a generic message plus the correlation ID — which **is the activity `id`**, so a user
      quoting it leads straight to every log line for that request (Q12)
- [ ] A person in the dev tenant messages the bot and sees the greeting

---

### U6 — Agent runtime

| | |
| --- | --- |
| **Delivers** | Agent FastAPI app, `GatewayClient`, `AWS::BedrockAgentCore::Runtime` + `RuntimeEndpoint` + `Memory` |
| **Proves** | A JSON payload gets a streamed answer — **tested with no Teams involvement at all** |
| **Demoable** | Moderately — a JSON payload in, a streamed answer out |
| **Components** | `Agent`, `GatewayClient` |

**AgentCore is mandated** (FR-21, gate Q3 = A), overriding PR #21's one-Lambda answer. Invoked with
**SigV4 from the Lambda, in-account** — never exposed to Azure Bot Service directly, because AgentCore's
`CUSTOM_JWT` authorizer cannot perform the `serviceurl` correlation U3 depends on.

**This is the payoff of the channel-agnostic decision**: the agent has never heard of Teams, so it is
testable with a JSON payload and no Bot Framework fixtures, and a future Slack or web front end reuses it
unchanged. `packages/builder-mcp/infra/builder-mcp.yml` is the worked example for the CloudFormation.

**Completion criteria**

- [ ] `GET /ping` → `{"status": "Healthy"}`; `POST /invocations` accepting an Envelope-derived payload
- [ ] **All model traffic through the LiteLLM gateway** at `https://api.ai.it.cornell.edu` (FR-23).
      No direct Bedrock inference — this is the hard constraint that permits medium-risk data
- [ ] Gateway key is a **service key issued for this bot**, never a person's, read from Secrets Manager
      at runtime (FR-23a), with the `GenerateSecretString` + one-time `put-secret-value` treatment
- [ ] Gateway-native model IDs, not Bedrock's native IDs
- [ ] Conversation history read and written in AgentCore Memory (FR-24). Each session runs in a
      dedicated microVM for up to 8 hours, giving per-user isolation by construction
- [ ] Output streamed as SSE; gateway errors translated into one internal error type
- [ ] Image referenced by **`CONTAINER_DIGEST`** (`<repo-uri>@sha256:…`) via `ParameterOverrides`,
      never by a mutable tag (FR-28, SECURITY-13)
- [ ] `bedrock-agentcore:InvokeAgentRuntime` scoped to the runtime ARN, no wildcard
- [ ] Every external call has explicit error handling (SECURITY-15)
- [ ] Verified end to end **before** Teams is wired to it

---

### U7 — Streaming delivery · **MOB CHECKPOINT**

| | |
| --- | --- |
| **Delivers** | `StreamingDelivery`; `DeliveryDispatcher` dispatching on `conversation.conversationType`; Worker wires agent → delivery |
| **Proves** | **Text appears progressively in a personal chat** |
| **Demoable** | **Yes — the second thing the whole room can judge** |
| **Components** | `DeliveryDispatcher` (streaming strategy), `Worker` (complete) |

**The seam is what makes U8 an addition rather than a rewrite** (FR-16). The agent must never call
delivery APIs directly. Both strategies consume the same chunk iterator, so the agent's output shape is
identical either way and a future channel is a third strategy rather than a change to anything else.

**Six rules that each silently break streaming.** Every one is easy to get wrong and none produces a
clear error:

**Completion criteria**

- [ ] An **informative** update first (progress bar, ≤1 KB / 1000 characters), then progressive text
- [ ] Content **cumulative, not deltas** — `"A brown"` → `"A brown fox"` → …
- [ ] `entities.type` is `streamInfo`; `streamId` taken from the first response (`201 Created`)
- [ ] `streamSequence` starts at 1, increases monotonically, and **MUST NOT be set on the final message**
- [ ] Final message is `type: "message"` with `streamType: "final"`
- [ ] Rate limit **1 request/second**; model tokens buffered **1.5–2 seconds**
- [ ] Calls **sequential** — await success before the next
- [ ] Attachments, AI labels, feedback buttons and sensitivity labels only on the final message
- [ ] Streaming used **only** in one-on-one chats; other scopes fall through to `SingleReplyDelivery`

---

### U8 — Scope expansion

| | |
| --- | --- |
| **Delivers** | Manifest `groupChat` + `team` scopes, `supportsChannelFeatures`, both conversation-ID formats handled |
| **Proves** | An `@mention` in a channel gets a reply |
| **Demoable** | Yes — a reply in a channel |
| **Components** | none new — this is why FR-16's seam exists |

Teams scopes are **personal + group chat + channel with `@mention` required**, no RSC (requirements Q4 = C).

**Completion criteria**

- [ ] Both conversation-ID formats handled: personal `a:xxx`, channel/group `19:xxx@thread.tacv2` (FR-13)
- [ ] Manifest v1.25 carries top-level `"supportsChannelFeatures": "tier1"` for `team` scope
- [ ] Group and channel scopes get typing indicator + single reply, not streaming (FR-18)
- [ ] In-place manifest updates **do not re-consent** — a scope change may need a re-install to take effect
- [ ] No new component added, confirming the seam held

---

### U9 — Hardening

| | |
| --- | --- |
| **Delivers** | Validation-failure alarm, reserved concurrency, dependency vulnerability scanning |
| **Proves** | Security Baseline satisfied in the deployed artifact |
| **Demoable** | Weakly — an alarm exists |
| **Components** | none |

**Split per Part 1 Q3 = C.** The cheap parts are **already done inline** and are not repeated here:
`uv.lock` in U1 (required by `uv sync --frozen` anyway) and 90-day log retention in U2 (one property on
a resource). What remains is genuinely separate work.

**Completion criteria**

- [ ] Alarm on repeated JWT validation failures (SECURITY-14)
- [ ] **Reserved concurrency set as a blast-radius control** (SECURITY-11). Recorded honestly: a Lambda
      function URL has no built-in throttling, so this **bounds cost and impact rather than preventing
      abuse**. Rate limiting remains a genuine gap
- [ ] Dependency vulnerability scanning step added or documented (SECURITY-10)
- [ ] An SBOM produced (SECURITY-10, SHOULD)
- [ ] Every log group has ≥ 90-day retention — verify U2 delivered it rather than assuming

---

## Bounded contexts

**Two contexts inside one blueprint** (Part 1 Q12 = B recorded as a note, A in practice):

| Context | Units | Boundary |
| --- | --- | --- |
| **Teams channel adapter** | U0, U2–U5, U7, U8 | Knows Bot Framework, JWTs, Teams streaming rules |
| **Conversational agent** | U6 | Knows models, memory and retrieval. **Has never heard of Teams** |

The design already draws this line — the agent has **no path to any Teams component**, and the
`Envelope` is the only thing crossing. Recording it as two contexts documents the seam without
prematurely splitting the deliverable, and it is what makes the extraction candidate above cheap.

**Track D owns the inter-block protocol**, so where this seam ends up formally is their decision;
Track C's job is to supply evidence to it, not to pre-empt it.

---

## Security Baseline verification across the decomposition

Extension **enabled**. Verified that every requirement carrying a Security Baseline obligation is owned
by a named unit, and that no obligation is orphaned.

| Rule | Owning unit(s) | Verified |
| --- | --- | --- |
| SECURITY-01 encryption | U2 (log groups, SSM), U4 (table), U6 (Memory) | ✅ |
| SECURITY-02 access logging — **compensating control** | **U3** — handler logs every inbound request | ✅ |
| SECURITY-03 application logging | U3 (`Logger`), all units use it | ✅ |
| SECURITY-04 HTTP security headers | — | **N/A**, no HTML served |
| SECURITY-05 input validation | U3 (size limit, schema, type dispatch), U6 (10k query cap at Tier B) | ✅ |
| SECURITY-06 least privilege | U2 (roles), U5 (secret ARN), U6 (runtime ARN) | ✅ |
| SECURITY-07 network — **documented exception** | U2 — public function URL by design | ✅ |
| SECURITY-08 access control | U3 | ✅ |
| SECURITY-09 hardening | U1 (base images), U3 (bare `200` on error) | ✅ |
| SECURITY-10 supply chain | **U1** (`uv.lock`, pinned bases) + **U9** (scanning, SBOM) | ✅ |
| SECURITY-11 secure design — **noted limitation** | U3 (isolated validator) + **U9** (reserved concurrency) | ✅ |
| SECURITY-12 credentials | U0 (no secret in files), U5, U6 (Secrets Manager only) | ✅ |
| SECURITY-13 integrity | U3 (safe parsing) + **U6/U1** (digest pinning) | ✅ |
| SECURITY-14 alerting | **U2** (retention, role cannot delete logs) + **U9** (alarm) | ✅ |
| SECURITY-15 fail-safe defaults | U3 (absent claim = failure), U5, U6 (error handling) | ✅ |

**No orphaned Security Baseline obligations. No blocking findings.** Three items remain compliant by
compensating control or documented exception rather than direct satisfaction — **SECURITY-02**,
**SECURITY-07** and **SECURITY-11** — unchanged from Requirements Analysis. All three follow from
choosing a Lambda function URL over API Gateway, and each now has a **named owning unit** rather than
sitting as a requirement nobody is scheduled to satisfy. That is the one thing this stage adds to them.

**One change since Requirements Analysis worth flagging.** SECURITY-13 cites CI/CD integrity as *"`main`
is PR-only with one human approval and nobody may approve their own PR."* **That is no longer true** —
zero approving reviews are required and only `ai-dlc-workshop` team members may merge, so `validate` is
the sole automated gate. The rule is still satisfied by digest pinning and safe parsing, but the
human-approval leg of its justification has gone. Not a blocking finding; recorded so it is not quoted
as fact later.

---

## Open items this stage does not close

| # | Item | Owner | Blocks |
| --- | --- | --- | --- |
| 1 | **Say to Marty today** that Track C ratified AgentCore over PR #21's one-Lambda answer | The user | Nothing — the answer follows the standing mandate. But a disagreement found in rehearsal costs the demo |
| 2 | **Azure subscription RBAC** for the Terraform service principal | Whoever owns the subscription | The `azurerm` half of U0. Routed around, not solved |
| 3 | **Gateway service key** for the bot, scoped for chat | Gateway operator | U6 deployment, not design |
| 4 | **`deployment_create` drops `inputs`** (#15 finding 2) | Track A | Nothing — U2 reads SSM instead. Fixing it makes U2's approach a workaround rather than the design |
| 5 | Coordination on `infra/course-chatbot.yml` with Tracks B and D | The mob | U2 merge conflicts in a file that deploys on merge |
| 6 | **Pipeline recovery procedure undocumented** (R-2) | Marty / Dan | Nothing directly. Still the scariest unmitigated risk in the repo |
| 7 | Tagging guidance document (D-3) | The user | Nothing — four tags stand meanwhile |

**Out of v1 and deliberately not unit-assigned**: Tier B retrieval, Tier C tools, RSC/thread replies
without `@mention`, group chats without `@mention`, secret rotation, automated tag validation.
