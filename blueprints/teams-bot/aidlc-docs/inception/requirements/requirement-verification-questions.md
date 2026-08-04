# Requirements Verification Questions — Teams Chatbot

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none
of the options match, choose the last option (**Other**) and describe your preference after the
tag. Add free-text notes alongside a letter wherever it helps — more context is always useful.

---

## ⛔ GATE PASSED — Consolidated Answers, 2026-08-04

All questions are answered. Explicit answers are recorded at each question below; the remainder were
answered by blanket approval of the recommended defaults (*"All the rest is good homie"*), and are recorded
here to make that explicit rather than implied.

| Q | Answer | Source |
| --- | --- | --- |
| Q1 | Workshop deliverable — a real platform component built during the two days | brief + context |
| **Q2** | **`teams-bot`** — generic, reusable, not course-specific | default approved |
| **Q3** | **Tier A** — prompt-configured. Tier B a stretch goal if the KB lands | explicit |
| Q3b | Demo values are **deployment-time parameters**, not blueprint design — chosen at deploy | derived from the Q3 reframe |
| **Q4** | **C** — personal + group chat + channel, `@mention` required. No RSC, no unknowns | explicit |
| Q5 | Workshop participants and the platform team | default approved |
| Q6 | **A** — AWS-native; n8n was a research spike, discarded | default approved |
| **Q7** | **A** — Lambda function URL, free AWS-provided address, `AuthType: NONE` + JWT in handler | explicit |
| **Q8** | **Teams response streaming** in personal chat; ack + typing + single reply elsewhere | explicit |
| Q9 | Conversation history via **AgentCore Memory** | default approved |
| Q10 | **Dev tenant**, full control | explicit |
| Q11 | **Single-tenant Entra app + client secret** in Secrets Manager | default approved |
| Q12 | **Manual runbook** for the Microsoft side; Terraform later | default approved |
| Q13 | Azure Contributor — held (dev tenant, "complete control") | explicit |
| Q14 | Teams admin — held, org publish self-service | explicit |
| Q15 | Secret placed manually into Secrets Manager at `aidlc/main/teams-bot-*` | default approved |
| Q16 | Rotation **out of scope** for v1; expiry noted as a risk | default approved |
| **Q17** | Container build wired **in this same PR** | default approved |
| **Q18** | **PR pushed to `main`.** No parallel environment | explicit |
| **Q19** | **DEFERRED — tagging doc incoming from the user.** The four `cornell:*` tags remain the known requirement; automated tag validation is **not** added in this PR pending that doc | explicit |
| Q20 | Medium-risk permitted; gateway-routed traffic is compliant. No message bodies in logs by default | explicit + default |
| Q21 | Workshop scale. No latency SLA — streaming removes the constraint | default approved |
| Q22 | No availability SLA for v1 | default approved |
| **Q23** | Security Baseline — **ENABLED** | default approved |
| **Q24** | Resiliency Baseline — **not enabled** | default approved |
| **Q25** | Property-Based Testing — **not enabled** | default approved |
| **Q26** | **B** — LiteLLM gateway for all model traffic. Hard constraint | explicit |

**Contradiction analysis performed** — no contradictions found among the answers. Two tensions were
identified earlier and both are resolved: Q8's original synchronous answer versus the AgentCore mandate
(resolved by moving to streaming), and Q26's gateway mandate versus Bedrock Knowledge Base embedding
(resolved by the KB team owning that decision, with `Retrieve` chosen to confine Bedrock's footprint).

Requirements generated at `aidlc-docs/inception/requirements/requirements.md`.

---

## Intent Analysis

| Dimension | Assessment |
| --- | --- |
| **User request** | "using the AI DLC start inception for Teams chatbot use information found here: `/home/fermin/codeprojects/ai-dlc-workshop/docs/teams-chatbot-docs`" |
| **Request type** | New Feature (new blueprint), with a possible Migration aspect (n8n prototype to governed deploy path) pending Q5 |
| **Scope estimate** | **Cross-system** — AWS, Microsoft Entra ID, Azure Bot Service, Microsoft Teams |
| **Complexity estimate** | **Complex** |
| **Depth selected** | **Comprehensive** |

**Why comprehensive**: the research documents settle the *Microsoft* side in real detail, but
the reverse engineering found seven things a Teams bot needs that this repository has never
done — public HTTPS ingress, deployed compute, an exercised container build, a stack that reads
a secret, any non-AWS provisioning, a runtime dependency policy, and tag validation. On top of
that, the validated prototype runs on self-hosted n8n, which conflicts with the repository's
hard constraints. Those are requirements decisions, not design details, and getting them wrong
is expensive because every merge to `main` deploys to a shared AWS account.

---

# Section 1 — Business Context and Scope

## Question 1

Today is **3 August 2026** — day one of the workshop this repository was built for. What is the
Teams chatbot's relationship to that workshop?

A) **Workshop deliverable** — participants build it during the workshop; INCEPTION artifacts are
the starting material they work from

