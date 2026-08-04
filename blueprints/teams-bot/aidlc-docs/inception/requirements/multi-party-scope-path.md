# Adding Group Chat and Channel Later — What It Actually Costs

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (forward-looking; not in scope for v1)
**Decision it follows**: Q8 → **streaming**.
**Question answered**: *"how hard would it be if we wanted multiple people?"*

> ## SCOPE REVISED 2026-08-03 — multi-chat is now IN SCOPE
>
> Q4 was answered "personal chat only for now" and then revised to **"we'll add multichat"**. This
> document therefore changes status from *forward-looking roadmap* to **in-scope requirements**.
>
> **"Multichat" has three materially different meanings** and they diverge sharply in cost and risk,
> so the exact target is recorded as an open question in `requirement-verification-questions.md` Q4
> rather than guessed at. The three are §2 (Tier 1), §3 (Tier 2), and the group-chat gap in §3a.
>
> **Two things change regardless of which tier is meant**, and both are significant:
>
> 1. **Both delivery paths must be built in v1**, not just the seam in §1. Streaming is one-on-one
>    only, so multi-party scopes need the acknowledge-plus-typing-plus-single-reply path built and
>    working, not merely anticipated.
> 2. **The medium-risk-data-in-a-shared-scope question in §5 is no longer deferred. It is live, and it
>    blocks.** Personal-only was what allowed it to be postponed honestly. That option has been given
>    up. See §5 — this is now the most important open item in this document, and it is a policy
>    decision rather than an engineering one.
>
> A third consequence, discovered on re-reading the research: **thread-reply filtering requires
> persistence**, which affects Q9. See §3b.

**Short answer**: the Teams-side work is genuinely small. The cost is almost entirely determined by
**one decision made now** — whether the delivery mechanism is abstracted from the agent. Get that
seam right today and later expansion is additive. Bake streaming into the handler and it is a rewrite
of the response path.

There are also two **non-technical** issues that are easy to miss and harder than any of the code.
See §5.

---

## 1. The one thing to do now, because it is nearly free today

Streaming works **only in one-on-one chats**. Every other scope needs the acknowledge-plus-typing-
indicator-plus-single-reply pattern. So the bot will eventually have **two delivery paths behind one
agent**.

**Build the seam now. Implement only the streaming side.**

Concretely: have the handler select a delivery strategy from `conversation.conversationType` rather
than calling streaming APIs inline.

```
                +---------------------------+
                |  agent produces an answer |
                +-------------+-------------+
                              |
                +-------------v-------------+
                |  deliver(activity, text)  |   <-- the seam
                +------+-------------+------+
                       |             |
          personal ----+             +---- groupChat / channel
                       |                          |
          +------------v-----------+   +----------v-------------+
          |  streaming delivery    |   |  ack + typing + single |
          |  (implement now)       |   |  reply (add later)     |
          +------------------------+   +------------------------+
```

**Text alternative.** The agent produces an answer and hands it to a single `deliver` function — the
seam. That function dispatches on the conversation type: personal chats use streaming delivery, which
is implemented now; group chats and channels use acknowledge-plus-typing-indicator-plus-single-reply,
which is added later. The agent itself never knows which path was taken.

That is roughly twenty to thirty lines of structure today. It converts "rewrite the response path"
into "write one more strategy class." Given the delivery paths differ in *shape* — many cumulative
updates versus one final message — retrofitting the seam later means touching everything that emits
output.

**This is the whole answer to "how hard".** With the seam: a few hours. Without it: a day of
untangling plus the risk of breaking the working path.

---

## 2. Tier 1 — group chat and channel, `@mention` required

The cheap version. In channels the bot only receives messages that `@mention` it, which is the
**default** and needs nothing extra to arrange.

