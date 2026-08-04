# AgentCore and Strands — research, 2026-08-04

**Why this exists**: Clarification Question 1 asks whether the agent runs on AgentCore or as Strands in
one Lambda. The question was framed on assumptions this research falsifies, and it also turned up
three factual errors in `requirements.md`. Sources are AWS documentation and `strandsagents.com`,
retrieved 2026-08-04, plus the worked example already in this repository.

---

## 1. The headline: **AgentCore Runtime does not require a container**

`AWS::BedrockAgentCore::Runtime` takes `AgentRuntimeArtifact`, which accepts **either** of two
mutually exclusive configurations — and both are CloudFormation-native:

| | |
| --- | --- |
| `ContainerConfiguration` | `ContainerUri` — an image in ECR. What `builder-mcp` uses |
| `CodeConfiguration` | source code location and execution settings — a **zip in S3** |

Direct code deployment ("CodeZip") went GA in **November 2025**. The steps are: package code and
dependencies into a zip, upload to S3, point the runtime at the bucket. **No Dockerfile, no ECR, no
image build.** It is the *default* build type in the AgentCore CLI (`agentcore create --build
CodeZip`), and the docs describe container builds as the option for "custom system-level dependencies
or a specific base image".

**This falsifies the premise of decision D-c.** D-c reasoned that Application Design Q11 specified two
container targets *because* there was a separate agent container on AgentCore, and therefore that
dropping AgentCore was what removed the second image. In fact **the AgentCore mandate and "no
container" are compatible** — they were never the same question.

### But read the caveats before treating this as a shortcut

- **arm64 is still mandatory, at the binary level.** AgentCore Runtime only supports arm64. The
  service scans every `.so` (Python) and `.node` (Node) file in the package and validates its **ELF
  header**. Any x86_64 or macOS binary fails agent creation with `CREATE_FAILED` and *"Your artifact
  contains binary files that are incompatible with Linux ARM64."* Pure-Python dependencies are fine;
  anything with a compiled extension needs
  `uv pip install --python-platform aarch64-manylinux2014 --only-binary=:all:`.
- **CodeZip is simpler in general but not obviously simpler *in this repository*.** This repo's deploy
  path is built around digest-pinned container images: `ContainerBuildProject`,
  `ArmContainerBuildProject`, the ECR login and the `CONTAINER_DIGEST` export in
  `pipeline/codebuild.yml`, all live and exercised. A CodeZip path needs **new** machinery — build the
  zip, upload to S3 with a deterministic key, pass that key as a parameter — none of which exists.
  Choosing CodeZip trades a proven path for an unproven one.

---

## 2. Strands and the gateway mandate — resolved, and better than expected

**Strands ships a first-class LiteLLM provider.** `strands.models.litellm.LiteLLMModel`, which
subclasses `OpenAIModel`. Cornell's gateway *is* a LiteLLM proxy — the A-2 network investigation
recorded `server: uvicorn` at `api.ai.it.cornell.edu`, and LiteLLM proxy is a uvicorn app — so the
documented proxy path applies directly:

```python
from strands import Agent
from strands.models.litellm import LiteLLMModel

model = LiteLLMModel(
    client_args={
        "api_key": "<from Secrets Manager>",
        "api_base": "https://api.ai.it.cornell.edu",
        "use_litellm_proxy": True,
    },
    model_id="<gateway model id>",
    params={"max_tokens": 4096},
)
agent = Agent(model=model, system_prompt=SYSTEM_PROMPT)
```

The alternative form is a `litellm_proxy/` prefix on `model_id` instead of the `use_litellm_proxy`
flag. Install is `pip install 'strands-agents[litellm]'` — LiteLLM is an **optional** dependency, so
omitting the extra produces `ModuleNotFoundError: No module named 'litellm'`.

**Three consequences:**

1. **FR-23 and FR-23a are satisfiable with a supported, documented provider.** No custom Strands model
   provider, no hand-rolled HTTP client.