B) **Workshop demo** — it needs to be working before or during the workshop as a demonstration
of the blueprint layer

C) **Post-workshop work** — the workshop is unrelated timing; this is the next real blueprint and
has no deadline pressure from it

D) **Reference design only** — produce the design artifacts now, decide later whether and when to
build

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 2

`CLAUDE.md` lists `blueprints/course-chatbot/` under "deliberately not built", described as
"managed Bedrock Knowledge Base, Teams bot, Strands agent". How should this work be scoped
against that?

A) **One blueprint, `course-chatbot`** — the Teams bot is one facet of it, and Knowledge Base and
agent arrive in the same blueprint

B) **A standalone `teams-bot` blueprint** — the Teams channel is its own reusable building block;
`course-chatbot` composes it later alongside the Knowledge Base and agent

C) **Start standalone, fold in later** — build `teams-bot` now, merge it into `course-chatbot`
once the other pieces exist

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Note**: this determines the `cornell:blueprint` tag value, the directory name, the
`pipeline/stacks.yml` key, and the stack name — all of which are load-bearing and awkward to
change after a first deployment.

## Question 3

> **REFRAMED 2026-08-03. The original question was the wrong shape — see below.** You observed that we
> don't know what the bot does because *the builder* specifies that at deployment time. That is correct,
> and the options below were written on the false assumption that the blueprint *is* a bot rather than a
> template that gets instantiated. Full analysis in `blueprint-configuration-surface.md`.
>
> **Answer to your MCP question**: the MCP **decides** the configuration; it does not **store** it.
> `CLAUDE.md` describes `builder-mcp/` as searching blueprints and *creating deployment repos* — both
> build-time actions. So it writes the parameter values into a repo, that repo's pipeline deploys the stack,
> and the running bot reads its config from environment variables or SSM. **The MCP is never in the request
> path.** Usefully, this means the bot's personality is a reviewable file in git, not a database row —
> exactly consistent with the no-click-ops constraint.
>
> **So the blueprint's configuration surface is its CloudFormation parameters.** One constraint to know
> now: CFN parameter values cap at **4096 characters** and SSM standard tier at 4 KB, so a long system
> prompt belongs in S3 with the parameter holding the object key.
>
> **What the reframe does not remove**: the template must be able to deploy the most capable variant it
> advertises. So the real question is which capability tiers v1 supports.

### Q3 (revised) — which capability tier does v1 support?

A) **Tier A — prompt-configured.** Parameters: system prompt, model id, greeting, Teams scopes. No new
data stores. Covers "a bot that helps with X" where X is general knowledge plus instructions.

B) **Tier B — A plus retrieval.** ~~Adds a corpus pointer and the whole R2 pipeline~~ **Revised
2026-08-03: the Knowledge Base ("KBB") team owns the vector store**, per the brief's "Document ETL & batch
processing → searchable knowledge store" blueprint. So Tier B is an **integration, not an
implementation** — a stack parameter holding their knowledge-store identifier, plus query-side code only
if they expose storage rather than search. Covers "a bot that answers questions about *our documents*".

**Update 2026-08-04 (second) — the KB design is now known, and Tier B is far cheaper than stated above.**
The KB team is using **Bedrock AgentCore Managed Knowledge Base**. The S3 bucket is its **data source**, not
its vector store; Bedrock owns chunking, embedding, storage **and retrieval**. Full analysis in
`knowledge-base-integration.md`.

**Tier B for this blueprint reduces to:**

| Item | Detail |
| --- | --- |
| One stack parameter | `KnowledgeBaseId`, supplied by the MCP |
| One IAM statement | `Retrieve` on that knowledge base ARN |
| Agent code | call `Retrieve`, put chunks in the prompt, generate via the gateway |
| **No** S3 access, **no** vector store, **no** embedding code | all owned by the KB team's blueprint |

**One firm design requirement**: use **`Retrieve`**, not `AgenticRetrieveStream`. `Retrieve` makes **no
foundation model invocation**, so all generative inference stays on the gateway; `AgenticRetrieveStream`
makes *multiple* Bedrock FM calls. (`RetrieveAndGenerate` is not available for managed KBs at all.)

**Three earlier cautions retired**: the embedding-model-match silent-failure risk is **eliminated** (Bedrock
embeds both sides); "search may be unowned" **does not apply**; and the R2 recommendation is **moot** — the
KB team has chosen R1 and that is theirs to make.

**Consequence for this question**: the argument for deferring Tier B was several hundred lines of vector
plumbing, and that argument has evaporated. The only remaining reason to defer is that **the knowledge base
does not exist yet**. Tier A still ships first because it unblocks the hard path — but **Tier B is now a
plausible stretch goal rather than a follow-up release**, if the KB team produces something inside the two
days. Five questions for the Knowledge Base team are in
`blueprint-configuration-surface.md` §4b — the two that decide our work are **"do you expose search or
only storage?"** and **"which embedding model, through the gateway?"** (the same model must be used at
ingest and query, or results are silently wrong).