| Work | Notes |
| --- | --- |
| Add `groupChat` and `team` to `bots[].scopes` in the manifest | Straightforward |
| Add top-level `"supportsChannelFeatures": "tier1"` | **Required by the v1.25 schema for `team` scope.** Two documented traps: the Developer Portal GUI **does not expose it**, so it must be added manually in the App package editor; and the portal's validator **wrongly rejects it if placed inside the bot object** — it belongs at top level. |
| Handle both conversation id formats | Personal is `a:xxx…`; channel and group are `19:xxx…@thread.tacv2`. Any code that assumes one shape breaks. |
| Strip `@mention` markup from `text` | The mention arrives as part of the message text; feeding it to the model unmodified is sloppy but harmless, so this is polish rather than blocking. |
| Implement the second delivery strategy | The real work, and small **if** §1 was done. |
| Install into the team | Operational detail worth knowing: the app install dialog shows only **"Add"**, which installs to personal scope. **Channel and team deployment is initiated from inside the team**, not from the install dialog. |

**No Entra changes. No admin consent beyond what you already control**, since you hold the dev tenant.

**Effort**: small to moderate. The delivery strategy dominates, and §1 is what makes it small.

---

## 3. Tier 2 — thread replies without `@mention` (RSC)

Everything in Tier 1, plus Resource-Specific Consent. This is what lets the bot see replies to its own
posts without being mentioned each time — the thing that makes a channel bot feel natural rather than
clunky.

| Work | Notes |
| --- | --- |
| Add `webApplicationInfo` to the manifest | `id` must be the bot's Entra app registration id — the same one in `bots[].botId`. `resource` must be present with any non-empty string; the research records it as **vestigial**, with `"https://AnyString"` being the convention that signals "RSC, not SSO". |
| Add `authorization.permissions.resourceSpecific` with `ChannelMessage.Read.Group` | Team-scoped **application** permission. |
| Bump the manifest version and republish | Via Developer Portal. |
| **Remove and re-add the app in each team** | A reinstall is required, per team. Not a background upgrade. |
| Consent | Granted by the **team owner at install time**. **No Entra admin action needed** — this is the pleasant surprise of RSC. |

### The known risk, flagged by your own research as untested

This is the one thing that could turn Tier 2 from moderate into a problem, and it is already an open
checkbox in `Teams Bot Channel Thread Replies - Research.md`:

> **Investigate `webApplicationInfo.id` conflict** — Earlier in this project, setting "Application
> (client) ID" in the Developer Portal (which maps to `webApplicationInfo.id`) caused **silent Teams
> install failures** because Teams tried to do SSO and the app registration wasn't configured for it.
> RSC requires `webApplicationInfo.id`, but uses `resource: "https://AnyString"` to signal "RSC-only,
> not SSO." **Test whether Teams respects this distinction with this app registration.**

So RSC needs the exact field that previously broke installs silently. The `resource` convention is
*believed* to disambiguate it, and that belief is **unverified**. Fallback paths, if it does break:
add SSO configuration to the app registration, or edit the manifest directly and bypass the portal
field entirely.

**Recommendation**: when Tier 2 is wanted, test this **first**, in a throwaway team, before building
anything around it. It is a fifteen-minute check that de-risks the whole tier.

### The other cost of RSC: it is a firehose

With `ChannelMessage.Read.Group`, the Bot Framework delivers **every message in every channel of that
team** to the endpoint — not just replies to the bot. Consequences: more invocations, more cost, and a
hard requirement to filter early and cheaply before doing anything expensive. A bot in a busy team
will see a lot of traffic that is none of its business.

**Effort**: moderate, with one genuine unknown.

### Two more RSC facts from the research, both operationally important

**The tenant can switch RSC off entirely.** The Teams admin center has an *"Allow resource-specific
consent"* setting. It is **enabled by default**, but if a tenant admin has disabled it, RSC simply does
not work — no manifest change will help. Worth confirming before building on it. Added as an admin
question.

**RSC does not force org publish.** It *"works the same way for both sideloaded apps and org-published
apps"* — consent is granted at installation time either way. So the RSC decision and the
publish-versus-sideload decision are independent, which is more freedom than expected.

**Two limits worth knowing:**

- **Missed replies are gone.** Without RSC enabled at install time, replies that did not `@mention` the
  bot *"were never delivered"* and cannot be recovered through Bot Framework. Retroactive fetch requires
  Graph API calls with `ChannelMessage.Read.All` or `.Group`. So enabling RSC late does not backfill.
