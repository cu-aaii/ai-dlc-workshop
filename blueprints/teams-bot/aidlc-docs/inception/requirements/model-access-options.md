# Model Access — Bedrock-Native vs Cornell's LiteLLM Gateway

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (research input)
**Trigger**: user disclosed that Cornell operates a LiteLLM gateway, configured in
`~/.claude/settings.json` (outside this repository)

**No credential appears in this file.** The gateway configuration contains a live API key. It was
read to identify the endpoint and query the model catalogue; the key itself is not reproduced here
and must never be committed. See §5.

---

## 1. What exists

Cornell runs an **Anthropic-API-compatible LiteLLM gateway** at:

```
https://api.ai.it.cornell.edu
```

Authenticated with a bearer key. A read-only `GET /v1/models` against it returns:

| Model ID | Kind |
| --- | --- |
| `claude-opus-5` | chat |
| `claude-opus-4-8` | chat |
| `claude-opus-4-7` | chat |
| `claude-opus-4-6` | chat |
| `claude-sonnet-5` | chat |
| `claude-sonnet-4-6` | chat |
| `claude-haiku-4-5` | chat |
| `google-enterprise-web-search` | tool/search |

Two observations from that list:

- It is **multi-provider**, not Anthropic-only — `google-enterprise-web-search` is served through
  the same endpoint. So the gateway is a genuine abstraction layer, not just a proxy.
- The local configuration aliases Haiku to `gemini-3.5-flash-lite`, which **does not appear in the
  returned catalogue**. Either the catalogue is scoped by key permissions or that alias is stale.
  Worth knowing before depending on a specific alias, but immaterial to the architecture.

---

## 2. First, the thing that was unclear: this does not conflict with AgentCore

The user's earlier uncertainty was whether AgentCore was "part of it". Adding LiteLLM could look
like a second, competing answer. It is not.

**AgentCore Runtime is a hosting, identity and memory layer. It does not dictate where inference
comes from.** It runs your ARM64 container on port 8080 and routes `/invocations` to it. What that
container calls is entirely its own business — Bedrock, Cornell's gateway, or both.

So these compose cleanly:

```
+-----------------------------------------------+
|  AgentCore Runtime  (hosting, identity,       |
|                      memory, observability)   |
|                                               |
|   your container:                             |
|     GET  /ping                                |
|     POST /invocations                         |
|         |                                     |
|         +--> Bedrock InvokeModel      (opt A) |
|         +--> api.ai.it.cornell.edu    (opt B) |
+-----------------------------------------------+
```

**Text alternative.** AgentCore Runtime provides hosting, identity, memory and observability, and
runs a container exposing `GET /ping` and `POST /invocations`. From inside that container, model
calls may go either to Bedrock via `InvokeModel` (option A) or outbound to Cornell's LiteLLM
gateway at `api.ai.it.cornell.edu` (option B). AgentCore is indifferent to which.

The same is true of Strands, if Q3 selects an agentic implementation: Strands supports multiple
model providers, including OpenAI/Anthropic-compatible endpoints, so a LiteLLM backend is a
configuration choice rather than a rewrite.

---

## 3. The actual decision, with the trade-offs that matter here

### Option A — Bedrock-native inference

Call `bedrock:InvokeModel` (or a cross-region inference profile) from the agent's execution role.

**For:**
- IAM-authenticated. **No API key at all**, therefore no secret to store, rotate or leak. In a
  repository that is public with secret scanning disabled, "no credential exists" is a materially
  stronger position than "the credential is stored correctly".
- Cost lands **in the workshop AWS account**, where the `cornell:*` tags and the cost dashboard
  can see it.
- No dependency on a service outside the account boundary.
- **Required anyway if retrieval is in scope** — see §4.

**Against:**
- Per-account model entitlement is a separate grant and remains **unverified** (DevOps question B).
  It could not be checked read-only without invoking a model.
- Catalogue is Bedrock's, so the newest Anthropic releases may lag the gateway's.

### Option B — Cornell's LiteLLM gateway

Call `https://api.ai.it.cornell.edu` with a bearer key from Secrets Manager.

**For:**
- **Model access is already solved.** This is the immediate practical appeal: it sidesteps DevOps
  question B entirely for chat inference.
- Access to `claude-opus-5` / `claude-sonnet-5` and a web-search tool, plus whatever Cornell adds
  later, without touching the blueprint.
