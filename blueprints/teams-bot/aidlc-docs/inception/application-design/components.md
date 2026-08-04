# Components — `teams-bot`

**Stage**: INCEPTION - Application Design
**Scope**: component identification, responsibilities and interfaces. Detailed business logic is deferred to
Functional Design in the CONSTRUCTION phase.

---

## Deployment units

Three deployable artifacts, from two container images.

| Unit | Runtime | Image target | Why it exists |
| --- | --- | --- | --- |
| **Front Door** | Lambda (container image) + function URL | `lambda` | The only thing Azure Bot Service can reach. Must reply in milliseconds. |
| **Worker** | Lambda (container image), async-invoked | `lambda` (same image, different handler) | Survives past the acknowledgement. Does the thinking-and-replying. |
| **Agent** | Bedrock AgentCore Runtime | `agent` | Channel-agnostic reasoning. Calls the gateway. |

The two Lambdas share one image with different handlers, per Q11 — so the Dockerfile has **two** named
targets, not three.

---

## Package layout

```
blueprints/teams-bot/
  infra/
    teams-bot.yml            CloudFormation
  src/
    frontdoor/               entry point A
    worker/                  entry point B
    agent/                   FastAPI app for AgentCore
    shared/                  imported by all three
  Dockerfile                 two named targets: lambda, agent
  pyproject.toml
  uv.lock                    required by uv sync --frozen (SECURITY-10)
  README.md
```

---

## 1. FrontDoor

**Purpose**: receive Bot Framework activities, prove they are genuine, acknowledge, and hand off.

**Responsibilities**

- Terminate the inbound request from the function URL
- Log every inbound request (the SECURITY-02 compensating control — a function URL has no access log)
- Validate the JWT via `JwtValidator`
- Claim the activity in `IdempotencyStore` so a retry cannot start a second pipeline
- Normalise the activity into an envelope
- Async-invoke `Worker`
- Return `200 OK` — **always**, including on validation failure

**Explicitly not its job**: calling the model, calling the Bot Framework API, or knowing anything about
streaming.

**Interface**: `handler(event, context) -> {"statusCode": 200}`

**Design constraint**: everything here is on the latency path. No model calls, no network round trips beyond
a cached JWKS lookup and one conditional DynamoDB write.

---

## 2. JwtValidator

**Purpose**: decide whether a request genuinely came from Azure Bot Service.

The most security-critical component in the blueprint. Written **self-contained, with no blueprint-specific
imports**, so extracting it for reuse later is a file move rather than a refactor (Q9).

**Responsibilities**

- Fetch and cache the Bot Framework JWKS; refresh on `kid` miss, not on a timer alone
- Verify signature with the algorithm **pinned to RS256** — never read `header.alg`
- Check `iss`, `aud`, `exp`/`nbf` with 300s skew
- **Check the `serviceurl` claim (lowercase `u`) against the normalised `body.serviceUrl`, and fail when the
  claim is absent**

**Interface**

```
validate(auth_header: str, activity: dict) -> ValidationResult
```

`ValidationResult` carries a boolean and a machine-readable reason — the reason is logged, never returned to
the caller.

**Why it is its own component**: SECURITY-11 requires security-critical logic to be isolated rather than
scattered. It also makes the mandatory negative test (FR-8a) possible without constructing a Lambda event.

---

## 3. ActivityNormalizer

**Purpose**: translate Bot Framework's wire format into a stable internal envelope, so that nothing
downstream depends on Bot Framework.

**Responsibilities**

- Validate the activity's shape and enforce size bounds (SECURITY-05)
- Normalise `serviceUrl` **once** — strip trailing slash, join with explicit `/` — and expose that single
  value for both the JWT check and reply URLs (FR-14)
- Dispatch on `body.type`; tolerate a missing `text`
- Filter `membersAdded`/`membersRemoved` on the `28:` bot prefix
- Classify the conversation as personal, group or channel

**Interface**

```
normalize(activity: dict) -> Envelope | None
```

Returns `None` for activities that need no work (for example `installationUpdate`).

**Envelope** — the contract between Front Door, Worker and Agent (Q4):

| Field | Purpose |
| --- | --- |
| `activity_id` | Idempotency key and correlation ID |
| `conversation_id`, `conversation_type` | Routing and delivery-strategy selection |
| `service_url` | Normalised, once |
| `user_id`, `user_name` | Context and memory key |
| `text` | May be absent |
| `activity_type` | `message`, `conversationUpdate`, … |
| `reply_to_id` | Present on channel replies; unused at Tier A |

---

## 4. IdempotencyStore

**Purpose**: ensure a given activity is answered exactly once, from **two** independent duplicate sources.

**Why two**: Azure Bot Service retries when it does not get a fast `200`; and Lambda async invocation
**retries twice on error**, which is internal and unrelated to Microsoft. Streaming raises the stakes because
Teams permits only one concurrent stream per chat — a duplicate produces a visible error rather than a
repeated answer.

**Design**: one DynamoDB table, partition key `activity_id`, TTL attribute, and a `status` field advanced by
conditional writes:

```
   (absent) --claim()--> claimed --begin_delivery()--> delivering --complete()--> done
```

- `FrontDoor.claim()` succeeds only if the item is absent → catches **Azure** retries
- `Worker.begin_delivery()` succeeds only if status is `claimed` → catches **Lambda async** retries

**Text alternative.** The item moves through three states. From absent, `claim()` sets it to `claimed`. From
`claimed`, `begin_delivery()` sets it to `delivering`. From `delivering`, `complete()` sets it to `done`. Each
transition is a conditional write, so any duplicate arriving at a state it cannot legally leave aborts
quietly.