Note the interface must be a **parameter, not a CloudFormation import** — the repo's "blueprints as
leaves" convention. The MCP knows both blueprints, so it is the natural place to supply the value.

C) **Tier C — B plus tools.** Adds tool/MCP endpoints the agent may call. Agentic loop, tool auth, error
handling. This is the brief's own example ("automate my team's access to backend tools and reporting").

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A.** It is a genuinely reusable blueprint — most internal chatbot requests really are a
prompt and a model — and it already exercises every hard path that is a first for this repository: Teams
ingress, JWT validation, streaming, AgentCore, the gateway, secrets, the four tags, and the ARM64 container
build. None of those gets easier by adding retrieval on day one. Design the parameter surface so B and C
slot in later without redesign.

### Q3b — what are the one or two demo configurations?

You mentioned giving it one or two options for the demo. Please specify, concretely, for each: **system
prompt (or its gist), model id from the gateway catalogue, and Teams scopes.**

[Answer]:

Two visibly different bots deployed from one blueprint demonstrates the keystone idea completely.

---

<details>
<summary>Original Q3, superseded — retained for the record</summary>

What must the bot actually *do* in its first deployed version?

A) **Echo / health check** — receive an activity and reply with something trivial, proving the
whole Teams-to-AWS path end to end and nothing more

B) **Fixed-response assistant** — answer from a small hardcoded or configuration-driven set of
responses; no model inference

C) **Bedrock model passthrough** — forward the message to a Bedrock model and return the reply;
no retrieval

D) **Retrieval-augmented answers** — Bedrock Knowledge Base retrieval over course content, then
a model reply

E) **Agentic** — a Strands agent with tool use, hosted on Bedrock AgentCore Runtime

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Note added 2026-08-03**: see also **Q26** — this question also determines whether Bedrock model
entitlement is mandatory. If you select D (retrieval), it is, because Bedrock Knowledge Bases
require a Bedrock embeddings model and Cornell's LiteLLM gateway offers none.

**Note added 2026-08-03**: this question decides whether Bedrock AgentCore is involved at all.
A and B need no model access whatsoever; C needs Bedrock inference but no agent runtime; D and E
are where AgentCore earns its place. AgentCore is confirmed CloudFormation-deployable in
`us-east-1`, so choosing D or E does not require a click-ops exception — but it does require
activating the ARM64 container build path (see `agentcore-placement-note.md` and Q17).

**Both notes above are partly obsolete**: the gateway *does* offer embedding models (the earlier finding
was a key-scope artifact), and AgentCore is now mandated regardless of capability. Retained for the record.

</details>

## Question 4

Which Teams conversation scopes must the first version support? The research is explicit that
sideloading reaches **personal scope only**, and that group chat and channel use require
publishing to the organization with Teams admin approval — a hard prerequisite, not an
optimization.

A) **Personal chat only** — one-to-one with the bot; sideloadable, no admin approval needed

B) **Personal + group chat**

C) **Personal + group chat + channel, `@mention` required** — the bot only sees messages that
mention it

D) **Personal + group chat + channel, including thread replies without `@mention`** — needs
resource-specific consent (`ChannelMessage.Read.Group`), team-owner consent at install, and an
app reinstall in each team

X) Other (please describe after [Answer]: tag below)

[Answer]: ~~**A**~~ **REVISED 2026-08-03 — "we'll add multichat". Multi-party scopes are IN SCOPE.**
Original answer (personal only) superseded and left visible for the record.

**Please pick one — "multichat" has three materially different meanings** and the cost and risk differ
sharply. Full costing in `multi-party-scope-path.md`.

B) **Personal + group chat, `@mention` required** — cheap. Note that group chats are `@mention`-gated
exactly as channels are; Microsoft's rule covers "a group or channel".

C) **Personal + group chat + channel, `@mention` required** — Tier 1. Manifest scopes plus the
`supportsChannelFeatures` placement traps, both conversation-id formats, and the second delivery path.
No Entra changes, no unknowns.

D) **As C, plus thread replies without `@mention` in channels** — Tier 2, needs RSC
`ChannelMessage.Read.Group`. Adds: the **untested `webApplicationInfo.id` install risk** your own
research flags as an open checkbox, an app **reinstall per team**, firehose traffic volume, and a
**persistence requirement** (see Q9 note).

E) **As D, plus group chats without `@mention`** — **not covered by any existing research.**
`ChannelMessage.Read.Group` is *team*-scoped and a group chat is not a team, so this needs a
chat-scoped RSC permission that has not been investigated here. Choosing this means accepting an
unresearched unknown.

[Revised answer]:

**Two things now apply regardless of which you pick**:

1. **Both delivery paths must be built in v1.** Streaming is one-on-one only, so the
   acknowledge-plus-typing-plus-single-reply path has to actually work, not just be anticipated. The
   §1 seam is no longer sufficient on its own.
