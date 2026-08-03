# AI-DLC State Tracking

## Project Information

- **Project Type**: Brownfield
- **Start Date**: 2026-08-03T18:06:09Z
- **Current Stage**: INCEPTION - Units Generation Part 1 **(plan created, awaiting answers)**

## Execution Plan Summary

- **Total stages remaining**: 8 (2 INCEPTION, 6 CONSTRUCTION)
- **Stages to Execute**: Application Design, Units Generation, Functional Design, NFR Requirements,
  NFR Design, Infrastructure Design, Code Generation, Build and Test
- **Stages to Skip**: User Stories — the deliverable is a parameterised infrastructure template with a
  single persona and no acceptance criteria beyond what requirements already capture
- **Risk Level**: **High** — never-executed container build path; self-deploying pipeline with an
  undocumented recovery procedure; shared account; parallel merges from multiple teams; nearly every
  element is a first for this repository
- **Plan**: `aidlc-docs/inception/plans/execution-plan.md`
- **Work Item**: Microsoft Teams chatbot blueprint

## Workspace State

- **Existing Code**: Yes
- **Programming Languages**: Python 3.11+, YAML (CloudFormation), Bash
- **Build System**: None conventional. `uv` inline script metadata (PEP 723) for Python
  tooling; CloudFormation deployed by CodePipeline; `tools/check` is the local/CI entry point
- **Project Structure**: Infrastructure-as-code monorepo (deploy pipeline plus blueprints)
- **Reverse Engineering Needed**: Yes
- **Workspace Root**: `/home/fermin/codeprojects/ai-dlc-workshop`

## Code Location Rules

- **Application Code**: Workspace root (NEVER in `aidlc-docs/`)
- **Documentation**: `aidlc-docs/` only
- **Repository-specific placement**: blueprint code and templates go under
  `blueprints/<name>/`, with CloudFormation at `blueprints/<name>/infra/<name>.yml`

## Repository Constraints In Force

These come from `CLAUDE.md` and bind every AI-DLC stage. The vendored AI-DLC rules have no
knowledge of them.

- Everything is IaC, deployed through GitHub. No click-ops.
- Serverless-first, region `us-east-1`. Lambda means container images.
- Secrets live only in AWS Secrets Manager. The repository is public and secret scanning
  is disabled by enforced org policy — never write a credential to any file.
- `main` is PR-only, one human approval, enforced by branch protection.
- All four `cornell:*` tags on every AWS resource.
- Stack names follow `<application>-<environment>-<name>`.
- Every CloudFormation template is registered in `pipeline/stacks.yml`, and every
  `deployed_by: pipeline` entry has a matching action in `pipeline/pipeline.yml`.
- `aidlc-rules/` is a verbatim vendored copy. Do not edit anything under it.

## Stage Progress

### 🔵 INCEPTION PHASE

- [x] Workspace Detection
- [x] Reverse Engineering
- [x] Requirements Analysis
- [x] User Stories — **SKIP** (infrastructure template; single persona; no acceptance criteria beyond
      requirements). User may still request it.
- [x] Workflow Planning
- [x] Application Design — **COMPLETE** (5 artifacts; Security Baseline verified, no blocking findings)
- [ ] Units Generation — **EXECUTE** (next)

### 🟢 CONSTRUCTION PHASE

- [ ] Functional Design — **EXECUTE**
- [ ] NFR Requirements — **EXECUTE**
- [ ] NFR Design — **EXECUTE**
- [ ] Infrastructure Design — **EXECUTE**
- [ ] Code Generation — **EXECUTE**
- [ ] Build and Test — **EXECUTE**

### 🟡 OPERATIONS PHASE

- [ ] Operations — PLACEHOLDER

## Current Status

- **Lifecycle Phase**: INCEPTION
- **Current Stage**: Units Generation — Part 1 (Planning), **at the answer gate**
- **Next Stage**: Units Generation Part 2, then CONSTRUCTION
- **Status**: ⏸️ **PAUSED overnight at the user's request.** Part 1 plan **APPROVED**; Part 2 generation
  **not started**.
- **Resume with**: `docs/AIDLC-TURNOVER-2026-08-04.md` — written for a fresh session, covering the next action,
  every decision made, the accumulated gotchas, and what not to reopen.
- **Next action**: read `aidlc-docs/inception/plans/unit-of-work-plan.md`, then generate the three unit
  artifacts. **No questions outstanding.**

### Units Generation decisions

**Mob-style execution** (whole cross-functional team, per the brief) · **one PR** · **everything in the dev
environment**, single identity · **the team owns U0**. Ten remaining questions took their defaults.

