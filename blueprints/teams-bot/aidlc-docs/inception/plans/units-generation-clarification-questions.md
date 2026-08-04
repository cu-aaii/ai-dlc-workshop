# Units Generation — Clarification Questions

**Created**: 2026-08-04
**Stage**: INCEPTION — Units Generation (Part 2, paused mid-generation)
**Reason**: a contradiction detected between two user inputs, per `question-format-guide.md`
§"Contradiction and Ambiguity Detection"

---

## Contradiction 1 — the agent runtime, and therefore the image count

You indicated **"MUST use Agent Core"** (gate question 3, answered as option A: *"AgentCore stands.
The agent ships as its own ARM64 container on AgentCore Runtime, with an Endpoint and Memory"*).

You then supplied decision record **D-b**, which states that *"**D-c** removes the question
entirely: Application Design Q11 specified two targets (`lambda`, `agent`) because there was a
separate agent container on AgentCore. **One Lambda means one image means one target.**"*

These are contradictory: D-c's premise is that there is **no** separate agent container, which is
the opposite of gate answer 3.

### What is *not* in dispute — D-b's conclusion is correct either way

Every citation in D-b was verified and every one holds. **D-b also corrects a real error in the
`unit-of-work.md` generated minutes earlier**, which placed Dockerfiles in `src/frontdoor/` and
`src/agent/`:

| Claim | Verified |
| --- | --- |
| `CLAUDE.md:30` — "one per component that ships an image, in that component's own directory, with a **named target** — there is no root `Dockerfile`" | ✅ verbatim |
| `CLAUDE.md:308-314` — the action sets `CONTAINER_CONTEXT` to the component directory and `CONTAINER_TARGET` to the target, and the two must agree with where the component lives | ✅ |
| `pipeline/pipeline.yml:678-696` — `BuilderMcpContainer` sets `CONTAINER_CONTEXT: packages/builder-mcp` (the component root) and `CONTAINER_TARGET: builder-mcp` | ✅ exactly as described |
| `pipeline/stacks.yml:55` — "root Dockerfile target `builder-mcp`" is stale; the file is at `packages/builder-mcp/Dockerfile` | ✅ **caught by D-b, missed in this stage's own review** |
| `blueprints/course-chatbot/README.md:22` — "the root Dockerfile's `course-chatbot` target"; target name right, "root" wrong | ✅ |
| The Lambda image must build on the **AWS Lambda Python base image**, because `requirements.txt` deliberately omits `boto3` (that image ships it), so `builder-mcp`'s `uv` base would break it | ✅ per `course-chatbot/README.md` |

**So the conclusion — one `Dockerfile` per component, at the component's own root, with a named
target and a matching `CONTAINER_CONTEXT` — is adopted regardless of how this question resolves.**
What is in dispute is only **how many components ship an image**: one, or two.

### The premise is what conflicts, and it changes real work

| | AgentCore (gate answer 3) | One Lambda (D-c) |
| --- | --- | --- |
| Images | **two** | **one** |
| `Dockerfile`s | `blueprints/course-chatbot/Dockerfile` (Lambda) **and** `blueprints/course-chatbot/agent/Dockerfile` | `blueprints/course-chatbot/Dockerfile` only |
| Targets | `course-chatbot`, `course-chatbot-agent` | `course-chatbot` |
| Base images | Lambda Python base **and** a `uv` base — AgentCore's reference pattern needs `uv sync --frozen` (SECURITY-10) | Lambda Python base only |
| Build actions | two | one |
| Build project | `ContainerBuildProject` **and** `ArmContainerBuildProject` (AgentCore requires arm64) | `ContainerBuildProject` |
| CloudFormation | adds `AWS::BedrockAgentCore::Runtime` + `RuntimeEndpoint` + `Memory` | none of those |
| **`U6`** | **exists as written** | **dissolves into the worker** |
| Conversation state | AgentCore Memory — Application Design Q7/Q9 stand | **Q9 reopens** — history needs a new home |
| FR-21 | satisfied | **violated** — FR-21 records AgentCore as mandated by Team E |

**Note that two `Dockerfile`s in one blueprint already has a precedent here**:
`blueprints/aisei-site/Dockerfile` and `blueprints/aisei-site/app/Dockerfile` both exist. So the
AgentCore branch does not strain the convention — it nests, the way `aisei-site` does.

**Note also that the differing base images are an argument *for* D-b's conclusion, not against it.**
Under AgentCore the two images want genuinely different bases — Lambda Python for one, `uv` for the
other — which is a better reason for two files than the convention change was.

### Clarification Question 1
Does **D-c** supersede gate answer 3, or does gate answer 3 stand?

A) **Gate answer 3 stands — AgentCore.** D-c is superseded. Two images, two `Dockerfile`s at
component roots, two Build actions, `U6` stays, FR-21 satisfied, Q7/Q9 state design unchanged.
D-b's placement and base-image guidance is adopted for both images.

