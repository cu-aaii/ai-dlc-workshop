# Application Design — `teams-bot`

**Stage**: INCEPTION - Application Design
**Generated**: 2026-08-04
**Extensions active**: Security Baseline

Consolidation of `components.md`, `component-methods.md`, `services.md` and `component-dependency.md`. Those
documents hold the detail; this one holds the shape, the decisions and their consequences.

---

## 1. The design in one page

**Three deployment units, from two container images.**

| Unit | Runtime | Job | Clock |
| --- | --- | --- | --- |
| **Front Door** | Lambda + function URL | Verify, deduplicate, acknowledge, hand off | **10–15 seconds, enforced by Microsoft** |
| **Worker** | Lambda, async-invoked | Invoke the agent, stream the reply into Teams | none |
| **Agent** | AgentCore Runtime (ARM64) | Reason. Knows nothing about Teams | none |

**The problem the design exists to solve**: a Lambda behind a function URL **returns and freezes**. FR-9
demands an acknowledgement in milliseconds; FR-17 demands the answer arrive as a series of later outbound
POSTs. Those cannot both happen in one invocation, so the work is split at the acknowledgement — and that split
is the whole architecture.

**Twelve components across those units** — see `components.md`. Four are security-critical: `JwtValidator`
(the control), `TokenProvider` and `GatewayClient` (each reads a secret), and `Logger` (must not leak).

---

## 2. Decisions taken, and what each bought

| # | Decision | Consequence |
| --- | --- | --- |
| Q1 | **Separate worker Lambda** does delivery | The agent stays channel-agnostic and reusable; Bot Framework knowledge is confined to two components |
| Q2 | **Async invoke** as the hand-off | Simplest possible; **but AWS retries twice on error**, which is a second duplicate source |
| Q3 | **Channel-agnostic agent** | Enforced by the dependency graph, not just documented — the agent has no path to `BotFrameworkClient` |
| Q4 | **Normalised `Envelope`** | Nothing downstream of the front door depends on Bot Framework's wire format |
| Q5 | **Streaming** | Producer–consumer pipeline; the answer publishes while it is still being generated |
| Q6 | **DynamoDB idempotency** | Two conditional guards covering two independent duplicate sources |
| Q7 | **Agent reads its own history** | Memory concerns stay inside the agent |
| Q8 | **Shared internal module** | One `src/shared/`, imported by all three units |
| Q9 | **JWT validation local but self-contained** | Depends only on `Logger`; extraction later is a file move |
| Q10 | **Python 3.12 / ARM64** | Matches AWS's AgentCore reference and the repo's existing tooling |
| Q11 | **One Dockerfile, two targets** | `codebuild.yml` already builds `--target`; the two Lambdas share the `lambda` image |
| Q12 | **Generic message + correlation ID** | Satisfies SECURITY-09/15 while remaining useful to whoever reads logs |
| Q13 | **No house style exists** | Follow `validate_stacks.py` and `hello-world.yml` conventions |

### The decision with the longest reach

**Q1.** Letting the agent talk to Teams directly would have been fewer moving parts. Choosing a separate worker
means the entire reasoning half — `Agent`, `GatewayClient`, AgentCore Memory — is reusable by a future Slack,
web or voice blueprint without modification. `component-dependency.md` costs that out: a new channel needs one
new delivery strategy and four replaced components, and touches nothing in the reasoning path.

---

## 3. Service boundaries

Drawn where a **trust, timing or reusability** change occurs.

| Boundary | What changes |
| --- | --- |
| Azure Bot Service → IngressService | **Trust** — untrusted becomes verified |
| IngressService → ConversationService | **Timing** — the acknowledgement deadline stops applying |
| ConversationService → AgentService | **Reusability** — Teams ends, generic reasoning begins |

```
  Azure Bot Service
        |  activity + JWT
        v
  IngressService ---- 200 OK (immediately) ----> Azure Bot Service
        |
        |  async invoke, Envelope
        v
  ConversationService <---- SSE chunks ---- AgentService ----> LiteLLM gateway
        |
        |  cumulative streaming POSTs
        v
  Bot Framework REST API ----> user watches the reply appear
```