- Central governance and consistency with how the rest of Cornell's AI work is configured.

**Against:**
- **Requires a long-lived API key.** It must live in Secrets Manager (hard constraint), which is
  satisfiable — but it reintroduces exactly the class of credential that is currently the largest
  live risk in this project.
- **Cost becomes invisible to this account's observability.** Spend lands on Cornell's central AI
  budget, not the AWS bill, so the `cornell:*` tag-driven cost dashboard — which is a stated
  purpose of the four-tag convention — **will not see it**. That is a direct, if partial,
  contradiction of the tagging rationale in `CLAUDE.md`, and it should be an explicit accepted
  trade-off rather than a surprise discovered later.
- Adds an external network dependency with an availability characteristic nobody has stated. If a
  VPC is ever mandated (still open), egress to a Cornell endpoint needs allowlisting.
- The endpoint is Cornell-internal infrastructure; whether it is reachable from an AWS account, and
  whether that is an approved use, is **not established**.

### Option C — both

LiteLLM for chat inference, Bedrock for embeddings. This is the likely landing point if Q3 selects
retrieval, for the reason in §4.

---

## 4. The constraint that decides it if Q3 lands on retrieval

**The LiteLLM catalogue contains no embeddings model.** Every entry is chat or search.

`AWS::Bedrock::KnowledgeBase` requires a **Bedrock** embeddings model — it is configured with a
Bedrock model ARN, not an arbitrary HTTP endpoint. It cannot be pointed at the gateway.

Therefore:

| If Q3 selects | Model access needed |
| --- | --- |
| A (echo) or B (fixed responses) | **None.** No model access of any kind. |
| C (model passthrough) | Either option. Genuine choice. |
| **D (retrieval / Knowledge Base)** | **Bedrock required** for embeddings, regardless of what serves chat. |
| E (agentic) | Either for inference; Bedrock if the agent also retrieves. |

**So DevOps question B does not go away.** If retrieval is in scope, Bedrock per-account model
entitlement must be confirmed no matter what the gateway offers. The reconnaissance did confirm
`amazon.titan-embed-text-v1`, `cohere.embed-v4:0` and `amazon.nova-2-multimodal-embeddings-v1:0`
are listable in the region — but listable is not the same as entitled.

---

## 5. Credential note

The gateway key is stored in `~/.claude/settings.json` — a developer machine configuration file,
**outside this repository**, so unlike the previously reported items there is no risk of it being
committed from here.

It is nonetheless a **fourth live credential** now in play alongside the Entra client secret, the
n8n bearer token and the GitHub PAT. Recording it for completeness of the exposure picture, not
because it needs the same urgency.

If option B or C is chosen, that key — or more likely a separate key issued for the bot — becomes
a Secrets Manager entry and the first secret this repository's infrastructure ever reads. Following
the convention observed in the platform team's other account, the natural name would be
`aidlc/main/<name>`.

One genuine upside worth noting: a gateway API key is a **simpler first secret** than the Entra
client secret. Read one value, put it in a header. If the design wants to prove the
Secrets-Manager-to-runtime pattern before taking on Entra's token exchange, this is the easier
first instance.

---

## 6. Effect on open questions

| Question | Effect |
| --- | --- |
| **New — Q26** | Added to `requirement-verification-questions.md`. Which model access path? |
| Q3 (capability) | Unchanged, but now determines whether Bedrock entitlement is mandatory (§4). |
| DevOps B (Bedrock entitlement) | **Still open, and still mandatory if Q3 → D.** Not resolved by the gateway. |
| DevOps 10 (VPC) | Slightly more consequential — option B adds egress to a Cornell endpoint. |
| Q20 (data sensitivity) | **Newly relevant.** Option B sends message content to a Cornell-operated gateway rather than keeping it inside the AWS account boundary. For a course chatbot with a FERPA dimension, where inference happens and what the gateway logs is a question worth an explicit answer. |

That last row is the one most likely to be overlooked. It is not an objection — a Cornell-operated
gateway may well be the *preferred* place for Cornell data — but it changes the data-flow diagram
and therefore the answer to Q20.

---

## 7. DECIDED 2026-08-03 — Option B, as a hard constraint

**All model traffic must route through the LiteLLM gateway.** Stated rationale: it is how Cornell
obtains the full model list **and the ability to handle medium-risk data**.

This is a compliance constraint, not a preference, so §3's trade-off framing is superseded. Two
corrections to what is written above:

**Correction 1 — the Q20 framing in §6 was backwards.** I recorded sending content to the gateway
as a data-flow change to weigh. In fact the gateway is the **governed channel that makes
medium-risk data permissible at all**. Routing inference through it is the control, not the risk.
Bedrock-direct inference is the non-compliant path here.

**Correction 2 — the secrets-posture argument in §3 no longer applies.** "Bedrock-native needs no
API key" is true but irrelevant: the no-key option is not available. The gateway key **must** be
held in Secrets Manager, so this blueprint necessarily becomes the first thing in this repository
to read a secret at runtime. That pattern is now required rather than optional.

### CORRECTED 2026-08-03 — the gateway does have embeddings; my earlier finding was a key-scope artifact

**The "no embeddings model" conclusion below was wrong, and the reason matters.**

The gateway offers a substantial embeddings catalogue, supplied by the user:

| Gateway model ID | Price (per 1M tokens, USD) |
| --- | --- |
| `amazon.titan-text-embeddings.v2` | 0.02 |
| `openai.text-embedding-3-small` | 0.02 |
| `cohere.embed-english.v3` | 0.10 |
| `text-embedding-005` | 0.10 |
| `text-multilingual-embedding-002` | 0.10 |
| `openai.text-embedding-ada.002` | 0.10 (legacy — prefer `-3-small`) |
| `cohere.embed-v4` | 0.12 |
| `openai.text-embedding-3-large` | 0.13 |
| `amazon.nova-2-multimodal-embeddings.v1` | 0.135 (+ per-image/per-second charges) |
| `gemini-embedding-001` | 0.15 |
| `gemini-embedding-2` | 0.20 |
| `multimodalembedding` | 0.80 |

`gemini-embedding-001` is noted as multilingual with selectable dimensions up to 3072.

**Why `GET /v1/models` did not show them.** The key in the developer configuration is a LiteLLM
**virtual key scoped to `llm_api_routes`**. `/v1/models` returns only the models that key is
entitled to call, and `/model/info` is refused outright:

```
{"detail":"Virtual key is not allowed to call this route.
           Only allowed to call routes: ['llm_api_routes'] ..."}
```

So the observation was accurate and the inference from it was not: it was never "the gateway has no
embeddings", it was "**this key** cannot see or call any embeddings model".

**This creates a concrete requirement.** The key issued for the bot must be scoped to include both
chat completions **and** embeddings. That folds into the service-key question already raised — a
per-deployment key, scoped for both, is what to ask the gateway operator for. A key scoped like the
developer one would fail at runtime on the first embedding call, and only then.

Note also that gateway model IDs use their own naming — `amazon.titan-text-embeddings.v2`, not
Bedrock's native `amazon.titan-embed-text-v2:0`. Configuration must use the gateway's identifiers.

### The consequence that survives the correction: `AWS::Bedrock::KnowledgeBase` is still unusable

Retrieval is no longer blocked on availability. It is still blocked on **routing**, for a different
reason, and this is the part worth being precise about.

`AWS::Bedrock::KnowledgeBase` is configured with a **Bedrock embedding model ARN**. It calls that
model itself, internally, as part of ingestion and of every `Retrieve` call. There is no
configuration surface to send those calls to `api.ai.it.cornell.edu` instead — so a Bedrock
Knowledge Base **structurally bypasses the gateway**, regardless of the gateway offering the same
Titan model.

The med-risk dimension makes this concrete rather than pedantic: a `Retrieve` call embeds **the
user's query text**. Under a rule that all model traffic routes through the gateway, sending user
queries straight to Bedrock is the thing the rule exists to prevent.

So three routes to retrieval remain:

- **R1 — Bedrock Knowledge Base with an explicit, granted exception** for its internal Bedrock
  embedding calls. Least to build; requires someone with authority to agree that AWS-internal
  Bedrock calls within Cornell's own account are acceptable for medium-risk data. That is a
  compliance decision, not an engineering one.
- **R2 — self-managed vectors, embeddings via the gateway.** Fully compliant with the routing rule.
  Embed through the gateway, store vectors in something we control — S3 Vectors, OpenSearch
  Serverless, or Aurora PostgreSQL with `pgvector`. More to build, and it introduces the project's
  first data store.
- **R3 — no vector search.** Keyword or full-text retrieval, or `google-enterprise-web-search` where
  the corpus is public web content rather than course material. Cheapest, least capable.