2. **`components.md` component 10, `GatewayClient`, largely collapses** into configuring
   `LiteLLMModel`. What remains is reading the key from Secrets Manager and translating errors — the
   streaming and request construction come free.
3. **AgentCore does not constrain the model.** The CloudFormation reference for
   `AWS::BedrockAgentCore::Runtime` says it is *"purpose-built for deploying and scaling dynamic AI
   agents and tools using any open-source framework including LangGraph, CrewAI, and Strands Agents,
   any protocol, and **any model**."* Any residual worry that AgentCore implies Bedrock inference, and
   therefore conflicts with Q26, is unfounded.

Also available and relevant later: LiteLLM supports **provider-agnostic prompt caching** through
`SystemContentBlock` arrays with a `cachePoint`, needing ≥1,024 tokens. A long Tier A system prompt is
exactly that shape. Not a v1 requirement; a cheap latency and cost win afterwards.

---

## 3. Strands and AgentCore Memory — also first-class

`pip install 'bedrock-agentcore[strands-agents]'` provides the **AgentCore Memory Session Manager**,
which persists Strands conversations. Short-term memory for within-session conversation history,
long-term memory with strategies.

So Application Design **Q7** ("the agent reads its own history") and **FR-24** are a supported
integration rather than custom code.

**One operational note that fits this repo well**: the docs say memory-resource creation is *"typically
done once, separately from your agent application… through the AWS Console or a separate setup script,
then use the memory ID in your agent application."* CloudFormation creating the resource and passing
the memory ID in as an environment variable is exactly that shape.

### `AWS::BedrockAgentCore::Memory` exists in CloudFormation

This was worth checking, because the mandate is CloudFormation-only and the knowledge base team hit
precisely this class of problem. It is real, with `Description`, `EncryptionKeyArn`,
`EventExpiryDuration`, `IndexedKeys`, `MemoryExecutionRoleArn`, `MemoryStrategies`, `Name`,
`StreamDeliveryResources` and `Tags`.

| Level | How it is written | Notes |
| --- | --- | --- |
| **Short-term** | `CreateEvent` API, stored **instantly** | Turn-by-turn history within a session. **All Tier A needs** |
| **Long-term** | Requires configured **extraction strategies** | `Semantic`, `Summary`, `UserPreference`, `Episodic`, `Custom` |

**Omitting `MemoryStrategies` gives short-term only**, which is the right v1 shape. Two things to know
before anyone reaches for long-term memory:

- **Extraction is asynchronous**, processed from raw events after every few turns. The docs are
  explicit: *"Design your application to handle the delay between event ingestion and memory
  availability."*
- **Long-term records cannot be created directly** — only extracted.

---

## 4. Three factual errors in `requirements.md`, found by this research

### 4a. FR-24's "per-user isolation by construction" is wrong

FR-24 states: *"Each AgentCore session runs in a dedicated microVM for up to 8 hours, giving per-user
isolation by construction."*

**The isolation half is confirmed and strong.** Each session gets a dedicated microVM with isolated
compute, memory and filesystem; on completion the microVM is terminated and memory sanitised. AWS
contrasts this with container or process isolation, which they say is insufficient for agents.

**"Per-user by construction" is the error.** From the same page:

> "AgentCore does **not** enforce session-to-user mappings — your client backend should maintain the
> relationship between users and their session IDs. Additionally, your client backend should implement
> logic for user to session lifecycle management like maximum number of sessions per user."

Isolation is **per session**, and mapping sessions to users is **our** job. Two failure modes follow,
and neither is theoretical:

- Reuse one session ID across users → **they share a microVM and each other's context.** A
  cross-tenant data leak, produced by our code, in a design whose whole justification was isolation.
- Mint a fresh session ID per turn → isolation is perfect and **conversation memory is lost every
  turn.**

**New design requirement**: the Worker must derive a **stable session identifier per Teams user and
conversation**, and it is a security control, not a convenience. This is a genuine gap in the current
requirements, not a restatement.