**Two revisions forced by those answers, applied to the plan:**

1. **Parallelism withdrawn.** Mob construction is serial — one unit at a time, whole team. This makes the
   risk-retirement ordering *more* important, and means each unit should end in something a non-engineer can
   evaluate. **U5 (bot says hello) and U7 (streaming) are the mob checkpoints**; U1–U3 are one stretch of
   plumbing. U0 is the exception — non-AWS, needs admin credentials, cannot be mobbed.
2. **One PR means the build path is first exercised on merge**, because `Environment=main` and the pipeline
   only runs on `main` — a PR branch does not trigger it. Mitigations: validate the Dockerfile locally with
   `docker buildx build --platform linux/arm64`, and expect one corrective merge.

**Units are therefore sequencing guidance, not PR boundaries.**

### Corrections from the Entra CLI research (2026-08-04)

`docs/teams-chatbot-docs/Entra CLI Automation - Research 2026-08-03.md` corrected two recorded items:

- **FR-7a added** — the manual Azure messaging-endpoint update is **not** necessary; `az bot update --endpoint`
  is automatable, so a post-deploy step pushes the stack output. Click-ops concession withdrawn.
- **§9 rationale sharpened** — manual Microsoft provisioning is right because the **catalog publish is
  delegated-only by documented design** and the unautomatable steps are **one-time per bot**, not because
  Terraform was out of scope for time. This changes whether the decision should be revisited: it should not.
- **A Terraform stage argued against** — `azuread_application_password` writes the secret into Terraform state,
  colliding with Secrets-Manager-only. A script writing straight to Secrets Manager avoids it.
- **R-3 revised** — a **certificate** instead of a client secret removes the silent-expiry risk; contained
  entirely within `TokenProvider`. Decision deferred to Infrastructure Design (`application-design.md` §6a).

### Application Design decisions on record

Q1 separate worker · Q2 async invoke · Q3 channel-agnostic agent · Q4 normalised envelope · Q5 streaming ·
Q6 DynamoDB idempotency · Q7 agent reads own history · Q8 shared module · Q9 JWT local but self-contained ·
Q10 Python 3.12/ARM64 · Q11 one Dockerfile two targets · Q12 generic message + correlation ID ·
Q13 no house style

**Three units, two images**: Front Door (Lambda + function URL) → Worker (Lambda, async) → Agent (AgentCore).
**Worker timeout must be set explicitly** — the 3-second default would truncate every reply.

### Workspace Detection

- [x] Workspace Detection - Completed 2026-08-03T18:06:09Z

### Reverse Engineering Status

- [x] Reverse Engineering - Completed 2026-08-03T18:06:09Z
- **Artifacts Location**: `aidlc-docs/inception/reverse-engineering/`
- **Approval**: Approved 2026-08-03T18:31:00Z

### Requirements Analysis Status

- [x] Intent analysis complete — New Feature (new blueprint) with a pending Migration
      decision; cross-system scope; Complex; **comprehensive** depth
- [x] Clarifying questions created — `aidlc-docs/inception/requirements/requirement-verification-questions.md`
      (25 questions, 7 sections; extension opt-ins are Q23-Q25)
- [x] Research note created — `aidlc-docs/inception/requirements/agentcore-placement-note.md`
      (Bedrock AgentCore placement; ingress gap explained; CloudFormation availability confirmed)
- [x] DevOps question set created — `aidlc-docs/inception/requirements/devops-questions.md`
      (22 questions for the platform/DevOps owner, awaiting answers)
- [x] Q3, Q7 and Q9 amended 2026-08-03 with AgentCore-aware options and notes
- [x] Prototype analysed — `aidlc-docs/inception/requirements/prototype-reference-implementation.md`
      (n8n export; 10 mechanics confirmed known-good, 2 defects found, 9 requirements derived)
- [x] DevOps short list answered 2026-08-03 — Lambda ingress confirmed, dev tenant with full
      control, AgentCore available; **VPC question open, assumption recorded**; follow-ups A/B/C raised
- [x] AWS account reconnaissance (read-only) — `aidlc-docs/inception/requirements/account-reconnaissance.md`.
      Follow-up A resolved as **A2** (AgentCore service enabled, no runtime deployed → blueprint
      must create one → ARM64 build on critical path). Bootstrap/pipeline/hello-world all deployed
      and green; `cu-aaii` connection `AVAILABLE`. Tag values observed. **New constraint: no Route 53
      zone and no ACM certificate in the workshop account.** Bedrock per-account model entitlement
      still unverified.