2. **The medium-risk-data-in-a-shared-scope question is now live and blocking.** A bot reply in a
   channel or group chat is visible to every member, including people who may not be entitled to the
   content, and the bot cannot know who is entitled to what. Personal-only was what allowed this to be
   postponed. That option has been given up, so it needs an answer from whoever owns the medium-risk
   classification before shared scopes are enabled. This is a policy decision, not an engineering one,
   and it is the single most important open item created by this change.

**Note**: the path to group chat and channel is costed in `multi-party-scope-path.md`. One action item
lands in v1 from it — **build the delivery seam now** (dispatch on `conversation.conversationType`)
even though only the streaming strategy is implemented. That is ~20-30 lines today versus rewriting
the response path later, because the two delivery patterns differ in shape: many cumulative updates
versus one final message.

Personal-only also **defers two genuinely hard non-code questions** rather than dodging them: that a
bot reply in a channel is visible to every channel member, which under a medium-risk classification is
a policy decision; and that conversation state stops being per-person once a conversation has several
participants.

## Question 5

Who are the intended end users of the first deployed version?

A) **Just you** — a single-user proof of the path

B) **The platform team** — a handful of internal testers

C) **Workshop participants** — a known, bounded group during the workshop

D) **A pilot course** — real students and faculty in one course

E) **Campus-wide** — generally available to Cornell users

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 2 — Target Architecture

## Question 6

The prototype validated in the research runs on **self-hosted n8n** (workflow `UpYSG156S63vb4HZ`),
with credentials in n8n's own Credentials store. That conflicts with three of this repository's
hard constraints: everything is IaC deployed through GitHub, serverless-first on AWS, and secrets
live only in AWS Secrets Manager. What is the target?

A) **AWS-native, n8n discarded** — rebuild the bot logic as AWS serverless compute; the n8n
workflow was a research spike and its value was the knowledge, not the code

B) **AWS-native, n8n kept as a separate research tool** — same as A, but n8n stays alive outside
this repository for future spikes

C) **AWS thin front door, n8n backend** — AWS terminates HTTPS and validates the inbound JWT, then
forwards to n8n for the logic. Requires accepting that some logic and some credentials live
outside the governed path

D) **n8n remains the whole backend for now** — document it, register nothing in this repository
yet, and revisit

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Note**: A and B are the only options fully inside the stated constraints. C and D are
legitimate choices, but they need an explicit, recorded decision to accept a documented exception
rather than an assumption on my part — which is why this is a question and not a design.

## Question 7

Azure Bot Service POSTs Bot Framework activities to a **public HTTPS messaging endpoint**. This
repository has no ingress of any kind, so whatever is chosen here is its first. Note that
`CLAUDE.md` states Lambda here means **container images**, and the ECR/CodeBuild path is defined
but has never been invoked.

A) **Lambda function URL** — simplest possible public HTTPS; no API Gateway, no VPC, IAM-free
`AuthType: NONE` with JWT validation in the handler

B) **API Gateway HTTP API + Lambda** — a managed front door with throttling and access logging in
front of the same handler

C) **API Gateway REST API + Lambda** — as B, plus request validation, WAF association and usage
plans if those are wanted

D) **ALB + Fargate** — a long-running container instead of Lambda; avoids cold starts and the
container-image Lambda path entirely, but introduces a VPC

E) **Point Azure Bot Service directly at a Bedrock AgentCore Runtime endpoint** — no AWS front
door at all, relying on AgentCore's own `CUSTOM_JWT` authorizer. Listed for completeness because
it has been raised; **researched and not recommended** — see the note below

X) Other (please describe after [Answer]: tag below)

[Answer]: **A — ANSWERED 2026-08-03.** Lambda function URL, using the **AWS-provided address** (no
custom hostname or certificate). Confirms `AuthType: NONE` with JWT validation in the handler, and
confirms the guard is in scope. See the URL-stability constraint recorded below.

**URL stability, verified against AWS documentation 2026-08-03** — this is the cost of choosing the
free address, and it is a real operational constraint rather than a theoretical one:

- The URL **survives function updates** — code, environment, configuration, memory. Ordinary
  redeploys through the pipeline will not change it.
- Deleting the function URL gives a **permanently different** address: *"When you delete a function
  URL, you can't recover it. Creating a new function URL results in a different URL address."*
- Deleting the **function** and immediately recreating one with the same name **may** remap the
  original URL — AWS words this as *"it is possible that the original function URL is mapped to the
  new function"*. That is a race, not a guarantee, and must not be designed around.

**Therefore, as requirements**: the function's `FunctionName` must be deterministic and stable, so
CloudFormation never replaces the function; the URL must be a **stack output** rather than a value
a human transcribes; and it must be accepted that deleting and recreating the stack means one manual
edit of the messaging endpoint in Azure. Worth stating plainly because a workshop is exactly the
setting where a stack gets torn down and rebuilt.

