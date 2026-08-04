# Component Dependencies — `teams-bot`

**Stage**: INCEPTION - Application Design
**Scope**: dependency matrix, communication patterns, data flow.

---

## Dependency matrix

Rows depend on columns. `→` = direct call, `···` = shared type only.

| | JwtValidator | ActivityNormalizer | IdempotencyStore | DeliveryDispatcher | BotFrameworkClient | TokenProvider | GatewayClient | ConfigProvider | Logger |
|---|---|---|---|---|---|---|---|---|---|
| **FrontDoor** | → | → | → | | | | | → | → |
| **Worker** | | ··· | → | → | | | | → | → |
| **JwtValidator** | | ··· | | | | | | | → |
| **ActivityNormalizer** | | | | | | | | | → |
| **IdempotencyStore** | | | | | | | | | → |
| **DeliveryDispatcher** | | ··· | | | → | | | → | → |
| **BotFrameworkClient** | | | | | | → | | | → |
| **TokenProvider** | | | | | | | | → | → |
| **Agent** | | | | | | | → | → | → |
| **GatewayClient** | | | | | | | | → | → |

**Properties worth noting:**

- **No cycles.** The graph is a DAG; every component can be constructed and tested in isolation.
- **`Logger` and `ConfigProvider` are leaves** depended on by nearly everything, and depend on nothing. That is
  what makes them safe to be ubiquitous.
- **`JwtValidator` depends on nothing but `Logger`.** Deliberate (Q9) — extracting it for reuse by a future
  Teams blueprint is a file move.
- **`FrontDoor` and `Worker` never call each other directly.** The only link is an async Lambda invoke, so
  neither imports the other.
- **`Agent` reaches only `GatewayClient`.** It has no path to `BotFrameworkClient` or `TokenProvider`, so it
  *cannot* accidentally become Teams-aware — the dependency graph enforces Q3 rather than merely documenting it.

---

## Communication patterns

| Edge | Mechanism | Sync? | Failure mode | Retry |
| --- | --- | --- | --- | --- |
| Azure Bot Service → FrontDoor | HTTPS POST, function URL | sync | timeout > 10–15s → `504` to user | Azure retries — hence `claim()` |
| FrontDoor → Worker | `lambda:Invoke`, `InvocationType: Event` | **async** | invoke throttled/failed | AWS retries **twice** — hence `begin_delivery()` |
| Worker → Agent | `InvokeAgentRuntime`, SigV4, SSE | sync, streaming | container cold start, timeout | none automatic; Worker handles |
| Agent → LiteLLM gateway | HTTPS POST, `stream: true` | sync, streaming | gateway 5xx/429 | Agent raises; Worker apologises |
| Worker → Bot Framework | HTTPS POST × N | sync, sequential | 429, or stream-sequence rejection | must await each before the next |
| Any → Secrets Manager | SDK | sync | denied/missing | fail fast at cold start |
| FrontDoor/Worker → DynamoDB | conditional writes | sync | condition failed = *expected* | none — `False` is a normal answer |

### The two patterns that carry the design

**Async invoke is the seam that makes the whole thing possible.** It is the only place where the
acknowledgement deadline stops applying. It is also the reason a second idempotency guard exists, because
AWS's automatic double-retry is a duplicate source entirely internal to us.

**Sequential outbound streaming is the one place concurrency is forbidden.** Teams requires each streaming
update to be acknowledged before the next is sent, `streamSequence` must increase monotonically, and only one
stream may be open per chat. Parallelising for throughput here would break it. `BotFrameworkClient` returns
responses rather than raising precisely so `StreamingDelivery` can enforce this explicitly.

---

## Data flow — a message that gets answered

```
[1] Azure Bot Service
      | Activity JSON + Bearer JWT
      v
[2] FrontDoor ---- JWT + activity ----> JwtValidator ---- kid ----> JWKS cache
      |                                     |
      |<------------- ValidationResult -----+
      |
      | activity ---> ActivityNormalizer ---> Envelope
      |
      | activity_id --> IdempotencyStore  (absent -> claimed)
      |
      +-- 200 OK --> Azure Bot Service          [user's client stops waiting]
      |
      | Envelope (async invoke)
      v
[3] Worker
      | activity_id --> IdempotencyStore  (claimed -> delivering)
      |
      | AgentRequest {conversation_id, user_id, text, activity_id}
      v
[4] Agent --- history key ---> AgentCore Memory
      |
      | system prompt + history + text
      v
[5] GatewayClient ---> api.ai.it.cornell.edu ---> model
      |
      |<---- text deltas (SSE) ----
      v
[6] Agent ---- SSE chunks ----> Worker
      |                            |
      | (persist turn to Memory)   | cumulative text, seq n
      |                            v
      |                       DeliveryDispatcher --> StreamingDelivery
      |                                                   |
      |                                                   v
      |                                          BotFrameworkClient
      |                                                   | + bearer token
      |                                                   |   (TokenProvider
      |                                                   |    <- Secrets Manager)
      |                                                   v
      |                                        Bot Framework REST API
      |                                                   |
      |                                                   v
      |                                           [7] user sees text appear
      v
    IdempotencyStore  (delivering -> done)
```

