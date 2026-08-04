# Knowledge Base Integration — Bedrock AgentCore Managed Knowledge Base

**Created**: 2026-08-04
**Stage**: INCEPTION - Requirements Analysis (research input)
**Source**: AWS documentation supplied by the user — `kb-managed-create` and
`kb-managed-customize-ingestion`, read in full 2026-08-04.
**Supersedes**: the three-way ambiguity in `blueprint-configuration-surface.md` §4a-bis, and my R2
recommendation in `model-access-options.md` §4.

**Summary: this is much better news than the previous position, and it retires three of my earlier
cautions.** The Knowledge Base team is using **Amazon Bedrock AgentCore Managed Knowledge Base**, which
owns chunking, embedding, storage *and* retrieval. Nothing is unowned, the embedding-model-mismatch risk
disappears, and this blueprint's share of retrieval work collapses to a parameter and an IAM statement.

---

## 1. What it actually is, and why the S3 confusion arose

From the documentation's opening line:

> When you create a managed knowledge base, **Amazon Bedrock AgentCore** manages the storage, indexing,
> and retrieval infrastructure for you.

The console path is **Amazon Bedrock AgentCore → Built-in tools → Knowledge Base**. So this is not a
separate service bolted alongside AgentCore — it is an **AgentCore built-in tool**. That makes it
architecturally coherent with Team E's AgentCore mandate rather than in tension with it.

**The key correction: the S3 bucket is the knowledge base's *data source*, not its vector store.**

```
  +------------------+     ingestion      +----------------------------+
  |  S3 bucket       | -----------------> |  Managed Knowledge Base    |
  |  (documents)     |  StartIngestionJob |   - smart parsing          |
  |  KB team owns    |                    |   - chunking               |
  +------------------+                    |   - embedding              |
                                          |   - vector storage         |
                                          |   - retrieval             |
                                          +-------------+--------------+
                                                        |
                                                        | Retrieve  (chunks)
                                                        v
                                          +----------------------------+
                                          |  Teams bot agent           |
                                          |  puts chunks in the prompt |
                                          |  generates via the gateway |
                                          +----------------------------+
```

**Text alternative.** The Knowledge Base team owns an S3 bucket containing documents. A
`StartIngestionJob` call ingests those documents into a Managed Knowledge Base, which performs smart
parsing, chunking, embedding, vector storage and retrieval — all managed by Bedrock AgentCore. The Teams
bot calls the `Retrieve` API to get relevant chunks, places them in its prompt, and generates the answer
through the LiteLLM gateway. The Teams bot never touches the S3 bucket.

**So the three-way ambiguity I raised is resolved, and it is the best of the three cases.** The bucket
holds documents, and the KB team's blueprint owns everything downstream of it. My concern that "chunking,
embedding and search may be unowned" does not apply.

**Correction to what I recorded last turn**: this blueprint's parameter should be a **knowledge base ID**,
not a bucket name. Reading the bucket directly would mean duplicating their ingestion pipeline — precisely
the wrong thing. `KnowledgeStoreLocation` becomes `KnowledgeBaseId`, and **the bucket is none of our
business.**

---

## 2. The one design requirement that matters: use `Retrieve`

Managed knowledge bases offer **two** query surfaces, and `RetrieveAndGenerate` is **not one of them**:

> **This API cannot be used with managed knowledge bases.** Use AgenticRetrieveStream or Retrieve with
> managed knowledge bases.

The two available options differ in a way that matters a great deal here:

| | **`Retrieve`** | `AgenticRetrieveStream` |
| --- | --- | --- |
| Output | Raw chunks + relevance scores | Deduplicated chunks (streaming), optional grounded answer |
| **Foundation model cost per call** | **None** | **Multiple invocations** |
| Latency | **Lowest** | Highest |
| Query decomposition | No | Yes |
| Multi-KB | No | Yes, up to 5 |
| Streaming | Sync only | Always |
| Relevance scores | In results directly | Trace events only |
| Guardrails | Supported | BLOCK only (MASK unsupported) |
| Query size | 10,000 characters | 10,000 characters |

**Requirement: use `Retrieve`.** Three reasons, in order of importance:

1. **It makes no foundation model invocation.** `AgenticRetrieveStream` makes *multiple* FM calls inside
   Bedrock — that is generative LLM inference happening outside the LiteLLM gateway, which is a
   substantial deviation from the Q26 mandate. `Retrieve` keeps **all** generation on the gateway and
   limits Bedrock's involvement to embedding the query for similarity search.
2. **Lowest latency**, which matters even under streaming since retrieval sits in front of first token.
3. **We keep control of generation**, which is the whole point of the gateway mandate.

`AgenticRetrieveStream` is genuinely more capable for multi-part and comparative questions, and is worth
revisiting later — but it should be an explicit decision with the gateway implication understood, not a
default.

---

## 3. Three of my earlier cautions are now retired

Stating these plainly because they were emphasised and should not linger as live concerns.

**a) The embedding-model-match risk is gone.** I warned that vectors from different models are not
comparable, so if we embedded queries ourselves we would have to use the KB team's exact model or get
silently wrong results. **Bedrock embeds both sides**, so consistency is guaranteed by construction. There
is no `EmbeddingModelId` parameter to thread through and no silent-failure mode. Drop it.

**b) "Search may be unowned" does not apply.** The managed KB owns retrieval. This was my sharpest concern
about the plain-S3-bucket answer and it is resolved.