**Note added 2026-08-03**: option E was researched properly rather than dismissed, and the
findings are in `agentcore-placement-note.md`. In short: AgentCore Runtime *is* publicly reachable
and *does* support OAuth JWT inbound auth, so the idea is not unreasonable. It fails on four
counts, of which the first is serious — AgentCore's generic JWT authorizer cannot assert that the
token's `serviceurl` claim matches `body.serviceUrl`, which is the specific control that prevents
an attacker with a valid token from redirecting the bot's replies. It would be lost **silently**.
Additionally, Azure Bot Service cannot produce SigV4, and AgentCore's streaming/long-running
response model conflicts with Teams' need for an immediate bare `200 OK`.

AgentCore remains the recommended home for the *agent logic*, invoked with SigV4 from behind
whichever front door is chosen in A–D. The front door stays deliberately thin: validate the JWT,
acknowledge, hand off.

## Question 8

Teams retries when the messaging endpoint is slow or returns anything other than `200 OK`. If the
bot's real work (retrieval, model inference) takes longer than a fast acknowledgement, how should
that be handled?

A) **Synchronous** — do the work and reply within the request; acceptable only if the work is
reliably fast

B) **Acknowledge then reply proactively** — return `200 OK` immediately, do the work
asynchronously, and post the answer as a new activity to the conversation

C) **Acknowledge with a typing indicator, then reply proactively** — as B, plus a visible "the bot
is working" signal

D) **Decide during design** — the answer depends on the capability chosen in Q3

X) Other (please describe after [Answer]: tag below)

[Answer]: **A — ANSWERED 2026-08-03.** Respond synchronously, using a "superfast lite model"
(`claude-haiku-4-5` is available on the gateway: 200K input, 64K output). Recorded with three
caveats below, because the prototype used the acknowledge-then-reply pattern and this is a
deliberate move away from it.

**Caveat 1 — container-image Lambda cold starts are the real risk.** `CLAUDE.md` mandates that
Lambda here means container images, and those initialise measurably slower than zip packages. A cold
request pays container init **plus** the gateway round trip **plus** generation, all inside
Microsoft's patience. Warm requests will be comfortable; the p99 is the exposure. Mitigations, in
increasing cost: keep the image small; cache the JWKS so it is never fetched in the critical path;
provisioned concurrency if the tail proves unacceptable.

**Caveat 2 — synchronous replies need idempotency.** If a response is slow enough that Azure Bot
Service retries, the handler will generate a second answer and the user sees the reply twice. The
prototype never had this problem because it acknowledged first and replied out of band. A
synchronous design must deduplicate on the activity `id`.

**Caveat 3 — the cheap hybrid is worth considering rather than dismissing.** Put a hard timeout of
roughly four seconds on the model call. If it returns in time, reply synchronously exactly as
intended. If it does not, return `200 OK` and deliver the answer as a proactive message instead.
This preserves the fast-path intent, removes the tail risk entirely, and is a small amount of code.
It is the one place where a few lines now avoids a failure mode that is unpleasant to diagnose from
Teams.

**REOPENED 2026-08-03 — please reconsider. The timeout was researched and there is a better option
than any of A-D above.**

Verified: the budget is **10-15 seconds depending on channel**, enforced by the Bot Service
connector, and overrun shows the user a **`504:GatewayTimeout`**. It cannot be extended. So
answering "all at once" with a slower model is not available.

But **Teams response streaming** is generally available and is a third pattern: return `200 OK`
immediately, then send outbound updates that Teams renders progressively into one message — an
informative progress bar first, then the answer appearing as it generates. **No timeout exposure, no
model constraint, and it feels faster than the synchronous path** because the user sees activity
within about a second.

It also **dissolves the AgentCore cold-start problem entirely** — the clock the two container cold
starts were racing no longer exists.

Two constraints that matter:

- **Streaming works only in one-on-one chats**, which makes **Q4 load-bearing**. Group chat and
  channel scopes need the acknowledge-plus-typing-indicator pattern instead, so those scopes mean
  two delivery paths behind one agent.
- Updates must be **cumulative** ("A brown" → "A brown fox" → …), rate-limited to **1/second** with
  1.5-2s token buffering, and `streamSequence` must **not** be set on the final message.

**Suggested revision**: stream if Q4 is personal-chat-only; stream plus a fallback path if Q4 is
broader. Keeping option A is defensible as a deliberate first step for shipping today — with a ~4s
timeout and proactive fallback — but it is a stepping stone, not the destination. Full analysis in
`response-delivery-and-timeouts.md`.

[Revised answer]: **STREAMING — ANSWERED 2026-08-03.** Use Teams response streaming. Supersedes the
earlier option A. With Q4 = personal chat only, streaming is available and v1 needs one delivery path.

Consequences now settled: **no timeout exposure** (the inbound request is acknowledged in
milliseconds); **no model constraint** — the "superfast lite model" is no longer required, so model
choice can be made on answer quality; and the **AgentCore two-cold-start tension is resolved**, since
the clock those cold starts were racing no longer exists.