**Text alternative.** (1) Azure Bot Service POSTs an Activity with a bearer JWT. (2) FrontDoor passes the token
and activity to JwtValidator, which resolves the signing key from a cached JWKS set and returns a validation
result; the activity is normalised into an Envelope; the activity id is claimed in the IdempotencyStore; and
`200 OK` is returned to Azure so the user's client stops waiting. FrontDoor then async-invokes the Worker with
the Envelope. (3) Worker advances the idempotency record from claimed to delivering and builds an AgentRequest
containing only conversation id, user id, text and activity id. (4) The Agent loads history from AgentCore
Memory. (5) GatewayClient calls the LiteLLM gateway, which calls the model, and receives text deltas as
server-sent events. (6) The Agent forwards chunks to the Worker as SSE while persisting the completed turn to
Memory; the Worker passes chunks to the DeliveryDispatcher, which selects StreamingDelivery, which sends
cumulative text with increasing sequence numbers through BotFrameworkClient — authenticated by a token that
TokenProvider obtained using a secret from Secrets Manager — to the Bot Framework REST API. (7) The user watches
the text appear. Finally the Worker marks the idempotency record done.

**The important structural feature**: the `200 OK` at step 2 happens *before* steps 3 through 7 exist. Nothing
after the acknowledgement is on any clock that Microsoft is watching.

---

## Data flow — `conversationUpdate` (the install greeting)

Shorter, and worth its own diagram because it is the path most likely to run first in a demo.

```
Azure Bot Service --> FrontDoor  [validate, claim, ack, async invoke]
                          |
                          v
                       Worker
                          | human_members(membersAdded)   -- drops 28: bot ids
                          | greeting_text from Config     -- NO agent call
                          v
                    DeliveryDispatcher --> SingleReplyDelivery --> Bot Framework
```

**Text alternative.** Azure Bot Service sends a `conversationUpdate` to FrontDoor, which validates, claims and
acknowledges it before async-invoking the Worker. The Worker filters `membersAdded` to human IDs only, takes
the configured greeting text, and — **without calling the agent at all** — sends a single reply through the
dispatcher to the Bot Framework API.

**Why the bypass matters**: a greeting is a configured constant. Calling a model for it would cost money, add
seconds, and introduce a failure mode on the one interaction that happens before the user has typed anything.

---

## External dependencies

| Dependency | Direction | Criticality | If unavailable |
| --- | --- | --- | --- |
| Azure Bot Service | inbound | **critical** | No messages arrive; nothing to do |
| `login.botframework.com` (JWKS) | outbound | **critical** | All validation fails closed; no replies |
| `login.microsoftonline.com` (token) | outbound | **critical** | Cannot reply outbound |
| `*.smba.trafficmanager.net` (`serviceUrl`) | outbound | **critical** | Cannot reply |
| `api.ai.it.cornell.edu` (gateway) | outbound | **critical** | Apology message with correlation ID |
| Bedrock AgentCore Runtime | outbound | **critical** | Apology message |
| Secrets Manager | outbound | **critical** | Cold-start failure |
| DynamoDB | outbound | important | Fail closed — refuse rather than risk duplicates |
| AgentCore Memory | outbound | degraded | Answer without history |
| KB (`Retrieve`) | outbound | Tier B only | Out of scope for v1 |

**Only AgentCore Memory degrades gracefully.** Everything else either fails closed or produces the apology
path — a deliberate consequence of SECURITY-15's fail-closed rule. Notably, **JWKS unavailability stops the bot
entirely**, which is correct: without the ability to verify a caller, answering anything would be worse than
answering nothing.

---

## Coupling assessment

| Coupling | Strength | Verdict |
| --- | --- | --- |
| FrontDoor ↔ Worker | **loose** — async invoke, shared `Envelope` only | Good. Neither imports the other |
| Worker ↔ Agent | **loose** — HTTP + a 4-field payload | Good. Enables agent reuse |
| Worker ↔ DeliveryDispatcher | moderate — `Protocol` | Good. Adding a channel adds a strategy, nothing more |
| DeliveryDispatcher ↔ Bot Framework | **tight** by necessity | Acceptable: contained in one component, which is the point of the seam |
| Everything ↔ `Logger`, `ConfigProvider` | ubiquitous but acyclic | Acceptable — both are leaves |
| FrontDoor ↔ IdempotencyStore ↔ Worker | **shared state** | The only shared mutable state in the system. Confined to three conditional operations on one table |

**The one tight coupling is deliberate and bounded.** Bot Framework's protocol is intricate — cumulative text,
sequence numbers, `serviceUrl` construction, token scopes — and rather than spread that across the system it is
concentrated in `DeliveryDispatcher` and `BotFrameworkClient`. Everything else in the blueprint could survive
Microsoft changing its API.

---

## What a future channel would cost

A useful test of whether the boundaries are right. To add, say, a Slack front end:

| Reused unchanged | Replaced | New |
| --- | --- | --- |
| `Agent`, `GatewayClient`, AgentCore Memory, `ConfigProvider`, `Logger`, `IdempotencyStore` | `JwtValidator` (Slack signing), `ActivityNormalizer`, `BotFrameworkClient`, `TokenProvider` | one delivery strategy |

**The entire reasoning half is reusable.** That is the return on the third service boundary, and it is why Q1
was answered with a separate worker rather than letting the agent talk to Teams directly.