Related constraint worth carrying: `runtimeSessionId` has a documented **minimum length of 33
characters**. A Teams conversation ID may be shorter than that, so the derivation probably needs a
hash or a prefix rather than a raw pass-through.

### 4b. ~~The "up to 8 hours" figure is unverified~~ — **CONFIRMED, retracted 2026-08-04**

Verified on the second pass. The docs state *"isolated sessions backed by ephemeral computes lasting up
to 8 hours per lifecycle"*, and `LifecycleConfiguration.maxLifetime` defaults to **28800 seconds = 8
hours**, which is also its maximum. FR-24's figure is correct. Only the *"per-user isolation by
construction"* half of that sentence is wrong (§4a).

### 4c. FR-27 is satisfied, and its stated reasoning no longer applies

FR-27 requires changing `ContainerBuildProject` from `LINUX_CONTAINER`/x86 to an ARM container type.
Upstream did this by **adding a second project**, `ArmContainerBuildProject`, rather than changing the
first. The requirement's intent is met; its literal instruction would now be wrong.

---

## 5. A third option nobody has costed: **AgentCore Harness**

A managed, **config-based agent loop** — model, tools, skills and memory as configuration, with **no
orchestration code and no container**. Create with `create-harness`, poll `get-harness` until `READY`,
invoke on the data plane with a `runtimeSessionId` and a `messages` list.

**Why it is worth naming**: Tier A is *"system prompt + model + conversation memory"* with no tool use.
That is close to exactly what Harness configures. Also relevant to the wider workshop —

> **Classic Bedrock Agents (`bedrock-agent`) is in maintenance mode and closed to new customers.**
> AWS's stated recommendation for new agent workloads is AgentCore, using the Harness managed loop.

**Two unverified blockers, and both are disqualifying if they land badly.** I am recording this as an
option to evaluate, **not** recommending it:

1. **Is Harness CloudFormation-deployable?** Not verified. The documented path is `create-harness` on
   the control plane and the AgentCore CLI. If it is API-only, it fails Marty's CloudFormation-only
   constraint — the exact trap flagged to the knowledge base team about managed knowledge bases.
2. **Can Harness use a non-Bedrock model?** Not verified. Runtime explicitly supports "any model";
   Harness configures the model for you, which is precisely where a Bedrock-only assumption would
   hide. If Harness cannot reach the LiteLLM gateway, **Q26 rules it out** regardless of anything else.

---

## 6. Traps confirmed — two of which this repository already solved

| Trap | Evidence | Status here |
| --- | --- | --- |
| **`AgentRuntimeName` takes underscores, not hyphens** | Pattern permits letters, digits and `_`, max 48 | **Already solved.** `builder-mcp.yml:234-235` comments it and uses `${Application}_${Environment}_builder_mcp`. **The `<app>-<env>-<name>` stack convention cannot be reused for this property** |
| **`Tags` is a map, not a list of `Key`/`Value`** | Both `Runtime` and `Memory` declare `Tags` as `Object of String` | **Already solved.** `builder-mcp.yml:265` comments it. This is the **third** instance after `AWS::SSM::Parameter` and `AWS::Bedrock::KnowledgeBase` — the pattern is "Bedrock-era resources take map tags" |
| **`/ping` must not advance `time_of_last_update` on every call** | A timestamp that moves every ping signals continuous status change, so **the idle timeout never fires**; sessions persist to `MaxLifetime` and **exhaust the session quota** | **New.** Directly relevant: streaming holds a session open, and `HealthyBusy` is what keeps it alive. Omit the field and the platform tracks changes itself |
| **Protocol must be declared** | `ProtocolConfiguration` ∈ `MCP \| HTTP \| A2A \| AGUI` | **New for us.** `builder-mcp` is `MCP`; ours is **`HTTP`** — `/invocations` on 8080, JSON or SSE |

