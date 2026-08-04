# Services and Orchestration — `teams-bot`

**Stage**: INCEPTION - Application Design
**Scope**: service boundaries, responsibilities, and how work is coordinated across them.

Three services, one per deployment unit. Each owns a distinct span of the request's life, and the boundaries
are drawn where a **trust, timing or reusability** change occurs — not arbitrarily.

---

## Why the boundaries fall where they do

| Boundary | What changes across it |
| --- | --- |
| Azure Bot Service → **IngressService** | **Trust.** Untrusted input becomes verified input. |
| IngressService → **ConversationService** | **Timing.** The 10–15s acknowledgement deadline stops applying. |
| ConversationService → **AgentService** | **Reusability.** Teams-specific concerns end; generic reasoning begins. |

That third boundary is the one with long-term value: everything above it is Teams, everything below it is not.

---

## 1. IngressService — Front Door Lambda

**Responsibility**: convert an untrusted HTTP request into a verified, deduplicated, normalised unit of work —
and get out of the way fast.

**Orchestration**

```
1. log_inbound_request(event, "received")           SECURITY-02 compensating control
2. parse body                                       malformed -> log, return 200
3. JwtValidator.validate(header, activity)           invalid  -> log, return 200
4. ActivityNormalizer.normalize(activity)            None     -> log, return 200
5. IdempotencyStore.claim(activity_id)               False    -> log, return 200
6. lambda.invoke(worker, InvocationType="Event")
7. return {"statusCode": 200}
```

**Text alternative.** The service logs the inbound request, parses the body, validates the JWT against the
activity, normalises the activity into an envelope, and claims the activity id in the idempotency store. Any
of those steps failing results in a log entry and a `200 OK` with no further action. On success it
asynchronously invokes the Worker and returns `200 OK`.

**Three properties of this ordering, each deliberate:**

- **Validation precedes claiming.** An unauthenticated caller must not be able to consume idempotency keys and
  suppress genuine activities — that would be a denial-of-service through the dedup table.
- **Claiming precedes invoking.** Otherwise a retry arriving during the invoke would start a second pipeline.
- **Every exit path returns `200`.** FR-10. There is exactly one return statement's worth of behaviour, and no
  branch that returns anything else.

**Latency budget**: a cached JWKS lookup and one conditional `PutItem`. No model calls, no Bot Framework
calls, no S3 reads on the warm path.

**Failure posture**: fail closed and silent. Nothing is delivered to the user, because an unverified request
has no legitimate user to answer.

---

## 2. ConversationService — Worker Lambda

**Responsibility**: produce an answer and get it in front of the user.

**Orchestration**

```
1. IdempotencyStore.begin_delivery(activity_id)      False -> stop (Lambda async retry)
2. branch on activity_type:
     conversationUpdate -> greeting/farewell, no agent call
     message            -> continue
3. chunks = Worker.invoke_agent(envelope, config)     SigV4, SSE
4. strategy = DeliveryDispatcher.select_strategy(conversation_type)
5. strategy.deliver(envelope, chunks)
6. IdempotencyStore.complete(activity_id)
```

**Text alternative.** The service first attempts to take over delivery, stopping if a duplicate invocation has
already done so. `conversationUpdate` activities produce a greeting or farewell without calling the agent.
Message activities invoke the agent over SigV4 with a streamed response, select a delivery strategy from the
conversation type, deliver the chunks through it, and mark the activity complete.

**Coordination detail worth stating**: steps 3 to 5 are a **producer–consumer pipeline**, not two phases. The
agent yields chunks while the strategy is already publishing earlier ones. The whole point of Q5 is lost if
this becomes "collect everything, then send".

**The `conversationUpdate` shortcut** matters: a greeting is a configured string, so calling a model for it
would waste money and add latency for no benefit. It is also the path most likely to fire first in a demo —
the bot greets you when installed — so it should be the most reliable path in the system.

**Failure posture**: fail *visible*. Unlike IngressService, there **is** a legitimate user waiting, so a
failure delivers a generic message plus the correlation ID (Q12) and logs the detail. Then `complete()` is
still called, so Lambda's automatic retry does not produce a second apology.

**Timeout**: explicitly configured, on the order of 5 minutes. Lambda's 3-second default would truncate every
reply.

---

## 3. AgentService — AgentCore Runtime

**Responsibility**: given text and a conversation identity, produce a better text. Nothing else.

**Orchestration**

