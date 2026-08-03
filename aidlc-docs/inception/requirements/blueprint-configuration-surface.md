# Q3 Reframed — The Bot's Behaviour Is a Deployment Parameter, Not a Blueprint Property

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis
**Trigger**: the user's observation that *"We don't know what the bot does. The user will ask it to be
built."*

**That observation is correct, and Q3 was the wrong shape.** This document records the correction and
proposes the question that should have been asked.

---

## 1. Why the original Q3 was wrong

Q3 asked *"what must the bot actually do in its first deployed version?"* with options ranging from echo
to agentic. That framing assumes the blueprint **is** a bot.

It is not. The participant brief is explicit about the architecture:

> A builder describes what they want inside their AI assistant ("automate my team's access to backend
> tools and reporting"); the platform figures out the right blueprint and deploys a working, governed
> starting point for them — self-service, on AWS, within Cornell's guardrails. **Every other blueprint
> below is a building block this keystone deploys.**

So the blueprint is a **template that gets instantiated**, and what any particular bot does is decided by
whoever requests it — *after* the blueprint is written. Asking the blueprint author to decide the bot's
purpose inverts the design.

**The right question is: what is the blueprint's configuration surface?** What knobs does it expose, that
someone else fills in per deployment?

---

## 2. Where the configuration actually lives — answering the MCP question

The user asked whether the MCP server is where this information is stored. **The MCP decides it; it does
not store it.** The distinction matters because it determines what has to be built.

`CLAUDE.md` describes `builder-mcp/` precisely:

> the MCP server that **searches blueprints and creates deployment repos**

Two verbs, both build-time. So the flow is:

```
  builder: "create a teams bot that answers questions about X"
        |
        v
  +-------------------------------------------+
  |  builder-mcp                              |
  |   1. search blueprints -> picks teams-bot |
  |   2. create a deployment repo, with the   |
  |      parameter values written into it     |
  +---------------------+---------------------+
                        |
                        v
  +-------------------------------------------+
  |  that repo's pipeline deploys the stack   |
  |  with those parameters                    |
  +---------------------+---------------------+
                        |
                        v
  +-------------------------------------------+
  |  running bot -- reads its own config      |
  |  from env vars / SSM at request time      |
  +-------------------------------------------+
```

**Text alternative.** A builder describes what they want. The `builder-mcp` server searches the blueprint
catalogue, selects the `teams-bot` blueprint, and creates a deployment repository with the chosen parameter
values written into it. That repository's pipeline deploys the CloudFormation stack using those parameters.
The running bot then reads its own configuration from environment variables or SSM at request time. The MCP
is not in the request path at all.

**The key consequence: because the MCP creates a *deployment repo*, the configuration is expressed as
infrastructure-as-code and checked into git.** That is exactly consistent with "everything is IaC, no
click-ops" — the bot's personality is a reviewable file, not a database row. Nothing is stored in the MCP
itself, and the MCP is never called while a user is talking to the bot.

**So the blueprint's configuration surface is its CloudFormation parameters.** That is the thing to design.

### How the running bot reads them

Two options, and they can be combined:

| Mechanism | Good for | Note |
| --- | --- | --- |
| **Environment variables** on the Lambda and AgentCore runtime, set from stack parameters | Model id, feature flags, scope settings | Simplest. Changing one requires a stack update. |
| **SSM Parameter Store** entries created by the stack | Anything worth changing without a redeploy | Matches the existing `hello-world` pattern (`/aidlc/main/hello-world/deployed-commit`). Watch the `AWS::SSM::Parameter` tags-as-a-map gotcha. |

**One real constraint worth knowing now**: CloudFormation parameter values are capped at **4096
characters**, and SSM standard-tier parameters at 4 KB. A substantial system prompt can exceed both. If
prompts are expected to be long, they belong in S3 with the stack parameter holding the object key — a
small decision that is annoying to retrofit.

---

## 3. The consequence the reframe does not remove

**The template must be able to deploy the most capable variant it advertises.** If a builder can ask for
retrieval, the retrieval plumbing has to exist in the template even when a given deployment does not use
it. So the reframe does not make the capability question disappear — it converts it from *"what does the
bot do"* into *"which capability tiers does v1 support"*, which is a scoping decision and a much easier one.

Suggested tiers:

| Tier | Configuration surface | Work | Covers |
| --- | --- | --- | --- |
| **A — prompt-configured** | system prompt, model id, greeting, Teams scopes | Smallest. No new data stores. | "a bot that helps with X", where X is general knowledge plus instructions |
| **B — A + retrieval** | plus a corpus pointer (S3 prefix) | Adds the whole R2 pipeline: chunking, embedding, a vector store, search | "a bot that answers questions about *our documents*" |
| **C — B + tools** | plus tool/MCP endpoints the agent may call | Largest. Agentic loop, tool auth, error handling | "a bot that *does* things" — the brief's own example |

**Recommendation for a two-day workshop: build Tier A properly, and design the parameter surface so B
and C slot in without redesign.** Tier A is a genuinely useful, genuinely reusable blueprint — most
internal chatbot requests are a prompt and a model — and it exercises the entire hard path end to end:
Teams ingress, JWT validation, streaming, AgentCore, the gateway, secrets, tags, the ARM64 container build.
Every one of those is a first for this repository, and none of them gets easier by also doing retrieval on
day one.

The user's own instinct — *"for the demo we'll give it just one or two options"* — points the same way. Two
Tier A deployments with different prompts and models demonstrate the keystone idea completely: same
blueprint, different bots, deployed from a description.

**If retrieval is wanted in the demo**, note that it is Tier B and read §4 for what that actually costs.

---

## 4. What "R2" means, plainly

Apologies for the shorthand. R1, R2 and R3 were three ways to do retrieval — letting the bot answer from
your documents rather than only from what the model already knows.

Any document-answering bot needs the same trick. You cannot paste all your documents into every prompt, so
you have to find the few relevant paragraphs first. The standard way is **embeddings**: convert text into a
list of numbers such that passages about similar things end up close together. Then "find relevant
paragraphs" becomes "find the nearest numbers", which is fast.

That needs two phases:

**Ingestion, done once (and on updates):**

```
documents -> split into chunks -> embed each chunk -> store the vectors
```

**Query time, on every question:**

```
question -> embed it -> find nearest stored vectors -> retrieve those chunks
         -> put them in the prompt -> ask the model
```

The three options differ only in **who does that work**:

### R1 — Bedrock Knowledge Base

AWS does all of it. Point `AWS::Bedrock::KnowledgeBase` at an S3 bucket and it chunks, embeds, stores and
searches for you. **Roughly one CloudFormation resource.** By far the least work.

**Why it is ruled out here**: it calls a **Bedrock** embedding model internally, with no configuration
surface to redirect that call. Every ingestion *and every user query* would be embedded by a direct Bedrock
call, bypassing the gateway. The Q26 mandate says all model traffic routes through the gateway. So R1 needs
someone to grant an exception — which is why it is not the recommendation, despite being the easiest.

### R2 — self-managed vectors, embeddings through the gateway

You do the work that R1 would have done, so that every embedding call goes through the gateway:

1. **Chunk** the documents — split into passages, with a little overlap.
2. **Embed** each chunk by calling the gateway's embeddings endpoint. Cheapest models are
   `amazon.titan-text-embeddings.v2` or `openai.text-embedding-3-small`, both **$0.02 per million
   tokens** — effectively free at course-catalogue scale.
3. **Store** the vectors.
4. **At query time**, embed the question the same way and search for nearest neighbours.

**Storage options, all confirmed CloudFormation-deployable in your account:**

| Option | CFN types | Trade-off |
| --- | --- | --- |
| **S3 Vectors** | `AWS::S3Vectors::VectorBucket`, `::Index` | **Recommended.** Purpose-built, cheapest, no cluster, no VPC. Both types `FULLY_MUTABLE` in us-east-1. |
| OpenSearch Serverless | `AWS::OpenSearchServerless::Collection` + security policies | More capable, hybrid keyword+vector search, materially more expensive, more moving parts. |
| Aurora + `pgvector` | `AWS::RDS::DBCluster` | Familiar SQL, but **requires a VPC** — which reopens the networking question you currently have an assumption against. |

**Honest cost**: this is real code — chunking, embedding calls, vector writes, a search path — plus a
storage resource. Call it a few hundred lines and a meaningful chunk of a day, against roughly one resource
for R1. That gap is the entire argument for deferring retrieval past the demo.

**Its advantage**: compliant by construction, no exception needed from anyone. On a two-day timeline, "no
approval required" is often faster than "less code".

### R3 — no vectors at all

Keyword or full-text search, or the gateway's `google-enterprise-web-search` if the corpus is public web
content. No embeddings, so no routing question. Much weaker at matching meaning rather than words — a
question phrased differently from the document will miss.

### Summary

| | Work | Gateway-compliant | Quality |
| --- | --- | --- | --- |
| R1 Bedrock KB | Lowest | **No** — needs an exception | Good |
| **R2 self-managed** | Highest | **Yes** | Good |
| R3 keyword | Low | Yes (no embeddings) | Weakest |

**None of this is needed for Tier A**, which is the recommendation for v1.

---

## 4a. The Knowledge Base team owns the vector store — Tier B changes shape

**Confirmed 2026-08-03**: "KBB" is the **Knowledge Base** team, and that track is defined in the
participant brief as one of the supporting blueprints:

> **Document ETL & batch processing** — Turning a pile of documents into something usable — extract,
> transform, and load into **a searchable knowledge store**, including large batch LLM jobs.

So the vector store is **their** blueprint, not this one. That is the right split — it is exactly the
"reusable building block" model the brief describes, and duplicating it here would be building a parallel
one-off, which the brief explicitly names as the thing the blueprint layer exists to prevent.

### What this does to Tier B

**Tier B stops being an implementation and becomes an integration.**

| | Before | After |
| --- | --- | --- |
| Chunking | ours | **theirs** |
| Embedding at ingest | ours | **theirs** |
| Vector storage | ours | **theirs** |
| Search | ours | **theirs, or ours — see §4b** |
| Our work | a few hundred lines plus a storage resource | **a stack parameter**, plus query-side code only if they expose storage rather than search |

Everything in §4 about R1/R2/R3 remains accurate as *background* — it is now largely a description of
decisions the Knowledge Base team faces rather than decisions this blueprint faces.

**This strengthens the Tier A recommendation for v1, for a new reason.** It is no longer mainly about
effort. Tier B is now **blocked on an interface that does not exist yet** — you cannot build against a
contract the other team has not defined. Tier A is unblocked today; Tier B is unblocked when they publish
something to point at.

### The interface convention is already set, and it constrains the answer

The repository has an established pattern, recorded in the Reverse Engineering artifacts:

> **Blueprints as leaves** — no blueprint imports from another or reads an export, so each is
> independently deployable and independently reasoned about.

> **Loose coupling by name, not export** — the pipeline references `cloudformation-deploy-role` by
> constructed name rather than importing a CloudFormation export.

**So the Teams bot must take the knowledge store identifier as a CloudFormation parameter — not as an
`!ImportValue` of the Knowledge Base stack's export.** A cross-stack import would make the two blueprints
jointly deployable and jointly breakable, losing the leaves property.

This also fits the keystone model exactly: **the MCP knows about both blueprints**, so the MCP is the
natural place to supply one blueprint's identifier to the other when it writes the deployment repo. No
runtime coupling, no deployment-order dependency, one reviewable parameter in git.

---

## 4a-bis. SUPERSEDED 2026-08-04 — see `knowledge-base-integration.md`

> **This section is largely obsolete.** The KB team is using **Bedrock AgentCore Managed Knowledge Base**.
> The S3 bucket is that knowledge base's **data source**, not its vector store — Bedrock owns chunking,
> embedding, storage **and retrieval**.
>
> **Three concerns raised below are retired**: search is owned; the embedding-model-match silent-failure
> risk is eliminated because Bedrock embeds both sides; and the three-way "what is in the bucket"
> ambiguity resolves to the best of the three cases.
>
> **Correction**: the parameter is a **`KnowledgeBaseId`**, not a bucket name or an S3 path, and this
> blueprint should have **no S3 access to their bucket at all** — reading it directly would duplicate
> their ingestion. The `KnowledgeStoreType` enum below is no longer needed.
>
> Retained below only as the record of what was known before the documentation arrived.

### Original section, superseded — Knowledge Base storage is "a simple S3 bucket", not yet created

**Status recorded 2026-08-04.** The Knowledge Base team has not finalised its design. What is known:

- Storage will be **a simple S3 bucket**, in **our own AWS account**
- **That bucket will serve the RAG**
- **It does not exist yet**, but will
- The KB team's remaining decisions are outstanding

**Explicitly agreed approach**: proceed with what is known and adjust later. This section is the note that
it is unresolved.

### What the S3 fact does settle — four things, all useful

1. **Same-account access.** No cross-account bucket policy, no resource-based policy negotiation, no
   assume-role hop. Just an IAM policy on our execution role. This removes a whole category of work.
2. **The IAM requirement is now concrete**: the AgentCore execution role needs `s3:GetObject` and
   probably `s3:ListBucket`, scoped to that bucket and prefix. Can be written now with the bucket name as
   a parameter.
3. **A bucket name or ARN is a perfectly good stack parameter** — consistent with the
   parameter-not-`!ImportValue` convention in §4a, and it needs no coordination beyond being told the name.
4. **No VPC implication.** S3 is reachable without private networking, so this does not disturb the
   recorded no-VPC assumption.

### What it does not settle — and this is the consequential part

**A plain S3 bucket is storage, not retrieval.** S3 by itself has no similarity search. So "the bucket
serves the RAG" can mean three quite different things, and they imply very different amounts of work for
this blueprint:

| What is actually in the bucket | Who embeds | Who searches | Our work |
| --- | --- | --- | --- |
| **Documents / text chunks** | **nobody yet** | **nobody yet** | Largest. Chunking, ingest-time embedding, a vector index, and query-side search all become ours or unowned. The embedding-model choice also becomes ours. |
| **Precomputed embeddings** (JSON/Parquet vectors) | KB team | us | Moderate. Load vectors, embed the query with **their exact model**, compute nearest neighbours ourselves. Workable for a small corpus; does not scale well. |
| **An S3 Vectors vector bucket** (`AWS::S3Vectors::VectorBucket` + `::Index`) | KB team | **S3 Vectors** | Smallest. Embed the query, call the index, get results. Native similarity search. |

**Worth flagging that the third option is a distinct AWS service, not a regular bucket.** S3 Vectors is
purpose-built for this and does the search natively — and it is confirmed `FULLY_MUTABLE` in our account.
If the KB team has not evaluated it, it is worth raising with them, because it is the difference between
"the bucket serves the RAG" being literally true and needing a search layer somebody has to own.

**The specific risk to name**: if the bucket holds plain documents and the KB team considers their job done
at that point, then **chunking, embedding and search are unowned** — each consuming blueprint would build
its own, differently, which is the duplication the blueprint layer exists to prevent. That is a boundary
question for Marty rather than a technical one.

### How to proceed without the answer — design the parameter surface to be agnostic

This is the actionable output, and it means the uncertainty costs nothing today.

Rather than a parameter that assumes a shape, Tier B takes a **pointer plus a declared kind**:

| Parameter | Values | Purpose |
| --- | --- | --- |
| `KnowledgeStoreType` | `none` \| `s3-documents` \| `s3-vectors` \| `retrieval-endpoint` | Tells the runtime how to use what it is given |
| `KnowledgeStoreLocation` | bucket/prefix, vector index ARN, or endpoint URL | Where it is |

**v1 ships with `KnowledgeStoreType: none`**, which is Tier A. Whichever answer the KB team lands on becomes
a new branch behind that parameter, not a redesign — and the blueprint never needs to know today.

**Also unblocked by this**: the embedding-model-match constraint from §4b can be handled the same way, as a
`EmbeddingModelId` parameter that must be set to whatever the KB team used. Recording it as a parameter
makes the coupling visible in the deployment repo instead of implicit in code.

### Bottom line

**Not a blocker for v1.** Tier A is unaffected, the critical path is unaffected, and the S3 details we have
are enough to write the IAM policy and the parameter shape. Formally recorded as an open dependency owned by
the Knowledge Base team, to be revisited when they decide. The one thing worth chasing before the two days
are out is whether **search** is owned by anyone.

---

## 4b. What to ask the Knowledge Base team

Five questions. The second and third are the ones that actually determine our work.

**1. What does your blueprint output, concretely?** An S3 Vectors index name, an OpenSearch Serverless
collection endpoint, a retrieval Lambda ARN, something else? Whatever it is becomes our stack parameter.

**2. Do you expose *search*, or only *storage*?** This is the big one.

- If they expose a **retrieval endpoint** — "here is a question, here are the relevant chunks" — the
  Teams bot needs **no vector code at all**. It calls their endpoint and puts the results in the prompt.
  Tier B becomes nearly free.
- If they expose only **storage**, the Teams bot must embed the user's question itself and run the
  nearest-neighbour search. That is meaningfully more work and it re-introduces the embedding-model
  coupling in question 3.

**3. Which embedding model, and does it go through the gateway?** Two distinct concerns, both important:

- **Routing**: if they embed via Bedrock directly, they inherit the R1 gateway-bypass problem and so do
  we by association. If they embed through the gateway, both blueprints are compliant.
- **The harder constraint — the embedding model must be the *same* at ingest and at query time.**
  Vectors produced by different models are not comparable; searching a Titan-embedded corpus with an
  OpenAI-embedded question returns nonsense, and it fails *silently* by returning plausible-looking but
  irrelevant results. So if we do the query side, **their model choice becomes our model choice**, and it
  has to be recorded as part of the interface rather than left to each side.

This is the kind of coupling that is invisible until results are quietly bad, so it belongs in the
contract explicitly.

**4. What is the identifier's shape and lifecycle?** Is one knowledge store shared by many bots, or one
per deployment? Does it change when they redeploy? If it changes, our parameter needs updating too.

**5. Will there be something to point at within the two days?** Determines whether Tier B is a real
option for the workshop or a follow-up.

### Second team-boundary question in a row

This is the second time blueprint ownership has come up — Team E on AgentCore, now Knowledge Base on the
vector store. The brief's model is teams self-organising across a blueprint list, which makes boundaries
emergent rather than assigned, so **Marty is the arbiter** for anything ambiguous. Worth a short
conversation covering both boundaries at once rather than discovering an overlap in a pull request.

---

## 5. Proposed replacement for Q3

Q3 is rewritten in `requirement-verification-questions.md` as a tier-scoping question. The substantive
answer needed is:

1. **Which tier does v1 support** — A, B, or C?
2. **What are the one or two demo configurations?** Concretely: prompt, model, and scopes for each. Two
   visibly different bots from one blueprint is the demonstration.

Everything else in this document is recorded so the design stage does not have to rediscover it.