Still required: cumulative (non-delta) updates, 1 request/second with 1.5-2s token buffering,
sequential calls, `streamSequence` omitted on the final message, and idempotency on the inbound
activity `id`. Plus the delivery seam noted under Q4.

**Consequence worth surfacing: this may remove AgentCore from the first version.** A synchronous
fast-lite-model reply is a Lambda calling the gateway and posting the answer — AgentCore Runtime adds
a network hop and is designed for longer-running agentic work, which is the opposite of this latency
budget. If the first version is a fast direct reply, AgentCore earns its place only when Q3 selects
agentic behaviour or when memory and tool use arrive. **That would take the ARM64 container build off
the critical path entirely.** Recorded as an observation for the design stage, not a decision —
there may be an organisational commitment to AgentCore that outweighs it.

## Question 9

Does the bot need to remember anything between messages?

A) **Stateless** — every activity is handled independently; no conversation history

B) **Conversation history only** — enough context for multi-turn dialogue

C) **History plus per-user preferences** — durable user-scoped state

D) **Decide during design** — depends on Q3

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Note added 2026-08-03 (second) — option A may no longer be available.** If Q4 lands on **D or E**
(thread replies without `@mention`), the bot must filter inbound channel traffic to replies to its *own*
posts. That is done by storing the activity id returned when the bot sends a post and matching it against
each inbound activity's **`replyToId`**. The id exists only in the send-time API response, so **the bot
needs durable storage of its own sent message ids even if it is otherwise stateless.**

It is a small amount of data with an obvious key — possibly satisfiable by AgentCore Memory rather than a
purpose-built table — but "stateless" and "thread replies without `@mention`" are mutually exclusive. The
alternative is to filter on `entities` for a mention of the bot's id, which needs no storage but gives up
the reason for enabling RSC in the first place.

**Note added 2026-08-03**: B and C no longer imply a hand-built DynamoDB table.
`AWS::BedrockAgentCore::Memory` is confirmed available in `us-east-1`, so if Q3 lands on D or E
the state store may come with the agent runtime rather than being built separately. The *storage
mechanism* is a design decision; what is needed here is only whether state is required at all.

---

# Section 3 — Identity and Non-AWS Provisioning

## Question 10

Which Microsoft tenant is the first deployment targeting? The research confirms
`allowedToCreateApps: true` in both the Cornell tenant and the dev tenant, and that Cornell
identity was insufficient for the dev environment.

A) **Cornell tenant** — the real target; needs Cornell Teams admin cooperation for anything
beyond personal-scope sideloading

B) **Dev tenant** — iterate freely where you already hold admin, then repeat in Cornell later

C) **Dev tenant first, Cornell as an explicit second milestone** — same as B, but the Cornell
migration is in scope for this work rather than deferred indefinitely

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 11

How should the bot authenticate outbound to the Bot Framework? Multi-tenant bot creation has been
unavailable since 31 July 2025.

A) **Single-tenant Entra app registration with a client secret** — what the research validated;
the secret must be stored in AWS Secrets Manager and rotated

B) **User-assigned managed identity** — no secret to store or rotate, but not validated in the
research and it ties the bot to Azure-side identity plumbing

C) **Whichever is simpler to get working first, revisit later** — accept a client secret now with
managed identity as a known follow-up

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 12

The Entra app registration, the Azure Bot Service resource with its `MsTeamsChannel`, and the
Teams app manifest are all outside AWS. `CLAUDE.md` designates Terraform-executed-from-CodeBuild
as the mechanism for non-AWS resources, and also lists that Terraform stage under "deliberately
not built". How should the Microsoft side be provisioned?

A) **Documented manual runbook now** — a human follows written steps in the portals; Terraform
later. Fastest, but the identity chain is not IaC and cannot be reproduced by the pipeline

B) **Build the Terraform stage now** — do it properly from the start; the Teams bot is the
blueprint that justifies it. Larger scope, and it is the first Terraform in the repository

C) **Manual runbook now, Terraform as a committed follow-up** — as A, but with the follow-up
tracked as in-scope work rather than an aspiration

D) **Terraform authored now but not wired into the pipeline** — committed `.tf` files a human runs
locally, so the definition is at least version-controlled

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 13

Creating the Azure Bot Service resource requires **Contributor on the Azure resource group** — an
Azure RBAC role, distinct from any Entra or Teams role. Is that access available?

A) **Yes, in both tenants** — no blocker

B) **Yes in the dev tenant only** — Cornell-side Azure access still needs to be arranged

C) **No, not yet in either** — this is a blocking prerequisite to resolve before implementation

D) **Unknown** — needs checking

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 14

If Q4 requires anything beyond personal scope, publishing to the organization with **Teams admin
approval** becomes a hard prerequisite. What is the state of that?

A) **Already arranged** — a Teams admin is lined up to approve org publish and set availability
scoping

B) **Expected to be straightforward** — not arranged, but no difficulty anticipated