- [x] LiteLLM gateway analysed — `aidlc-docs/inception/requirements/model-access-options.md`.
      Cornell operates an Anthropic-compatible gateway; it composes with AgentCore rather than
      competing. **No embeddings model in its catalogue**, so Bedrock entitlement stays mandatory
      if Q3 selects retrieval. New **Q26** added (Section 8) for the model-access decision.
- [x] **Q26 ANSWERED — option B, hard constraint.** All model traffic must route through the
      LiteLLM gateway; it is how Cornell gets the full model list and **medium-risk data
      handling**. Consequences in `model-access-options.md` §7 — including that **Q3 option D
      (Bedrock Knowledge Base retrieval) cannot be built as specified** because the gateway
      exposes no embeddings model. Medium-risk classification also weakens the no-VPC assumption
      and the `AuthType: NONE` ingress choice.
- [x] Plain-language ingress explainer written for administrators —
      `aidlc-docs/inception/requirements/ingress-explained.md` (12 questions grouped by which
      admin can answer them)
- [x] **Q7 ANSWERED — option A**: Lambda function URL, free AWS-provided address. No DNS or
      certificate work; admin questions 5-6 withdrawn. URL-stability constraints recorded
      (deterministic `FunctionName`, URL as stack output, stack rebuild costs one manual Azure edit).
- [x] **Q8 ANSWERED — option A**: synchronous reply with a fast "lite" model
      (`claude-haiku-4-5`). Three caveats recorded: container-image cold-start tail risk,
      idempotency on activity `id` to prevent duplicate replies, and a recommended ~4s-timeout
      hybrid fallback. **May remove AgentCore from v1**, which would take the ARM64 build off the
      critical path.
- [x] Guard confirmed in scope — the nine JWT/handler requirements in
      `prototype-reference-implementation.md` §6 stand.