- **In-place manifest updates do not re-consent.** Adding RSC to an already-installed app requires the
  team to **remove and re-add** it. This is the gotcha the research calls out explicitly, and it scales
  with the number of teams the bot is already in.

RSC requires manifest schema **1.12 or later**; note this is a different threshold from the **1.25**
required for `supportsChannelFeatures`.

---

## 3a. The gap: group chat without `@mention` is not covered by the research

Worth flagging because it bears directly on what "multichat" means.

The `@mention` requirement applies to **"a group or channel"** — Microsoft's wording covers both. So
group chats are `@mention`-gated exactly as channels are.

But the research documents RSC only for **channels**, via `ChannelMessage.Read.Group`, which is a
**team-scoped** permission. A group chat is not a team, so that permission does not apply to it.
Receiving all messages in a group chat without `@mention` would need a **chat-scoped** RSC permission,
which the existing research does not cover and which has not been verified here.

**Consequence**: if "multichat" means *group chats where the bot responds without being mentioned*, that
is a **fourth option** with no research behind it yet. If it means group chats where users `@mention`
the bot, it is Tier 1 and cheap. The distinction is worth settling explicitly, because one of those
answers has an unknown attached.

---

## 3b. Thread-reply filtering requires persistence — this affects Q9

This is the finding that changes another answer, and it is easy to miss.

To respond only to replies to *its own* posts rather than to all channel traffic, the bot must:

1. **store the activity id** returned by the Bot Framework API when it sends a channel post, then
2. compare each inbound activity's **`replyToId`** against those stored ids, and
3. return `200` silently for anything that does not match.

The activity id is only available in the API response at send time. **So the bot needs durable storage
of its own sent message ids — even if it is otherwise stateless.**

Q9 offered "stateless" as option A. Under RSC-based thread filtering, fully stateless is **not
available**: something must remember what the bot posted. It is a small amount of data with an obvious
key, and it may be satisfiable by AgentCore Memory or a small DynamoDB table rather than anything
elaborate — but Q9 can no longer be answered "stateless" without also deciding not to do thread
filtering.

The canonical alternative filter, per the research, is to inspect `entities` for a mention of the bot's
id and act only on mentions — which needs no storage but also gives up the whole point of RSC.

---

## 4. What does *not* get harder

Worth stating, because it is the reassuring half:

- **The ingress, the guard, and the AgentCore runtime are all scope-agnostic.** The endpoint, the JWT
  validation, the container, the gateway call — none of it changes.
- **No new AWS infrastructure.** Tiers 1 and 2 are manifest and handler work.
- **No pipeline changes.** No new stack, no new stage, no `stacks.yml` entry.
- **Org publish is not a blocker for you.** Sideloading reaches personal scope only, and group/channel
  needs org publish with Teams admin approval — but you hold the dev tenant, so it is self-service.
  This is the step that would be a multi-week wait in the production tenant.

---

## 5. The two hard parts, and neither is code

### Med-risk data becomes visible to everyone in the channel — NOW LIVE

**Status changed 2026-08-03.** While Q4 was "personal chat only", this was a question that could be
deferred honestly. Multi-chat being in scope removes that option. Nothing about it is solved by code.

#### CLOSED 2026-08-03 by decision

**Confirmed by the user, twice:** medium-risk data may travel **to and from** the gateway, and *"if
traffic is routed through LiteLLM then med is fine."*

**Treated as settled.** Since all model traffic routes through the gateway by mandate (Q26), medium-risk
handling is compliant, and **no policy escalation is required for shared scopes.** Admin question 14 is
withdrawn.

Recorded plainly for the record, without reopening it: the concern raised below was about *audience* — who
can see a reply in a shared channel — rather than about the data path. The user has reaffirmed that
gateway-routed traffic settles it. That is their call to make and it is recorded as made. The analysis
below is retained only as context for how the question arose.

**Practical consequence: shared scopes are unblocked.** Q4's B/C/D/E choice is now a purely technical
decision, and Q3/Q20 no longer carry a compliance dependency.

#### Original analysis, retained as context