**Interface**

```
claim(activity_id: str, ttl_seconds: int) -> bool
begin_delivery(activity_id: str) -> bool
complete(activity_id: str) -> None
```

All three return or fail without raising on contention; a `False` means "someone else has this, stop".

---

## 5. Worker

**Purpose**: do the work that could not fit inside the acknowledgement.

**Responsibilities**

- Take over delivery of the activity (`begin_delivery`)
- Invoke the Agent on AgentCore Runtime, requesting a streamed response
- Consume the stream and drive `DeliveryDispatcher`
- Mark the activity complete
- On failure, deliver a generic message plus the correlation ID (Q12) and log the detail

**Interface**: `handler(event, context) -> None`

**Design constraint**: **the Lambda timeout must be set explicitly.** The default of 3 seconds would truncate
every reply. A value on the order of 5 minutes is required.

---

## 6. DeliveryDispatcher

**Purpose**: the seam FR-16 mandates. Selects a delivery strategy from `conversation_type` so the Agent never
learns how replies reach the user.

**Interface**

```
deliver(envelope: Envelope, chunks: Iterator[str]) -> None
```

**Strategies**

| Strategy | Used for | Behaviour |
| --- | --- | --- |
| `StreamingDelivery` | personal | Informative update, then cumulative text updates, then a final message |
| `SingleReplyDelivery` | group, channel | Typing indicator, then one complete message |

Both consume the same chunk iterator, so the Agent's output shape is identical either way. Adding a future
channel is a third strategy, not a change to anything else.

### StreamingDelivery — the fiddly one

Carries the Teams streaming rules, all of which are easy to get wrong:

- content is **cumulative**, not deltas
- `streamSequence` starts at 1, increments, and **must be absent on the final message**
- `streamId` comes from the first response (`201 Created`)
- rate limit **1 request/second**; buffer chunks for 1.5–2 seconds
- calls are **sequential** — await success before the next
- final message is `type: "message"` with `streamType: "final"`

---

## 7. BotFrameworkClient

**Purpose**: the only component that speaks HTTP to Microsoft.

**Responsibilities**

- Acquire and cache a bearer token via `TokenProvider`
- Build reply URLs from the normalised `service_url`
- POST activities, typing indicators and streaming updates
- Surface rate-limit and error responses to the caller rather than swallowing them

**Interface**

```
send_activity(service_url, conversation_id, payload) -> Response
reply_to_activity(service_url, conversation_id, activity_id, payload) -> Response
```

---

## 8. TokenProvider

**Purpose**: obtain the outbound Bot Framework token without ever holding a credential in code.

**Responsibilities**

- Read the Entra client secret from Secrets Manager
- `client_credentials` grant, scope `https://api.botframework.com/.default`
- Cache the token until shortly before expiry

**Interface**: `get_token() -> str`

---

## 9. Agent

**Purpose**: reasoning. **Channel-agnostic** (Q3) — it has never heard of Teams.

**Responsibilities**

- Serve `GET /ping` → `{"status": "Healthy"}`
- Serve `POST /invocations`, accepting an Envelope-derived payload
- Read and write conversation history in AgentCore Memory (Q7)
- Call the LiteLLM gateway with the configured system prompt and model
- Stream output back as SSE

**Interface**: FastAPI app on `0.0.0.0:8080`, wrapped by `opentelemetry-instrument`.

**Why channel-agnostic matters**: it is testable with a JSON payload and no Bot Framework fixtures, and a
future Slack or web blueprint could reuse it unchanged.

---

## 10. GatewayClient

**Purpose**: call Cornell's LiteLLM gateway. The only component that talks to a model.

**Responsibilities**

- Read the gateway service key from Secrets Manager
- POST chat completions with `stream: true`
- Yield text chunks
- Translate gateway errors into a single internal error type

**Interface**: `stream_completion(system: str, messages: list) -> Iterator[str]`

---

## 11. ConfigProvider

**Purpose**: resolve configuration once, at cold start.

**Responsibilities**

- Read environment variables set from stack parameters
- Fetch the system prompt from S3 when `SystemPromptS3Key` is used instead of the inline parameter
  (FR-3a — the 4096-character parameter cap)
- Fail fast and loudly on missing required configuration

**Interface**: `get() -> Config` (cached)

---

## 12. Logger

**Purpose**: structured logging with a correlation ID, used by every component.

**Design decision**: **the correlation ID is the activity `id`.** It already exists, is stable across
retries, and appears in the user-facing error message (Q12) — so a user quoting it leads straight to every log
line for that request.

**Responsibilities**

- Emit JSON with timestamp, level, correlation ID, component and message
- **Never** log secrets, tokens, or message bodies by default

**Interface**: `get_logger(component: str, correlation_id: str | None) -> Logger`

---

## Component summary

| # | Component | Unit | Security-critical |
| --- | --- | --- | --- |
| 1 | FrontDoor | Front Door | yes — entry point |
| 2 | JwtValidator | shared | **yes — the control** |
| 3 | ActivityNormalizer | shared | yes — input validation |
| 4 | IdempotencyStore | shared | no |
| 5 | Worker | Worker | no |
| 6 | DeliveryDispatcher | Worker | no |
| 7 | BotFrameworkClient | shared | yes — holds a token |
| 8 | TokenProvider | shared | **yes — reads a secret** |
| 9 | Agent | Agent | no |
| 10 | GatewayClient | Agent | **yes — reads a secret** |
| 11 | ConfigProvider | shared | no |
| 12 | Logger | shared | yes — must not leak |