```
1. GET  /ping        -> {"status": "Healthy"}
2. POST /invocations:
     a. load history from AgentCore Memory (keyed on conversation + user)
     b. assemble messages: system prompt + history + new text
     c. GatewayClient.stream_completion(...)      LiteLLM, stream=true
     d. yield chunks as SSE
     e. persist the completed turn to Memory
```

**Text alternative.** The service exposes a health endpoint returning healthy, and an invocations endpoint
which loads conversation history from AgentCore Memory keyed on conversation and user, assembles a message list
from the system prompt, the history and the new text, calls the LiteLLM gateway with streaming enabled, yields
the resulting chunks as server-sent events, and persists the completed turn back to Memory.

**What this service must not do**, stated because it is the design:

- must not know the `service_url`, the `conversation_type`, or that Teams exists
- must not call the Bot Framework API
- must not hold Entra credentials
- must not decide how the answer is displayed

**Persist after streaming, not before.** History is written once the turn completes, so an abandoned or failed
generation does not poison the next turn's context.

**Failure posture**: raise. The Worker is the component with a user to apologise to; the agent's job is to
report failure accurately upward.

---

## Cross-cutting concerns

| Concern | Where it lives | Note |
| --- | --- | --- |
| Configuration | `ConfigProvider`, cached at cold start | Fails fast; a missing value is a startup error, not a request error |
| Logging | `Logger`, correlation ID = activity id | Same ID spans all three services, so one user complaint traces end to end |
| Secrets | `TokenProvider`, `GatewayClient` | Each reads its own; no service passes a credential to another |
| Idempotency | `IdempotencyStore` | The only state shared between IngressService and ConversationService |
| Observability | `opentelemetry-instrument` on the agent | AgentCore Observability; the Lambdas use structured logs |

**The correlation ID is the single most useful cross-cutting decision here.** Because it is the activity id —
which Azure generates, which is identical across retries, and which the user is shown on failure — a report of
"it broke and said `abc123`" resolves to every log line across all three services without any lookup table.

---

## Service interaction diagram

```
   Azure Bot Service
          |
          |  (1) POST activity + JWT
          v
   +-------------------------+
   |  IngressService         |
   |  verify - claim - ack   |
   +-----------+-------------+
          |         ^
          |         |  (2) 200 OK, immediately
          |         +---------------------------> Azure Bot Service
          |
          |  (3) async invoke, Envelope
          v
   +-------------------------+        (4) InvokeAgentRuntime, SigV4
   |  ConversationService    | -------------------------------------+
   |  deliver the answer     |                                      |
   +-----------+-------------+ <------------------------------------+
          |                            (5) SSE text chunks          |
          |                                                          v
          |                                          +-----------------------------+
          |                                          |  AgentService               |
          |                                          |  memory + gateway + stream  |
          |                                          +--------------+--------------+
          |                                                          |
          |  (6) cumulative streaming POSTs                          | (4a) LiteLLM
          v                                                          v
   Bot Framework REST API                                api.ai.it.cornell.edu
          |
          v
   user sees the reply appear
```

**Text alternative.** Azure Bot Service POSTs an activity with a JWT to IngressService, which verifies it,
claims it, and returns `200 OK` immediately. It then asynchronously invokes ConversationService with the
envelope. ConversationService calls AgentService on AgentCore Runtime using SigV4 and receives text chunks as
server-sent events; AgentService in turn calls the LiteLLM gateway. As chunks arrive, ConversationService makes
cumulative streaming POSTs to the Bot Framework REST API, and the user watches the reply appear.

---

## What each service is allowed to reach

Least privilege (SECURITY-06) falls naturally out of the boundaries — no service holds a permission it does not
use, and the separation is enforceable rather than aspirational.

| Service | May call | May **not** call |
| --- | --- | --- |
| IngressService | DynamoDB (`PutItem`, conditional), `lambda:InvokeFunction` on the Worker only | AgentCore, Secrets Manager, Bot Framework |
| ConversationService | `bedrock-agentcore:InvokeAgentRuntime` on one ARN, DynamoDB, Secrets Manager (Entra secret only), Bot Framework over HTTPS | The gateway, S3 |
| AgentService | AgentCore Memory, Secrets Manager (gateway key only), the gateway over HTTPS | Bot Framework, DynamoDB, the Entra secret |

**IngressService cannot invoke AgentCore and cannot read any secret.** Since it is the only internet-facing
component, that is the property worth having: compromising the public endpoint yields the ability to enqueue a
work item, and nothing else.