- [x] **CORRECTED**: the gateway *does* offer 12 embedding models. The earlier "none available"
      finding was an artifact of a LiteLLM virtual key scoped to `llm_api_routes`. New requirement:
      the bot's gateway key must be scoped for **embeddings as well as chat**.
      `AWS::Bedrock::KnowledgeBase` nonetheless remains unusable under the routing rule (it calls
      Bedrock embeddings internally, including on the user's query text) — routes R1/R2/R3 recorded,
      R2 the safe default.

- [x] **AgentCore MANDATED** (Team E; "it should be CloudFormation" — Marty Sullivan, Principal SA
      per the participant brief). My earlier observation that v1 might not need AgentCore is
      **withdrawn**. ARM64 container build is back on the critical path. CloudFormation support
      already verified. See `agentcore-mandate-and-critical-path.md`.
- [x] Workshop brief read — `docs/Participant Brief - Invited Attendees (2).html`. Teams-fronted
      chatbots is an **explicitly named target blueprint**; workshop is 2026-08-03/04; keystone is a
      "Cornell Builder" that deploys blueprints. Brief's "reusable platform blueprints" framing
      **informs Q2 toward a generic `teams-bot`** but does not answer it.
- [x] Critical path specified: (1) `pipeline.yml:203-208` `LINUX_CONTAINER`/x86 → `ARM_CONTAINER`
      + aarch64, (2) add a namespaced Build stage — none exists today, (3) Dockerfile with a named
      target, arm64, port 8080, `/ping` + `/invocations`, (4) plumb `CONTAINER_DIGEST` via
      `ParameterOverrides`, (5) blueprint template, (6) register in `stacks.yml` **and**
      `pipeline.yml`. **Steps 1-4 have never executed; ECR holds zero images.**
- [x] Critical path steps 1, 4, 5, 6 **approved**. Step 2 clarified: the build *machinery* is all in
      this repo (`codebuild.yml`, `ContainerBuildProject`, `ContainerRepository` — live as ECR
      `aidlc-main`); only the ~15-line `Stages:` entry is missing. Step 3 best practices researched —
      AWS reference Dockerfile recorded; needs a **`uv.lock`**, which also closes RE tech-debt item 4.
- [x] **Escalation 1 RESOLVED** — Marty: open a PR on this repo, he reviews. Residual: call the Build
      stage out in the PR description (Team E may also add one), and the pipeline self-deployment
      recovery path is still undocumented.
- [x] **Escalation 2 ANSWERED with research** — budget is **10-15s, channel-dependent**, enforced by
      the connector, overrun shows `504:GatewayTimeout`, not extendable. **Teams response streaming**
      found as a better third option: no timeout exposure, no model constraint, feels faster, and
      **dissolves the AgentCore cold-start tension**. See `response-delivery-and-timeouts.md`.
- [x] ~~Q4 answered option A (personal only)~~ **REVISED 2026-08-03 — multi-chat IS IN SCOPE.**
      **Q4 reopened**: "multichat" has three-plus distinct meanings (B/C/D/E) with sharply different
      cost and risk; awaiting the specific choice. Two consequences apply regardless: **both delivery
      paths must be built in v1**, and the **med-risk-in-shared-scope policy question is now live and
      blocking** (was deferrable only while personal-only).
- [x] Research docs re-read in full now that multi-party is in scope. New findings: **`replyToId`
      filtering requires persistence → Q9 "stateless" is incompatible with thread replies**; the tenant
      can **disable RSC** (admin question 13); **group-chat-without-@mention is unresearched** (Q4
      option E); RSC does **not** force org publish; missed replies cannot be backfilled; in-place
      manifest updates do not re-consent.
- [x] **Q8 ANSWERED — streaming** (supersedes the earlier option A; original left visible, not
      overwritten). **Lifts the "lite model" constraint** — model choice is now about answer quality —
      and **resolves the AgentCore cold-start tension**.
- [x] Multi-party expansion costed — `aidlc-docs/inception/requirements/multi-party-scope-path.md`.
      **One v1 action item: build the delivery seam** (dispatch on `conversation.conversationType`)
      while implementing only streaming. ~20-30 lines now vs rewriting the response path later.
      Tier 1 (@mention) small-moderate; Tier 2 (RSC) moderate with an **untested
      `webApplicationInfo.id` install risk** to test first.

### Answered so far

Q7 (ingress), Q8 (streaming), Q26 (model access).

**Outstanding: Q1-Q6, Q9-Q25.** Priority order:

1. **Q3 REFRAMED by the user, and the reframe is correct** — the blueprint is a *template the keystone
   instantiates*, not a bot, so its behaviour is a deployment parameter. Q3 rewritten as a **capability
   tier** choice (A prompt-configured / B +retrieval / C +tools), with **Tier A recommended**, plus new
   **Q3b** for the one or two concrete demo configurations. See
   `blueprint-configuration-surface.md`.
   - **MCP question answered**: the MCP *decides* config and does not *store* it — it creates deployment
     repos, so config is CFN parameters checked into git, and the MCP is never in the request path.
   - Constraint recorded: CFN parameter values cap at 4096 chars, SSM standard at 4 KB — long system
     prompts belong in S3 with the parameter holding the key.
   - **Knowledge Base ("KBB") team owns the vector store** (brief: "Document ETL & batch processing →
     searchable knowledge store"). So **Tier B is an integration, not an implementation** — a stack
     parameter, plus query-side code only if they expose storage rather than search. Tier B is now
     **blocked on an interface that does not exist yet**, which strengthens the Tier A recommendation.
   - Interface must be a **parameter, not `!ImportValue`** — the repo's "blueprints as leaves"
     convention. The MCP supplies the value, since it knows both blueprints.
   - **Five questions for the KB team** in `blueprint-configuration-surface.md` §4b. The two that matter:
     *search or storage only?* and *which embedding model, via the gateway?* — the embedding model **must
     match between ingest and query** or results are silently wrong.

## Open Dependencies

### KB integration — LARGELY RESOLVED 2026-08-04

The KB team is using **Bedrock AgentCore Managed Knowledge Base** (an AgentCore built-in tool, so coherent
with the AgentCore mandate). **The S3 bucket is its data source, not its vector store** — Bedrock owns
chunking, embedding, storage **and retrieval**. See `knowledge-base-integration.md`.

**Tier B for this blueprint collapses to**: one `KnowledgeBaseId` parameter, one IAM statement for
`Retrieve`, and prompt assembly. **No S3 access, no vector store, no embedding code.**

**Firm design requirement**: use **`Retrieve`**, not `AgenticRetrieveStream` — `Retrieve` makes **no FM
invocation** so all generation stays on the gateway; `AgenticRetrieveStream` makes multiple Bedrock FM calls.
(`RetrieveAndGenerate` is unavailable for managed KBs.) Query limit 10,000 chars — truncate deliberately if
history is concatenated.

**Three earlier cautions retired**: embedding-model-match risk **eliminated** (Bedrock embeds both sides);
"search may be unowned" **does not apply**; **R2 recommendation moot** — KB team chose R1, their call.

**Withdrawn from the previous entry**: the `KnowledgeStoreType` enum, the `EmbeddingModelId` parameter, and
the `s3:GetObject`/`s3:ListBucket` requirement. The vector-store CFN verification is no longer relevant here.

**Still open**: the `KnowledgeBaseId` value, and the KB team's timeline. **Tier B is now a plausible stretch
goal rather than a follow-up** — the vector-plumbing argument for deferring it has evaporated.

**Flagged to the KB team** (their risk, not ours): whether a **managed** KB is CloudFormation-deployable at
all — `AWS::Bedrock::KnowledgeBase` is `FULLY_MUTABLE` here but `type: MANAGED` support was **not verified**,
and the docs show only console/CLI. If API-only, their blueprint cannot be pure CloudFormation under Marty's
constraint. Also: embedding model **type** and **chunking strategy** are both **irreversible** after
creation, and `CUSTOM` embedding disables the **managed reranker**.

### Superseded — original KB storage note (record only)

Recorded 2026-08-04 at the user's explicit request; agreed approach is to proceed and adjust later.

**Known**: a **simple S3 bucket**, in our own AWS account, which "will serve the RAG". **Not yet created.**
KB team decisions still outstanding.

**Settled by this**: same-account access (no cross-account policy work); the IAM requirement
(`s3:GetObject`/`s3:ListBucket` scoped to the bucket); a valid parameter shape (bucket name/ARN); no VPC
implication.

**Not settled**: **whether search exists.** A plain S3 bucket is storage, not retrieval. Three possible
bucket contents with very different costs — documents/chunks (embedding + index + search unowned),
precomputed embeddings (we search, using *their* model), or an **S3 Vectors** vector bucket (native search,
confirmed `FULLY_MUTABLE` here — worth raising with them if unevaluated).

**Risk to escalate to Marty**: if the bucket holds plain documents and the KB team considers its work done
there, then chunking, embedding and search are **unowned**, and every consuming blueprint builds its own.

**Mitigation — costs nothing today**: Tier B parameters are **agnostic** — `KnowledgeStoreType`
(`none` | `s3-documents` | `s3-vectors` | `retrieval-endpoint`), `KnowledgeStoreLocation`,
`EmbeddingModelId`. **v1 ships `none`.** Any answer becomes a new branch, not a redesign.

**Not a blocker for v1.** Tier A and the critical path are unaffected.
2. **Q4** — which of B/C/D/E "multichat" means. Now a purely technical choice. D and E carry unknowns
   (untested `webApplicationInfo.id` install risk; unresearched chat-scoped RSC).
3. **Q9** — state, constrained: "stateless" is unavailable if Q4 lands on D or E.
4. Q1, Q2, Q5, Q6, Q10-Q25.

### Confirmed constraints

- **Medium-risk data is approved to and from the gateway** (2026-08-03, reaffirmed). Gateway-routed
  traffic is compliant, so **shared scopes need no policy escalation** and admin question 14 is
  withdrawn. Q3/Q20 and Q4 carry no compliance dependency.
- **R2 is the recommended retrieval route** if Q3 selects retrieval — not for medium-risk reasons but
  because `AWS::Bedrock::KnowledgeBase` structurally bypasses the gateway, which the Q26 mandate
  forbids. R2 needs no exception granted by anyone.
- **Vector store verified CloudFormation-deployable** in the account, all `FULLY_MUTABLE` in us-east-1:
  `AWS::S3Vectors::VectorBucket` + `::Index` (**recommended** — cheapest, no cluster, no VPC),
  `AWS::OpenSearchServerless::Collection`, `AWS::RDS::DBCluster` (Aurora+pgvector, but **needs a VPC**).
  Gateway embeddings are ~$0.02/1M tokens — effectively free at this scale.
- [x] **Answers received and validated for contradictions** — 2026-08-04. No contradictions found. Two
      earlier tensions both resolved (Q8 synchronous vs AgentCore → streaming; Q26 gateway vs Bedrock KB
      embedding → KB team owns it, `Retrieve` chosen).
- [x] **`requirements.md` generated** — 2026-08-04. Tier A, Q4=C, streaming, PR to `main`.
      Security Baseline compliance evaluated: **no blocking findings**; three items compliant via
      compensating control or documented exception (SECURITY-02, -07, -11).
- [ ] **Awaiting user approval**

### Remaining INCEPTION Stages

- [ ] Requirements Analysis (in progress — at answer gate)
- [ ] User Stories (conditional)
- [ ] Workflow Planning
- [ ] Application Design (conditional)
- [ ] Units Generation (conditional)

## Extension Configuration

| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes | Requirements Analysis |
| Resiliency Baseline | No | Requirements Analysis |
| Property-Based Testing | No | Requirements Analysis |

Full rules loaded for Security Baseline only
(`aidlc-rules/aws-aidlc-rule-details/extensions/security/baseline/security-baseline.md`), per the deferred
rule-loading instruction. Resiliency and property-based testing full rules **not** loaded.