B) **D-c supersedes — one Lambda, no AgentCore.** One image, one `Dockerfile`, one target
`course-chatbot`, one Build action. `U6` dissolves into the worker. **FR-21 is contradicted and the
Team E mandate is overridden**, so that override should be stated to Marty rather than left implicit.
**Q9 reopens** — a new decision is needed on where conversation history lives, which will need its own
question.

C) **Both, staged** — build the one-Lambda image now so a working bot exists for the demo, and keep
`U6` in the unit artifacts as the next unit rather than deleting it. Honest about the mandate being
deferred rather than met.

X) Other (please describe after [Answer]: tag below)

[Answer]: **A — AgentCore stands, delivered in two steps.** Answered 2026-08-04 by the user, in their
words: *"it replaces `_ask()`. The model call moves out of the Lambda into an AgentCore Runtime
container; the Lambda becomes a Bot Framework front door that calls InvokeAgentRuntime. That seam is
the only structural change, and it needs no worker Lambda, no SSE, no queue."*

**The seam, verified against the code**: `_ask(turns) -> (text, usage)` at
`blueprints/course-chatbot/src/handler.py:120`. Narrow in, narrow out. Step 1 ships the Lambda front
door calling the gateway directly; step 2 replaces `_ask()` with `invoke_agent_runtime`. The Lambda
front door is required either way, because Azure Bot Service can only reach a public HTTPS endpoint
and never AgentCore directly (FR-21 — AgentCore's `CUSTOM_JWT` authorizer cannot do the `serviceurl`
correlation).

**Withdrawn by this answer**: the Worker Lambda, async invoke, SSE, the DynamoDB idempotency table, and
`StreamingDelivery`. Synchronous reply fits the 10–15s Teams budget once both hops are pre-warmed
(§9 of `agentcore-strands-research-2026-08-04.md`). U4 and U7 are deferred, not deleted.

**Five consequences of the swap**, recorded so they are not rediscovered:

1. `SYSTEM_PROMPT`, `MODEL_ID`, `MAX_TOKENS` and `EFFORT` move into the agent container. `MODEL_ID`
   must stop being a required import-time variable in the Lambda (`handler.py:40` raises `KeyError`).
2. The gateway key moves with them. The **runtime** role gets `secretsmanager:GetSecretValue`; the
   **Lambda** role drops Bedrock and gains only `bedrock-agentcore:InvokeAgentRuntime` on the runtime
   ARN. Net narrowing.
3. **`history` cannot come from the client.** `_parse_request` reads prior turns from the request body,
   but Teams hands over one activity and no history — so the stateless-by-client contract cannot
   survive contact with Teams, independently of AgentCore. Multi-turn comes from session affinity
   (free, ephemeral) or AgentCore Memory (persistent).
4. Session ID replaces `conversation_id` as the load-bearing identifier: ≥33 characters, derived
   deterministically from the Teams conversation. It is simultaneously the warm-start control and the
   per-user isolation control that FR-24 misstated.
5. 409 `RetryableConflictException` retry on the invoke, and an explicit Lambda timeout — the front
   door now holds the request open while AgentCore works, so the 3-second default would truncate
   every reply.

**One simplification made explicit**: `/invocations` returns **plain JSON, not SSE**. The AgentCore
HTTP contract supports either, and with no streaming consumer there is no reason to build the harder
one.

**Original analysis, retained as written:**

**No recommendation offered on the substance.** Gate answer 3 was emphatic ("**MUST** use Agent
Core") and FR-21 records the mandate as Team E's, not Track C's — so this is not a call to make from
a convention document. What is worth saying is only this: **B and C both require a second answer**
(where conversation state lives), and **B contradicts a recorded mandate**, so if the intent is B the
override is better said out loud today than found in rehearsal.

---

## Applied immediately — independent of this question

These needed no answer and are done:

- **`blueprints/course-chatbot/README.md:22`** — "root Dockerfile" corrected.
- **`pipeline/stacks.yml:55`** — the `builder-mcp` description corrected to
  `packages/builder-mcp/Dockerfile`.

## Held pending this question

- The **code organisation strategy** section of `unit-of-work.md` — its `Dockerfile` placement is
  wrong as generated (`src/frontdoor/`, `src/agent/`) and will be rewritten to D-b's convention once
  the image count is known, since one-versus-two changes that whole section.
- `unit-of-work-dependency.md` and `unit-of-work-story-map.md` — not yet generated. `U6`'s existence
  changes both the dependency matrix and the requirement-to-unit mapping for FR-21, FR-22, FR-24 and
  FR-27.