**c) The R2 recommendation is moot.** `model-access-options.md` recommended R2 — self-managed vectors with
embeddings through the gateway — because R1 (Bedrock Knowledge Base) bypasses the gateway. **The KB team
has chosen R1, and that decision is theirs to make, not this blueprint's.** Since the retrieval service is
an AgentCore built-in tool and AgentCore is mandated, R1 is evidently the intended platform direction. This
blueprint should consume it rather than build a parallel R2 pipeline — which would be exactly the
duplication the blueprint layer exists to prevent.

**One factual note for Marty, recorded once and not argued**: with a managed knowledge base, Bedrock
embeds the user's query text internally rather than through the gateway. That is inherent to the service,
not a configuration choice. Choosing `Retrieve` over `AgenticRetrieveStream` limits Bedrock's footprint to
that embedding call and keeps all generative inference on the gateway. Noting it so it is on the record; the
architecture is the platform's call and it appears already made.

---

## 4. What this blueprint actually has to build for Tier B

Almost nothing. This is the headline.

| Item | Detail |
| --- | --- |
| **Stack parameter** | `KnowledgeBaseId` — supplied by the MCP, consistent with parameter-not-`!ImportValue` |
| **IAM** | Permission for the `Retrieve` action on that knowledge base ARN, on the AgentCore execution role |
| **Agent code** | Call `Retrieve`, take the chunks, put them in the prompt, generate via the gateway |
| **No S3 access** | Do **not** grant or use `s3:GetObject` on their bucket — that was based on the earlier misunderstanding |
| **No vector store** | No `AWS::S3Vectors::*`, no OpenSearch, no Aurora. The verification I did of those types is no longer relevant to this blueprint. |

**Worth investigating during design**: because the managed KB is an **AgentCore built-in tool**, an agent
running on AgentCore Runtime may be able to use it as a native tool rather than us hand-coding a `Retrieve`
call and prompt assembly. That would be cleaner still. Not assumed here.

---

## 5. Constraints worth knowing — several are irreversible

These mostly bind the KB team, but two affect us and all are cheap to know now.

**Irreversible after creation:**

- **Embedding model type cannot be changed** after the knowledge base is created — switching between
  `MANAGED` and `CUSTOM` requires creating a **new** knowledge base.
- **Chunking strategy cannot be changed** after connecting the data source.

Both are worth flagging to the KB team before they create anything, because the remedy is a rebuild.

**Embedding model options:**

- `MANAGED` (default) — a service-managed model; no selection, no dimensions, no Bedrock service limits to
  manage.
- `CUSTOM` — your own Bedrock embedding model ARN, dimensions 1024, float32. Supported: Titan Text
  Embeddings V2, Cohere Embed English v3, Cohere Embed Multilingual v3, Cohere Embed v4, Nova Multimodal
  Embeddings.
- **If `CUSTOM` is chosen, the managed reranker is unavailable.** Reranking materially improves retrieval
  quality, so this is a real trade-off rather than a footnote. `MANAGED` is the better default unless
  there is a specific reason.

**Parsing and chunking:**

- **Only `SMART_PARSING`** is supported. `BEDROCK_FOUNDATION_MODEL` and `BEDROCK_DATA_AUTOMATION` are not.
- **Semantic chunking is not supported** for managed knowledge bases.
- Default chunking is **fixed-size, 300 tokens, 20% overlap**. Alternatives are `FIXED_SIZE` with your own
  values, or `NONE` for pre-split documents.

**Affects us directly:**

- **Query size limit is 10,000 characters.** A Teams message will not approach this, but a design that
  concatenates conversation history into the retrieval query could. Truncate deliberately.
- Advanced indexing can cover visual content in documents, audio and video files — relevant only if the
  corpus includes them.

---

## 6. A risk to raise with the KB team

**Can a managed knowledge base be created in CloudFormation?**

Marty's constraint is CloudFormation, no click-ops. The documentation shows the console flow and the
`aws bedrock-agent create-knowledge-base` CLI call with `"type": "MANAGED"`. `AWS::Bedrock::KnowledgeBase`
exists and is `FULLY_MUTABLE` in this account, but **whether that resource type supports
`type: MANAGED` and `managedKnowledgeBaseConfiguration` was not verified** — the CLI examples are not
evidence that the CloudFormation resource has caught up, and managed KBs are a newer offering.

This is the KB team's problem rather than ours, but it is worth raising early: if managed knowledge bases
turn out to be API-only, their blueprint cannot be pure CloudFormation, and they would need either a custom
resource or an explicit exception from Marty. Better discovered now than at merge time.

**It does not block this blueprint**, since we only consume a knowledge base ID.

---

## 7. Net effect

| Previously | Now |
| --- | --- |
| Tier B = build the R2 pipeline (~few hundred lines + storage) | **Tier B = one parameter, one IAM statement, and prompt assembly** |
| Embedding-model-match a silent-failure risk | **Eliminated** — Bedrock embeds both sides |
| "Search may be unowned" | **Owned by the managed KB** |
| Vector store choice open (S3 Vectors / OpenSearch / Aurora) | **Not our decision at all** |
| R2 recommended | **R1 chosen by the KB team; consume it** |
| KB storage an open dependency blocking Tier B | **Largely closed.** Remaining unknown is only the `KnowledgeBaseId` value and their timeline. |

**Tier B is now cheap enough that it is worth reconsidering whether it belongs in v1** — the earlier
argument for deferring it was several hundred lines of vector plumbing, and that argument has evaporated.
The remaining reason to defer is only that the knowledge base does not exist yet. If the KB team produces
one within the two days, Tier B becomes a small addition rather than a second project.

Recorded as an update to Q3 rather than a change of recommendation: **Tier A still ships first**, because it
is what unblocks the hard path, but Tier B is now a plausible stretch goal instead of a follow-up release.