Also noted, not needed: AgentCore Runtime now supports **bi-directional WebSocket streaming** at `/ws`
via `InvokeAgentRuntimeWithWebsocketStream`. SSE over `/invocations` is sufficient for us, since Teams
streaming is driven by the Worker, not the browser.

---

## 7. The wider AgentCore surface, for context

Ten-plus services, of which this blueprint needs two or three:

| Service | What it is | Us? |
| --- | --- | --- |
| **Runtime** | Serverless hosting for an agent loop you wrote. Container **or** zip | **Yes** |
| **Memory** | Short-term and long-term agent memory | **Yes** |
| **Observability** | OTEL traces to CloudWatch; enabled by `opentelemetry-instrument` | **Yes**, free with the entrypoint wrapper |
| **Harness** | Managed config-based loop, no code | **Maybe** — see §5 |
| Gateway | Turns REST APIs, Lambdas and MCP servers into agent tools | No — Tier C |
| Identity | Auth against Okta/Entra/Cognito; act on behalf of a user | No — Teams supplies identity |
| Policy | Cedar or natural-language guardrails, intercepting Gateway tool calls | No — no Gateway |
| Code Interpreter | Sandboxed code execution | No — Tier C |
| Browser | Web automation | No |
| Registry / Evaluations | Catalogue agents; LLM-as-judge quality scoring | No, but **Evaluations is interesting for the KB team** |
| Payments | x402 microtransactions | No |

---

## 8. What this means for Clarification Question 1

The choice is **three** options, not two, and the middle one did not exist in the original framing:

| | Option 1 — Runtime + container | Option 2 — Runtime + CodeZip | Option 3 — one Lambda (D-c) |
| --- | --- | --- | --- |
| FR-21 / Team E mandate | **satisfied** | **satisfied** | **violated** |
| Container to build | yes, arm64 | **none** | yes (Lambda image) |
| Q9 conversation state | unchanged — AgentCore Memory | unchanged | **reopens** |
| Proven in this repo | **yes — `builder-mcp`** | no | partially — `tiny-chatbot` |
| New pipeline machinery | **none** | zip build + S3 upload + parameter | none |
| arm64 constraint | image build | **wheels must be aarch64** | none |

**Recommendation: Option 1 for today, Option 2 recorded as the better end state.**

The reasoning is specific to this repository rather than to AgentCore. `packages/builder-mcp` is
already *an arm64 AgentCore runtime, built by the pipeline, deployed by digest from CloudFormation* —
which is the exact shape U6 needs, working, with the naming and tag traps already discovered and
commented. Option 2 is genuinely simpler in the abstract and would delete a whole class of work, but
it needs pipeline machinery that does not exist, on the day of the demo, to replace machinery that
does. That is the wrong trade this afternoon and the right one next week.

**Option 3's central argument is now weak.** It traded away a mandate to avoid a container — and a
container was never what the mandate cost.

---

## 9. Session affinity and cold starts — researched 2026-08-04, second pass

**Question asked**: can AgentCore Runtime plus FastAPI hold a connection open so there is no cold
start, making a synchronous reply viable inside the Teams 10–15s deadline?

**Answer: session affinity is real, documented, and AWS's own named cold-start mitigation — but it does
not help the *first* message, which is exactly the demo case. Pre-warming closes that gap.**

### The mechanism

Runtime sessions are **sticky to a microVM**, keyed on a session header:

| Protocol | Session header |
| --- | --- |
| **HTTP** (ours) | **`X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`** |
| MCP | `Mcp-Session-Id` |
| A2A / AG-UI | `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` |

> "Amazon Bedrock AgentCore uses the session header to route requests to the same microVM instance.
> Clients must capture the session ID returned in the response and include it in all subsequent
> requests to ensure session affinity. **Without a consistent session ID, each request may be routed to
> a new microVM, which may result in additional latency due to cold starts.**"

So AWS frames consistent session IDs as *the* cold-start control. Session IDs need **≥33 characters**.

