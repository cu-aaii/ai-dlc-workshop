# Response Delivery — The Real Timeout Budget, and Why Streaming Beats Both Options

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (research input)
**Question answered**: *"If we don't reply with a fast model, can we do the response all at once or
will that time out?"*

**Short answer**: it will time out, and you cannot extend the window. But there is a third option I
had not put in front of you, it is generally available, and it removes the constraint entirely rather
than working around it. It also dissolves the AgentCore cold-start tension.

---

## 1. The budget, verified

From Microsoft's own guidance on long-running operations:

> If the bot doesn't complete the operation within **10 to 15 seconds, depending on the channel**,
> the Azure AI Bot Service will time out and report back to the client a **`504:GatewayTimeout`**.

And from the Bot Framework basics documentation:

> The bot has **15 seconds** to acknowledge the call with a status 200 on most channels.

So the numbers are:

| | Value |
| --- | --- |
| Budget | **10-15 seconds**, channel-dependent |
| What the user sees on overrun | `504:GatewayTimeout` |
| Extendable? | **No.** It is enforced by the Bot Service connector, not by us. |
| Consequence beyond the error | Retries, which a synchronous handler turns into duplicate replies |

That budget covers **everything**: Lambda cold start, JWT validation, the `InvokeAgentRuntime` call,
AgentCore's own container start, the hop to `api.ai.it.cornell.edu`, generation, and the reply.

**So the answer to "can we do it all at once with a slower model" is no.** Microsoft's documented
answer to exactly this problem is the acknowledge-then-notify pattern — which is what the n8n
prototype already did.

---

## 2. The third option: Teams response streaming

This is generally available on web, desktop and mobile, and it is what modern AI assistants in Teams
actually do.

**The mechanism.** Return `200 OK` to the inbound request immediately — so the 15-second budget is
never even approached — then send a *sequence* of outbound activities that Teams renders
progressively into a single message:

1. **Informative updates** — a blue progress bar with text like "Searching through documents…".
   Buys unlimited time while showing the user something is happening. Max 1 KB / 1000 characters.
2. **Response streaming** — rendered as a typing indicator, revealing the answer as it is generated.
3. **A final message** that closes the stream.

Users also get a **Stop** button by default, letting them abandon a response and re-prompt.

**Why this is better than either option I gave you:**

| | Synchronous + lite model | Ack + single proactive reply | **Streaming** |
| --- | --- | --- | --- |
| Timeout risk | Real, worst on cold start | None | **None** |
| Model choice | Constrained to fast models | Free | **Free** |
| Perceived speed | Fast when it works | Feels laggy — silence, then an answer | **Fast — activity within ~1s** |
| Duplicate replies on retry | Yes, needs idempotency | No | **No** |
| AgentCore cold start | The core problem | Absorbed | **Absorbed** |
| Extra work | Least | Some | Most |

**It gets you what you wanted from the synchronous decision — a fast-feeling bot — without the
constraint that motivated choosing a lite model.** You can use whatever model actually answers best.

---

## 3. The constraints, because they are specific and some are sharp

Straight from the API documentation. These are the things that will bite an implementation.

### Scope limitation — the important one

> Streaming agent messages are supported **only in one-on-one chats**.

**This ties directly to Q4.** If the first version is personal chat only, streaming is available. If
group chat or channel support is required, streaming is **not** available there and those scopes need
the plain acknowledge-then-reply pattern, ideally with a typing indicator. A design that assumes
streaming everywhere will fail the moment the bot is added to a channel.

Also: **only one concurrent streaming response per chat**.

### Content must be cumulative, not deltas

Each streaming update carries the **entire message so far**, not the new fragment:

```
"A brown"  ->  "A brown fox"  ->  "A brown fox jumps over the fence"
```

Sending `"A brown"` then `"Hello"` is an error. So the handler accumulates model output and resends
the growing string. Simple, but the opposite of how most streaming APIs work — and an easy thing to
get wrong when wiring a model's token stream straight through.

### Rate limit and pacing

> The throttling limit is **1 request per second**.

And the explicit recommendation:

> Buffer the tokens from the model for **1.5 to two seconds** to ensure a smooth streaming process.

Calls must also be **sequential** — wait for a successful response before sending the next. A model
emitting tokens faster than one update per second must be buffered, not forwarded.

### The REST contract, and its one trap

Outbound POSTs go to `/conversations/<conversationId>/activities`:

| Field | Notes |
| --- | --- |
| `type` | `typing` for every intermediate update; `message` for the final one |
| `text` | the cumulative content |
| `entities.type` | must be `streamInfo` |
| `entities.streamId` | from the first response; required on every subsequent call |
| `entities.streamType` | `informative`, `streaming`, or `final` |
| `entities.streamSequence` | starts at **1**, monotonically increasing |

The first call returns **`201 Created`** with `{"id": "a-0000l"}` — that id is the `streamId`.
Subsequent calls return `202`.

**The trap**: `streamSequence` must be present on the start and continue calls and **must not be set
on the final message**. Setting it there is an error, and it is exactly the kind of off-by-one detail
that produces a broken stream with a confusing message.

### Final-message-only features

Attachments, the AI-generated-content label, feedback buttons and sensitivity labels are available
**only on the final streaming message**. Anything richer than plain text has to wait for the end.

---

## 4. Recommendation

**Revisit Q8.** It was answered "A — synchronous with a superfast lite model", chosen to make the bot
feel fast. Streaming achieves that goal better, and without the constraint:

- **If Q4 is personal chat only** — stream. Informative update immediately, then progressive text.
  Use whatever model gives the best answers. No timeout exposure at all.
- **If Q4 includes group chat or channel** — stream in personal chat, and use acknowledge-plus-typing
  indicator plus a single reply in the scopes where streaming is unavailable. Two delivery paths, one
  agent behind them.
- **If the priority is shipping something today** — the synchronous lite-model path is genuinely the
  least code, and with a hard timeout of roughly four seconds plus a proactive fallback it is safe
  enough for a demo. Treat it as a deliberate first step with streaming as the known next one, rather
  than as the destination.

**Required regardless of which path**: idempotency keyed on the inbound activity `id`. Any design
that can be retried must not answer twice.

### What this does to the AgentCore tension

It removes it. The concern was two container cold starts in series — Lambda, then AgentCore Runtime —
inside a 15-second window. Under streaming, the inbound request is acknowledged in milliseconds and
the cold starts happen while the user watches a progress indicator. **The clock the cold starts were
racing no longer exists.**

That also means the AgentCore mandate and a good model are no longer in tension with responsiveness,
which is worth saying plainly: the architecture Team E asked for is fully compatible with a bot that
feels fast.

---

## 5. Effect on open questions

| Question | Effect |
| --- | --- |
| **Q8** — sync vs proactive | **Recommend revisiting.** Streaming is a better answer than the recorded option A. |
| **Q4** — conversation scopes | **Newly load-bearing.** Streaming is personal-chat-only, so Q4 now determines whether one delivery path suffices or two are needed. |
| Q3 — capability | **Less constrained.** Model choice is no longer bounded by latency, so a better model or a retrieval step is affordable. |
| AgentCore cold starts | **Resolved**, provided the response is not synchronous. |
| Q9 — conversation state | Unchanged. |

---

## Sources

Microsoft Learn, retrieved 2026-08-03: *Manage a long-running operation* (Azure AI Bot Service), the
*Basics of the Microsoft Bot Framework* 15-second acknowledgement statement, and *Stream agent
messages* (Microsoft Teams platform) for the streaming mechanism, limits and REST contract.