**R1 versus R2 is the decision to put in front of whoever owns the med-risk classification**, and it
is worth doing before design rather than during. R2 is the safe default if no answer arrives.

#### Firmed up 2026-08-03 — R2 is now the clear route, and R1 is harder to justify

Confirmed by the user: **the gateway 100% allows medium-risk data.** That does not help R1 — it makes it
harder to defend.

The logic: the gateway is the *approved channel* for medium-risk data, and that approval is the stated
reason all traffic must route through it. R1's problem was never that Bedrock is unsafe; it is that a
Bedrock Knowledge Base **bypasses the gateway entirely**, embedding the user's query text via a direct
Bedrock call with no configuration surface to redirect it. Establishing more firmly that the gateway is
*the* sanctioned path makes the bypass more clearly the exception it always was.

So this is not a change of conclusion but a strengthening of it:

- **R2** — embed through the gateway, store vectors in something we control (S3 Vectors, OpenSearch
  Serverless, or Aurora with `pgvector`) — is compliant by construction and needs no exception granted.
- **R1** — Bedrock Knowledge Base — still needs someone with authority to accept that its internal
  embedding calls sit outside the approved channel. That is now a narrower and more awkward ask than
  before.

**Recommendation: plan on R2 if retrieval is in scope.** It costs more to build and it does not require
anyone to sign off on an exception, which on a two-day timeline is likely the faster path in practice.
Still contingent on Q3 selecting retrieval at all.

### The original, now-superseded analysis

Two facts now collide:

1. All model traffic must route through the gateway.
2. The gateway catalogue exposes **no embeddings model** — `GET /v1/models` returns chat models and
   `google-enterprise-web-search`, nothing else.

Any vector-search retrieval needs an embeddings model. `AWS::Bedrock::KnowledgeBase` needs a
**Bedrock** embeddings model ARN specifically, which by (1) is not an available call.

**Therefore Q3 option D — retrieval-augmented answers over a Bedrock Knowledge Base — cannot be
built as described.** Not "is harder"; cannot, as specified, without one of:

- **D1** — the gateway exposes an embeddings model (it may already and simply not advertise it in
  `/v1/models`; this is a question for the gateway operator, not something to probe by guessing).
- **D2** — a narrow, explicitly granted exception permitting embeddings calls direct to Bedrock,
  which would need to be reconciled with the medium-risk data rule, since embedding text means
  sending that text to Bedrock.
- **D3** — retrieval without vector search: keyword or full-text search, or
  `google-enterprise-web-search` if the corpus is public web content rather than course material.
- **D4** — defer retrieval out of the first version.

**This is now the highest-value open question in the project**, because it determines whether the
headline capability most people imagine for a "course chatbot" is reachable at all. It is also
cheap to resolve — one question to whoever operates the gateway.

### Cost attribution is now a known limitation rather than a choice

Gateway spend lands on Cornell's central AI budget, so it will not appear in the AWS bill and the
`cornell:*` tag-driven cost dashboard cannot see it. Since the gateway is mandatory, this is no
longer a trade-off to accept — it is a **gap in the observability design** that whoever builds the
cost dashboard needs to know about. Per-blueprint model spend will have to come from the gateway's
own accounting, keyed on whatever identifier the bot's API key carries.

Worth raising with the gateway operator: **can a distinct key be issued per blueprint or per
deployment**, so spend is attributable the way the tags were meant to make it? If yes, that is the
bridge between the two systems and it costs nothing to set up now.

### Consequences for constraints already recorded

| Previously | Now |
| --- | --- |
| VPC assumption: no VPC, public egress | **Weaker.** Medium-risk data may carry a network requirement. Egress must reach `api.ai.it.cornell.edu`; if that is campus-reachable only, a VPC and routing become mandatory rather than optional. Re-ask. |
| Q7 ingress: Lambda function URL, `AuthType: NONE` | **Needs re-examination.** An unauthenticated-at-the-edge public endpoint handling medium-risk data is more likely to attract a security review than the same endpoint handling test traffic. API Gateway with WAF becomes more defensible. |
| AgentCore CloudTrail caveat | **More pointed.** AgentCore's JWT inbound auth writes claims including Subject to CloudTrail, and AWS warns against PII there. Under a medium-risk classification this needs a definite answer, not a note. |
| DevOps question B (Bedrock entitlement) | **Largely moot for chat.** Still decisive for embeddings, via D1/D2 above. |