C) **A known obstacle** — likely slow or uncertain; the design should not depend on it for the
first version

D) **Not applicable** — Q4 answer is personal scope only

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 4 — Secrets

## Question 15

If a client secret is used (Q11 A or C), it must live only in AWS Secrets Manager — and no stack
in this repository reads a secret today, so this sets the pattern. How should the secret get
*into* Secrets Manager?

A) **Manual one-time entry** — a human creates the secret value in the console or CLI; the
blueprint template references it by name and never contains it

B) **Bootstrap-created empty, populated manually** — CloudFormation creates the secret container
with no value; a human fills it once. Makes the secret's existence IaC without ever committing
its value

C) **Terraform-created and populated** — whichever Terraform provisions the Entra app also writes
the resulting secret into Secrets Manager, so no human handles the value

D) **Decide during design** — depends on Q12

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Standing constraint regardless of answer**: this repository is public and secret scanning is
disabled by enforced org policy. No secret value goes into any file here, ever. The live
credentials currently sitting in `docs/teams-chatbot-docs/Research into in-tenant setup.md` and
`.mcp.json` still need rotating — see the note in `audit.md`.

## Question 16

Should secret rotation be in scope for the first version?

A) **No** — manual rotation, documented in the runbook

B) **Alerting only** — no automation, but a reminder or expiry alarm before the secret expires

C) **Yes, automated** — Secrets Manager rotation with a rotation Lambda that updates the Entra
app registration

D) **Not applicable** — Q11 answer is managed identity, so there is no secret

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 5 — Repository Mechanics

## Question 17

`ContainerBuildProject`, `ContainerRepository` and `pipeline/codebuild.yml` are defined and
lint-clean but **no stage has ever invoked them**, so the `CONTAINER_TARGET`/`DATE_TAG` in,
`CONTAINER_DIGEST` out contract is unproven. If the design needs a container image, how should
that be approached?

A) **Wire it as part of this blueprint** — add the Build stage action and Dockerfile here, and
absorb whatever debugging the first invocation requires

B) **Wire it in a separate preparatory pull request** — prove the container path independently
first, so a failure there is not tangled up with bot logic

C) **Avoid it** — choose a design that needs no container image (a zip Lambda would require
relaxing the container-image convention; Fargate would need its own image anyway)

D) **Decide during design** — depends on Q7

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 18

Where should the first deployment go? `Environment` is the branch name, capped at
`[a-z0-9]{1,4}` — four characters, no hyphens — because it is interpolated into stack names and
into the IAM prefix the deploy role is scoped to. Merges to `main` deploy to the **shared** AWS
account every workshop participant uses.

A) **Straight to `main`** — the shared environment, once the PR is approved

B) **A parallel environment first** — deploy the pipeline with a short branch name such as `bot`
or `dev`, validate there, then merge to `main`

C) **Parallel environment only for now** — do not touch `main` until the Microsoft side is
confirmed working

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 19

The reverse engineering found that all four `cornell:*` tags are mandatory and feed inventory and
the cost dashboard, but **nothing validates their presence** — and a missing tag makes the
resource invisible to exactly the reporting the tags exist for. Should closing that gap be in
scope?

A) **Yes** — extend `pipeline/validate_stacks.py` to fail on a blueprint resource missing any of
the four tags, in this work

B) **Yes, but separately** — worth doing, as its own pull request, not entangled with the bot

C) **No** — out of scope; rely on review

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 6 — Non-Functional Requirements

## Question 20

What is the sensitivity of the message content the bot will handle, and what may be logged? This
drives log retention, CloudWatch configuration, encryption choices, and whether conversation
content may be stored at all.

A) **Non-sensitive** — public course information; full request and response logging is fine for
debugging

B) **Internal but not regulated** — log metadata and errors; avoid logging message bodies in
normal operation

C) **Student data, FERPA-relevant** — no message content in logs, encryption at rest required, and
retention limits needed. Note that a course chatbot answering student questions is plausibly in
this category

D) **Unknown** — needs a decision from a data steward or the platform team before implementation

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 21

What load and latency should the first version be designed for?

A) **Demo scale** — a handful of users, a few messages a minute; latency merely tolerable

B) **Small pilot** — tens of users, occasional bursts; a reply within a few seconds

C) **Course scale** — hundreds of users, bursts around assignment deadlines; a reply within a few
seconds, and Bedrock throughput limits become a real consideration

D) **Campus scale** — thousands of users; needs explicit capacity planning

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 22

What availability and recovery expectation should the first version be held to?

A) **Best effort** — no target; outages are acceptable and fixed when noticed

B) **Business hours, best effort** — expected to work during the day; no formal target, but an
outage should be noticed rather than discovered

C) **Defined target with alerting** — an explicit availability goal, with alarms on endpoint
errors and delivery failures

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 7 — AI-DLC Extensions

These three questions come from the AI-DLC extension opt-in prompts and are reproduced verbatim.
Your answers determine which rule sets bind the rest of this workflow.