**Text alternative.** Azure Bot Service sends an activity with a JWT to IngressService, which returns `200 OK`
immediately and then asynchronously invokes ConversationService with a normalised envelope. ConversationService
invokes AgentService, which calls the LiteLLM gateway and streams text chunks back as server-sent events. As
chunks arrive, ConversationService posts cumulative streaming updates to the Bot Framework REST API and the user
watches the reply appear.

**Least privilege falls out of the boundaries rather than being bolted on.** IngressService — the only
internet-facing component — can write one DynamoDB item and invoke one Lambda. **It cannot read any secret and
cannot invoke AgentCore.** Compromising the public endpoint yields the ability to enqueue a work item, and
nothing else.

---

## 4. Where the known bugs are designed out

The prototype's `serviceurl` check read correctly, passed review, and did nothing. Rather than rely on whoever
implements this remembering that, several interfaces are shaped so the bug is not expressible:

| Interface choice | Bug prevented |
| --- | --- |
| `validate(auth_header, activity)` takes both | A validator that structurally cannot check `serviceurl` |
| `ValidationResult.ok` — no third state | Absent claim treated as a pass (**the prototype's actual bug**) |
| `_continue(..., cumulative, seq)` | Sending deltas where Teams requires cumulative text |
| `_finalise(...)` has **no** `seq` parameter | Setting `streamSequence` on the final message |
| `invoke_agent(...) -> Iterator[str]` | Buffering the whole answer and silently losing streaming |
| `claim() -> bool` **and** `begin_delivery() -> bool` | Covering only one of the two duplicate sources |
| `AgentRequest` has no Teams fields | Coupling the agent to Bot Framework |
| `TokenProvider` reads its own secret | A credential travelling through call signatures |

**`normalize_service_url()` exists as one function** used by both the JWT check and reply URL construction, so
the two cannot disagree — the prototype's second defect was relying on an undocumented trailing slash.

---

## 5. Security Baseline verification

Evaluated against these design artifacts, as the extension requires before a completion message.

| Rule | Status | Where it lives in the design |
| --- | --- | --- |
| **SECURITY-01** Encryption | **Compliant** | DynamoDB encrypted at rest by default; every external call HTTPS; AgentCore Memory managed |
| **SECURITY-02** Access logging | **Compliant — compensating control** | `Logger.log_inbound_request()` exists as a **named function** so the control is discoverable, not scattered. A function URL has no access log |
| **SECURITY-03** App logging | **Compliant** | `Logger`, JSON, correlation ID = activity id, spanning all three services. No bodies or secrets |
| **SECURITY-04** HTTP headers | **N/A** | No HTML served |
| **SECURITY-05** Input validation | **Compliant** | `JwtValidator` then `ActivityNormalizer`, which validates shape and enforces size bounds and raises on malformed input |
| **SECURITY-06** Least privilege | **Compliant** | Per-service allow/deny table in `services.md`. Specific ARNs; ingress holds no secret |
| **SECURITY-07** Network config | **Compliant — documented exception** | No VPC. The public function URL is required — Azure's source addresses are not fixed. Authorisation is at the application layer |
| **SECURITY-08** Access control | **Compliant** | Deny by default; token validated on **every** request; `serviceurl` correlation. CORS N/A |
| **SECURITY-09** Hardening | **Compliant** | No credential in code; user-facing errors are a generic message plus a correlation ID |
| **SECURITY-10** Supply chain | **Compliant** | `uv.lock` required by `uv sync --frozen`; pinned base image; image referenced by digest |
| **SECURITY-11** Secure design | **Compliant — noted limitation** | `JwtValidator` is a dedicated isolated module; layered validation/authorisation/TLS. **Rate limiting remains a gap** — a function URL has none, so reserved concurrency bounds blast radius rather than preventing abuse. Misuse case addressed: valid token, attacker-controlled `serviceUrl` |
| **SECURITY-12** Credentials | **Compliant** (mostly N/A) | No user authentication of our own. `TokenProvider` and `GatewayClient` each read their own secret; none is passed between components |
| **SECURITY-13** Integrity | **Compliant** | Untrusted JSON validated before use, never deserialised into arbitrary types; image digest-pinned; `main` is PR-only with one human approval |
| **SECURITY-14** Alerting | **Compliant** | ≥90-day retention; `ValidationResult.reason` is a stable machine-readable string **specifically so validation-failure alarms can filter on it**; roles cannot delete their own log groups |
| **SECURITY-15** Fail-safe | **Compliant** | IngressService fails **closed and silent**; ConversationService fails **visible** (there is a user waiting) then still calls `complete()` so the automatic retry does not produce a second apology; JWKS unavailability stops the bot entirely, which is correct |

**No blocking security findings.** Two items carry a compensating control or documented exception —
SECURITY-02 and SECURITY-07 — and SECURITY-11 carries a stated limitation. All three follow from choosing a
Lambda function URL over API Gateway and were accepted at Requirements Analysis.

---

## 6. Design risks

| # | Risk | Mitigation in the design |
| --- | --- | --- |
| 1 | Worker Lambda timeout left at the 3-second default would truncate **every** reply | Recorded as an explicit requirement; ~5 minutes |
| 2 | Teams streaming rules are intricate and fail confusingly | Concentrated in `StreamingDelivery`; two rules encoded in method signatures |
| 3 | Two independent duplicate sources, one of them internal | Two conditional guards on one table |
| 4 | AgentCore cold start after the ack | Harmless — no clock is running. The user sees the informative update |
| 5 | Container build path has never executed | Prove with a trivial container before wiring the real agent |
| 6 | Streaming adds a second failure surface mid-reply | Apology path plus correlation ID; `complete()` still called |

---

## 6a. Open design choice added 2026-08-04 — certificate or secret for outbound auth

`docs/teams-chatbot-docs/Teams Admin CLI Automation - Findings 2026-08-03.md` (which absorbed the
former `Entra CLI Automation - Research 2026-08-03.md`) raises a choice that affects `TokenProvider` and
is better decided deliberately than inherited from the prototype.

| | Client secret | Certificate |
| --- | --- | --- |
| `TokenProvider` implementation | send the secret in a `client_credentials` request | **sign a client assertion** — more code |
| Expiry | expires; a person must track it (risk R-3) | **removes R-3** |
| Storage | Secrets Manager | Secrets Manager (private key) |
| Provisioning | `az ad app credential reset` | certificate generation and upload |

The prototype used a secret, so a secret is the path of least resistance — but it is the path that carries an
expiry that will silently break the bot months later. **Recorded as a decision for Infrastructure Design**, not
settled here. `TokenProvider.get_token()`'s signature is unaffected either way, so this choice does not
propagate beyond that one component — which is itself an argument that the current boundary is drawn correctly.

---

## 7. Deferred to Functional Design (CONSTRUCTION)

Deliberately absent here, per this stage's scope:

- validation ordering and the precise error taxonomy
- chunk-buffering arithmetic against the 1/second limit and 1.5–2s guidance
- retry and backoff policy for gateway and Bot Framework calls
- prompt assembly and history-window trimming
- greeting/farewell text templating
- AgentCore Memory key structure and retention

---

## 8. Traceability

| Requirement | Realised by |
| --- | --- |
| FR-6, FR-7 | Front Door unit, function URL, deterministic `FunctionName` |
| FR-8, FR-8a | `JwtValidator` — plus the negative test its interface makes possible |
| FR-9, FR-10 | IngressService — every exit path returns `200` |
| FR-11 | `IdempotencyStore`, two guards |
| FR-12, FR-13 | `ActivityNormalizer` — `classify_conversation`, `human_members`, tolerates absent `text` |
| FR-14 | `normalize_service_url()` — one function, two consumers |
| FR-15 | `JwtValidator._signing_key` — refresh on `kid` miss |
| FR-16 | `DeliveryDispatcher` + `select_strategy` |
| FR-17 | `StreamingDelivery` |
| FR-18 | `SingleReplyDelivery` |
| FR-19, FR-20 | `BotFrameworkClient`, `TokenProvider` |
| FR-21, FR-22 | Agent unit — SigV4 in-account, `/ping` + `/invocations`, ARM64 |
| FR-23, FR-23a | `GatewayClient` — service key from Secrets Manager |
| FR-24 | AgentCore Memory, read by the Agent (Q7) |
| FR-25 | Tier B — out of scope; the Agent is where `Retrieve` would attach |
| FR-3a | `ConfigProvider` — S3 fetch for oversized prompts |