Confirmed by the user: **the gateway 100% allows medium-risk data.** That is definitive and it fully
answers the **processing** question — it is permitted to send medium-risk data through
`api.ai.it.cornell.edu` for inference. This is why the gateway is mandatory, and it is now on the record
rather than inferred.

**It does not answer the disclosure question**, which is a different thing:

| Question | Answer |
| --- | --- |
| May medium-risk data be **processed** through the gateway? | **Yes — confirmed, 100%.** |
| May medium-risk data be **displayed to every member of a Teams channel**? | **Still open.** |

The gateway's approval governs the channel data travels *through*. Channel visibility governs who can
*see the output*. An approved processing path says nothing about permitted audience — in the same way
that a system approved to handle confidential records does not thereby authorise showing those records to
everyone in a room.

The gateway confirmation actually **sharpens** this rather than resolving it: it establishes that
medium-risk data will legitimately flow through the bot, so the bot really can produce medium-risk output.
The concern moves from hypothetical to live.

#### The reframe that probably dissolves it

The disclosure question is downstream of a simpler one: **can the bot's answers contain medium-risk data
at all?** That depends entirely on what the bot has access to — i.e. on Q3 and Q20.

- **If the bot's knowledge is non-sensitive** — a public course catalogue, published policies, general
  campus information — then its output cannot be medium-risk, and the channel-visibility question
  **evaporates**. No policy conversation needed. For a first version this is the most likely situation.
- **If the bot can reach medium-risk material** — student records, anything FERPA-touching — then audience
  matters, and one of these needs to be chosen: restrict shared-scope replies to non-sensitive content;
  reply privately when a response would include sensitive data; or record an explicit accepted-risk
  decision.

**So the practical next step is not a policy escalation — it is answering Q3 and Q20.** If the corpus is
non-sensitive, say so and this closes. Admin question 14 only needs asking if the answer is that the bot
can reach medium-risk material.

In a one-on-one chat, an answer goes to one person, and that person asked the question. In a channel,
the bot's reply is visible to **every member of that channel** — including people who may not be
entitled to the information in it.

Under a medium-risk classification, a bot that can surface med-risk data in a channel is broadcasting
it. The bot has no way to know who in the channel is entitled to what.

**This is a policy question and it should be settled before channel scope is enabled, not after.**
Possible answers include restricting the bot to non-sensitive content in shared scopes, replying
privately when a response would include sensitive data, or accepting the exposure with an explicit
decision on record. All are legitimate; none should be arrived at by default.

This is the single strongest argument for the Q4 answer being right — personal chat only means this
question can be deferred honestly rather than dodged.

### Conversation state stops being per-person

If Q9 lands on any conversation state, a group conversation has **many** users. Questions that
collapse to the same answer in a one-on-one chat and diverge in a group:

- Is history scoped to the conversation or to the user?
- If two people ask follow-ups simultaneously, whose context applies?
- AgentCore Runtime isolates **per session** in a dedicated microVM. What does a session map to — the
  conversation, or the user within it?

In 1:1 all three collapse. In a group they do not, and the answer changes what gets stored and how it
is keyed. Deciding it later means migrating whatever was stored under the 1:1 assumption.

**Also**: Teams rate-limits bots per thread and globally per app per tenant. More participants means
closer to those limits, and streaming's one-request-per-second cap already consumes budget.

---

## 6. Summary

| | Effort | Blockers |
| --- | --- | --- |
| **The seam** (do now) | ~20-30 lines | None. Nearly free today, expensive later. |
| **Tier 1** — group + channel, `@mention` | Small-moderate | The `supportsChannelFeatures` placement traps. |
| **Tier 2** — thread replies, RSC | Moderate | **Untested `webApplicationInfo.id` install risk.** Test first. Plus firehose volume. |
| **Med-risk in shared scopes** | Not code | **Policy decision required.** The real gate. |
| **Multi-user state** | Depends on Q9 | Migration cost if deferred past a state design. |

**The one action item from this document**: build the delivery seam in v1 even though only the
streaming path is implemented. Everything else can wait, and waiting costs little. That cannot.
