# Component Methods — `teams-bot`

**Stage**: INCEPTION - Application Design
**Scope**: method signatures, purpose, and input/output types.

> **Detailed business rules are deliberately absent.** Validation ordering, retry policy, chunk-buffering
> arithmetic and error taxonomy belong to **Functional Design** in the CONSTRUCTION phase. What follows fixes
> the *interfaces* so components can be built and tested independently.

Signatures are Python 3.12 with type hints (Q10). `Envelope` and `Config` are dataclasses.

---

## Shared types

```python
@dataclass(frozen=True)
class Envelope:
    activity_id: str
    activity_type: str            # "message" | "conversationUpdate" | ...
    conversation_id: str
    conversation_type: str        # "personal" | "groupChat" | "channel"
    service_url: str              # normalised exactly once
    user_id: str
    user_name: str | None
    text: str | None              # absent on non-message activities
    reply_to_id: str | None
    members_added: list[str]      # human IDs only; 28: prefixes removed
    members_removed: list[str]

@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None            # logged, never returned to the caller

@dataclass(frozen=True)
class Config:
    bot_client_id: str
    system_prompt: str
    model_id: str
    greeting_text: str
    teams_scopes: list[str]
    agent_runtime_arn: str
    worker_function_name: str
    idempotency_table: str
    entra_secret_arn: str
    gateway_secret_arn: str
    gateway_base_url: str
```

---

## 1. FrontDoor

```python
def handler(event: dict, context: object) -> dict:
    """Lambda function URL entry point. ALWAYS returns {"statusCode": 200}."""
```

```python
def _process(event: dict) -> None:
    """Log, validate, claim, normalise, dispatch. Raises nothing to the caller."""
```

**Return contract**: `{"statusCode": 200}` unconditionally — on success, on a rejected token, and on an
internal error. FR-10: any other status causes Azure Bot Service to retry a request that can never succeed.

---

## 2. JwtValidator

```python
class JwtValidator:
    def __init__(self, expected_audience: str, jwks_url: str) -> None: ...

    def validate(self, auth_header: str | None, activity: dict) -> ValidationResult:
        """Verify a Bot Framework token against the activity it arrived with."""

    def _signing_key(self, kid: str) -> dict:
        """Return the JWK for kid, refreshing the cached key set on a miss."""
```

**Notes on the interface, not the rules:**

- `validate` takes **both** the header and the activity, because the `serviceurl` claim can only be checked
  against the request body. A validator that took only the token could not implement the control.
- Absence of the `serviceurl` claim returns `ok=False`. The signature makes no allowance for "claim missing,
  treat as pass" — that possibility is designed out.
- `reason` is a stable machine-readable string for alarm filtering (SECURITY-14), never surfaced to a caller.

---

## 3. ActivityNormalizer

```python
def normalize(activity: dict) -> Envelope | None:
    """Validate shape and bounds, then project onto Envelope.
    Returns None when the activity requires no work (e.g. installationUpdate)."""

def normalize_service_url(raw: str) -> str:
    """Strip trailing slash. Single source of truth for both the JWT check and reply URLs."""

def classify_conversation(activity: dict) -> str:
    """-> "personal" | "groupChat" | "channel"."""

def human_members(members: list[dict] | None) -> list[str]:
    """Drop entries whose id begins with '28:' (bots)."""
```

`normalize` raises on malformed input; the caller treats that as a validation failure and still returns `200`.

---

## 4. IdempotencyStore

```python
class IdempotencyStore:
    def __init__(self, table_name: str) -> None: ...

    def claim(self, activity_id: str, ttl_seconds: int = 3600) -> bool:
        """Conditional insert. False => already claimed; stop processing."""

    def begin_delivery(self, activity_id: str) -> bool:
        """claimed -> delivering. False => a duplicate invocation; stop."""

    def complete(self, activity_id: str) -> None:
        """delivering -> done. Best effort; never raises."""
```

**Two guards, two duplicate sources** — `claim` blocks Azure Bot Service retries, `begin_delivery` blocks
Lambda's automatic async retries. Both return `bool` rather than raising, because "someone else has this" is
an ordinary outcome, not an error.

---

## 5. Worker

```python
def handler(event: dict, context: object) -> None:
    """Async-invoked. event is a serialised Envelope."""
```

```python
def _run(envelope: Envelope) -> None:
    """begin_delivery -> invoke agent -> dispatch delivery -> complete."""
```

```python
def invoke_agent(envelope: Envelope, config: Config) -> Iterator[str]:
    """Call InvokeAgentRuntime with SigV4, requesting SSE. Yield text chunks."""
```

`invoke_agent` returns an **iterator**, not a string — that is what makes streaming possible without the
Worker knowing how delivery works.

---

## 6. DeliveryDispatcher

```python
class DeliveryStrategy(Protocol):
    def deliver(self, envelope: Envelope, chunks: Iterator[str]) -> None: ...

def select_strategy(conversation_type: str) -> DeliveryStrategy:
    """personal -> StreamingDelivery; groupChat/channel -> SingleReplyDelivery."""
```