## Question 23: Security Extensions

Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade
applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 24: Resiliency Extensions

Should the resiliency baseline be applied to this project?

**What this extension is.** Enabling it applies a set of **directional, design-time best
practices** for building resilient systems, derived from the **AWS Well-Architected Framework
(Reliability Pillar)** and resilience-review guidance. It steers requirements, design, and code
toward fault tolerance, high availability, observability, and recoverability — covering 15
practice areas across business goals, change management, observability, high availability,
disaster recovery, and continuous improvement.

**What this extension is NOT.** Enabling it does **not** make your workload production-ready, nor
does it certify or guarantee any availability, RTO, or RPO target. It is a **starting point** that
scaffolds good resiliency decisions early — it is not a substitute for a formal **AWS
Well-Architected Review** of the built system.

Treat the output as a well-grounded **first draft of your resiliency posture** to build on and
validate — not a finished, production-certified result.

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance
(recommended for business-critical workloads, as an informed starting point that you can validate
and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental projects
where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 25: Property-Based Testing Extension

Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business
logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for
projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin
integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

# Section 8 — Model Access (added 2026-08-03)

Added after the extension questions to avoid renumbering anything above. It belongs logically with
Section 2.

## Question 26

Cornell operates an Anthropic-API-compatible **LiteLLM gateway** at
`https://api.ai.it.cornell.edu`, offering `claude-opus-5`, `claude-sonnet-5`, several other Claude
models and `google-enterprise-web-search`. This was not known when Section 2 was written. Where
should model inference come from?

A) **Bedrock-native** — `bedrock:InvokeModel` or a cross-region inference profile, authenticated by
the execution role. **No API key exists at all**, and spend lands in the workshop AWS account where
the `cornell:*` cost dashboard can see it. Requires confirming per-account model entitlement.

B) **Cornell's LiteLLM gateway** — model access is already solved and the newest models are
available, at the cost of a long-lived API key in Secrets Manager, an external network dependency,
and spend that is **invisible to this account's tag-based cost dashboard**

C) **Both** — the gateway for chat inference, Bedrock for embeddings. The likely answer if this
blueprint does retrieval, for the reason in the note below

D) **Not applicable** — the first version needs no model inference at all (consistent with Q3 = A
or B)

X) Other (please describe after [Answer]: tag below)

[Answer]: **B — ANSWERED 2026-08-03.** All model traffic must route through the LiteLLM gateway.
Stated rationale: it is how Cornell gets the full model list **and the ability to handle
medium-risk data**. Recorded as a **hard constraint**, not a preference — see
`model-access-options.md` §7 for the consequences, one of which is significant.

**Note**: the gateway catalogue contains **no embeddings model**, and
`AWS::Bedrock::KnowledgeBase` is configured with a Bedrock model ARN rather than an arbitrary HTTP
endpoint — so it cannot be pointed at the gateway. **If Q3 selects D (retrieval), Bedrock model
access is required regardless of the answer here.** Full trade-off analysis, including the
`google-enterprise-web-search` capability and the effect on Q20, is in `model-access-options.md`.

**This interacts with Q20.** Option B sends message content to a Cornell-operated gateway rather
than keeping it inside the AWS account boundary. That is not an objection — a Cornell gateway may
well be the preferred place for Cornell data — but it changes the data-flow picture, so please
answer Q20 with this in mind.

---

# Answers I Am Not Asking For

Recorded so you can see what I took as settled from the research documents and `CLAUDE.md`, and
correct me if any of it is wrong.

| Taken as settled | Source |
| --- | --- |
| Region is `us-east-1`; `Application` is `aidlc` | `CLAUDE.md` |
| Inbound JWTs must be validated, not trusted — RS256 against the Bot Framework JWKS, `iss`, `aud`, `exp`/`nbf` within five minutes, and the `serviceurl` claim matched against the body's `serviceUrl` | research findings |
| The endpoint must return `200 OK` quickly or Teams retries | research findings |
| Handlers must tolerate activities with no `text` (`conversationUpdate`, `installationUpdate`) | research findings |
| Azure Bot Service is the supported path; `dev.botframework.com` is legacy; Bot Framework SDK v4 support ended 31 December 2025 and the successor is the Microsoft 365 Agents SDK | research findings |
| Manifest v1.25 needs top-level `"supportsChannelFeatures": "tier1"` for `team` scope, and the Developer Portal "Application (client) ID" field must be left blank | research findings |
| Thread replies without `@mention` need resource-specific consent, not Microsoft Graph change notifications | research recommendation |
| Stack naming, the four `cornell:*` tags, registry-plus-pipeline-action registration, and explicit parameter passing all apply to this blueprint | `CLAUDE.md` |
| Nothing under `aidlc-rules/` gets edited | `CLAUDE.md` |

---

**When you are done**, say so and I will read this file, validate the answers for contradictions,
raise a clarification file if any are found, and then generate
`aidlc-docs/inception/requirements/requirements.md`.