### Session states — the important detail

| State | Meaning |
| --- | --- |
| **Active** | Processing a sync request, a command, or a background task (the latter signalled by `HealthyBusy` in `/ping`) |
| **Idle** | "Completed processing but **remains available for future invocations**" — the microVM is still there, **warm** |
| **Stopped** | microVM terminated. Next invocation provisions a **new** compute — a cold start. Session ID stays valid until the runtime ARN is deleted |

A session becomes `Stopped` on: **15 minutes idle** (default), **8 hours max lifetime** (default), an
explicit `StopRuntimeSession`, or a failed health check.

### Both timeouts are CloudFormation-tunable

`LifecycleConfiguration` on `AWS::BedrockAgentCore::Runtime`:

| Property | Default | Range |
| --- | --- | --- |
| `IdleRuntimeSessionTimeout` | 900 s (15 min) | 60 – 28800 s |
| `MaxLifetime` | 28800 s (8 h) | 60 – 28800 s |

### What this does and does not solve

- **Does not solve the first message.** A new session always provisions a new microVM. Someone walking
  up on stage and messaging the bot for the first time **is** the cold-start case. Session affinity by
  itself does not help the demo.
- **Does solve messages 2..N**, for as long as the idle timeout allows.
- **`HealthyBusy` is not a keep-warm.** It signals *background task in progress* so the runtime does
  not scale the session down mid-work. Using it to hold an idle session open is a misuse, and the
  `/ping` docs warn specifically that a `time_of_last_update` which advances on every ping prevents the
  idle timeout from ever firing — sessions then persist to `MaxLifetime` and **exhaust the session
  quota**.

### The thing that does solve it: pre-warm a known session

Because the session ID is **ours to choose** and is derived deterministically from the Teams
conversation (which §4a already requires as a *security* control), the session can be provisioned
before anyone messages the bot:

1. Set `IdleRuntimeSessionTimeout` high for the demo — up to `28800` (8 h).
2. Send one throwaway `InvokeAgentRuntime` with the demo conversation's session ID before going on
   stage. That provisions the microVM.
3. Every subsequent message in that conversation lands **warm** for the whole window.

In practice the simplest version is: **the presenter sends the bot one message a minute before
starting.** No extra code at all.

### A bonus that cuts scope

> "Context is preserved between invocations to the same session."

Within a warm session the microVM holds conversation context in memory. For a demo this means
**AgentCore Memory can be skipped entirely** — session affinity provides multi-turn continuity for
free. The trade-off is stated plainly in the docs: *"the compute associated with a session is
ephemeral. Any data stored in memory or written to disk persists only for the compute lifecycle."* So
context is lost when the session stops. Fine for a demo; not fine as the persistent-history design,
which is what AgentCore Memory is for.

### A new gotcha that matters for a Teams bot specifically

> "While the service provisions or tears down a session, a second operation targeting that same session
> returns a retryable HTTP **409 `RetryableConflictException`** (`Session operation in progress, please
> retry`). This window is brief. Already-running sessions are not affected. **Retry with short
> exponential backoff.**"

This will fire in normal Teams use: a user sending two messages quickly, or an Azure Bot Service retry,
hits the same session during provisioning. **Unhandled, it looks like the bot ignoring a message.**
Cheap to handle, easy to omit, and the first cold invocation — the demo case — is exactly when the
provisioning window is open.

### Consequence for the fastest path

Pre-warming removes the *latency* objection to synchronous + AgentCore cleanly. It does **not** remove
the *build time*, which was the other half of the objection: a second arm64 image, a second Build
action, the Runtime and Endpoint in CloudFormation, SigV4 invoke, session-ID derivation and 409 retry.

The two paths share most of their work, so they should be **sequenced, not chosen between**: the Lambda
front door is required either way, and swapping its gateway call for an AgentCore invoke is a change to
one function — the channel-agnostic seam in `application-design.md` already anticipates it.