```python
class StreamingDelivery:
    def deliver(self, envelope: Envelope, chunks: Iterator[str]) -> None: ...
    def _start(self, envelope: Envelope, text: str) -> str:      # -> streamId
    def _continue(self, envelope: Envelope, stream_id: str, cumulative: str, seq: int) -> None: ...
    def _finalise(self, envelope: Envelope, stream_id: str, cumulative: str) -> None: ...

class SingleReplyDelivery:
    def deliver(self, envelope: Envelope, chunks: Iterator[str]) -> None: ...
```

**Interface observations:**

- `_continue` takes `cumulative`, not `delta` — the parameter name encodes the Teams requirement so the
  cumulative rule is hard to violate accidentally.
- `_finalise` takes **no** `seq` parameter, because `streamSequence` must be absent on the final message. The
  signature makes the correct behaviour the only expressible one.
- Both strategies satisfy the same `Protocol`, so `Worker` holds no conditional logic about delivery.

---

## 7. BotFrameworkClient

```python
class BotFrameworkClient:
    def __init__(self, token_provider: TokenProvider) -> None: ...

    def send_activity(self, service_url: str, conversation_id: str,
                      payload: dict) -> Response:
        """POST {service_url}/v3/conversations/{id}/activities"""

    def reply_to_activity(self, service_url: str, conversation_id: str,
                          activity_id: str, payload: dict) -> Response:
        """POST .../activities/{activity_id}"""

    def send_typing(self, service_url: str, conversation_id: str) -> Response: ...
```

`Response` exposes status and parsed body. Errors are returned, not raised, so `StreamingDelivery` can honour
the "await success before the next call" rule explicitly.

---

## 8. TokenProvider

```python
class TokenProvider:
    def __init__(self, secret_arn: str, client_id: str, tenant_id: str) -> None: ...

    def get_token(self) -> str:
        """Cached client_credentials token; refreshes shortly before expiry."""
```

The secret is read inside `get_token`, never passed in as a constructor argument — so no caller can hold a
credential (SECURITY-12).

---

## 9. Agent (AgentCore Runtime)

```python
app = FastAPI()

@app.get("/ping")
def ping() -> dict:
    """-> {"status": "Healthy"}"""

@app.post("/invocations")
async def invocations(payload: AgentRequest) -> StreamingResponse:
    """SSE stream of text chunks."""
```

```python
@dataclass(frozen=True)
class AgentRequest:
    conversation_id: str
    user_id: str
    text: str
    activity_id: str          # correlation ID only
```

```python
async def run_turn(req: AgentRequest, config: Config) -> AsyncIterator[str]:
    """Load history, call the gateway, stream chunks, persist the turn."""
```

**Note the absence of Teams concepts** in `AgentRequest` — no `service_url`, no `conversation_type`, no
`reply_to_id`. That absence is the design (Q3), and it is what makes the Agent reusable.

---

## 10. GatewayClient

```python
class GatewayClient:
    def __init__(self, base_url: str, secret_arn: str) -> None: ...

    async def stream_completion(self, system: str, messages: list[dict],
                                model: str) -> AsyncIterator[str]:
        """POST /v1/chat/completions with stream=true. Yield text deltas."""
```

---

## 11. ConfigProvider

```python
@lru_cache(maxsize=1)
def get_config() -> Config:
    """Resolve env vars; fetch the system prompt from S3 when a key is configured.
    Raises on missing required values — fail fast at cold start, not mid-request."""
```

---

## 12. Logger

```python
def get_logger(component: str, correlation_id: str | None = None) -> Logger:
    """Structured JSON logger. correlation_id is the activity id."""

def log_inbound_request(event: dict, outcome: str) -> None:
    """SECURITY-02 compensating control: a function URL has no access log,
    so every inbound request is recorded here. Never logs the body."""
```

`log_inbound_request` exists as a named function rather than an ad-hoc call so the compensating control is
discoverable and reviewable, not scattered.

---

## Interfaces that carry a rule in their shape

Worth collecting, because these are places where the signature prevents a known bug rather than relying on
whoever implements it:

| Signature choice | Bug it prevents |
| --- | --- |
| `validate(auth_header, activity)` takes both | A validator that cannot check `serviceurl` at all |
| `ValidationResult.ok` with no "unknown" state | Treating an absent claim as a pass — the prototype's actual bug |
| `_continue(..., cumulative, seq)` | Sending deltas instead of cumulative text |
| `_finalise(...)` has no `seq` | Setting `streamSequence` on the final message |
| `invoke_agent(...) -> Iterator[str]` | Buffering the whole answer and losing streaming |
| `claim() -> bool` and `begin_delivery() -> bool` | Covering only one of the two duplicate sources |
| `AgentRequest` has no Teams fields | Coupling the agent to Bot Framework |
| `TokenProvider` reads its own secret | A credential being passed around by callers |
