# Functional Design — the front door unit

**Generated**: 2026-08-04
**Stage**: CONSTRUCTION — Functional Design (per-unit)
**Unit**: front door
**Depth**: **minimal**, and retrospective

## Why minimal depth, and why this stage runs at all

`core-workflow.md` says to skip Functional Design when there is "no new business logic", and to vary
depth by complexity. Most of this unit's design already exists: `inception/application-design/`
carries twelve components with responsibilities and interfaces, and `requirements.md` carries the
rules. Re-deriving that would produce a longer document and no new information.

What *is* new since those were written, and what this stage therefore records:

1. **The business rules as actually implemented**, which differ from the design in three places.
2. **The grounding contract** — how retrieved passages become a prompt. That did not exist at
   Application Design, because retrieval was a stretch goal then.
3. **The decision table for what the bot does with each activity**, which was spread across FR-12,
   FR-18 and the `28:` filter and is easier to check in one place.

> **Retrospective.** The code was written before this stage ran. Where implementation and design
> disagree, this document records the implementation as the fact and names the divergence — it does not
> quietly rewrite the design to match.

---

## 1. Activity decision table

Everything the front door does, given an inbound activity. Read top to bottom; first match wins.

| # | Condition | Action | Requirement |
| --- | --- | --- | --- |
| 1 | Request path/JWT invalid, or `serviceurl` mismatched, or claim absent | Log the reason, **return 200**, do nothing | FR-8, FR-10 |
| 2 | `BOT_APP_ID` unconfigured | Reject **everything** | fail-closed, SECURITY-15 |
| 3 | Body > 256 KB, or not a JSON object | Log, return 200 | SECURITY-05 |
| 4 | `type == conversationUpdate` **and** a member not prefixed `28:` joined | Send the greeting | FR-12 |
| 5 | `type == conversationUpdate` **and** only `28:` members joined | Nothing — this is the bot itself | FR-12 |
| 6 | `type == message` **and** `text` is non-empty | Typing indicator, then retrieve, ask, reply | FR-18, FR-25 |
| 7 | `type == message` **and** `text` empty or absent | Nothing. An attachment, reaction or card action | FR-12 |
| 8 | Any other type | Nothing, accepted silently | FR-12 |
| 9 | Anything above raises | Log with correlation id, **return 200** | FR-10 |

**Row 2 is the one worth arguing about.** An unconfigured audience could plausibly mean "validation
disabled". It is read as "reject everything" instead, because the alternative turns a misconfigured
deployment into an open relay on a public URL. A bot that answers nothing is a visible failure; a bot
that answers anyone is not.

**Rows 1 and 9 both return 200 deliberately.** A non-2xx makes Azure Bot Service retry a request that
can never succeed, forever.

---

## 2. The grounding contract

New at this stage. `_ask()` assembles one prompt from three parts:

```
system = <base prompt, from S3 or the built-in default>
         + "\n\n"
         + <grounding block, chosen by whether retrieval returned anything>
user   = <the student's question, truncated to 4000 chars>
```

**Two grounding blocks, and the difference between them is the guardrail:**

| Retrieval | Grounding block instructs the model to | Behaviour |
| --- | --- | --- |
| ≥1 passage | Answer **only** from the passages; if they do not cover the question, say so and refer to course staff | Grounded answer, or an honest refusal |
| 0 passages | Say it does not have the information and refer to course staff. **Never guess** | Refusal |

**Passages are wrapped in numbered `<passage N>` tags**, not concatenated raw. Delimiting them means
the model can attribute a statement to a passage, and a passage containing something prompt-like is
visibly data rather than instruction.

**The refusal path is a feature, not a fallback.** PR #21 answered Q4 as refuse-when-ungrounded on demo
grounds: the audience is provost-level, and a design that produces confident ungrounded answers about
real Cornell courses, contained only by a disclaimer nobody reads, is worse than one that declines.
A refusal demonstrates the guardrail working.

**Retrieval failure degrades to the 0-passage path, and never to an error.** A slow or unreachable
knowledge base costs the student a *grounded* answer, not their answer — the model is told it has no
material and refuses on that basis. Verified for three cases: no id configured, retrieve raising, and a
20,000-character query truncated to the 10,000-character service cap.

---

## 3. Where the implementation diverges from Application Design

| Design said | Implementation does | Assessment |
| --- | --- | --- |
| `ActivityNormalizer` produces an `Envelope` with 8 fields including `reply_to_id` | `parse_activity` produces an `Activity` with 8 fields, no `reply_to_id` | **Fine.** `reply_to_id` was for channel thread replies, which are out of v1 scope. Adding it is one field |
| `DeliveryDispatcher` selects a strategy from `conversation_type` | No dispatcher. One reply path | **A real loss** — FR-16's seam does not exist, so adding group/channel scopes changes the reply path rather than adding a strategy |
| `IdempotencyStore` with three-state conditional writes | Not implemented | **A real loss.** Azure retries can produce a duplicate reply. The activity id is still threaded as the correlation id, so restoring it is additive |
| Agent reads its own history from AgentCore Memory | No conversation state at all | **Deferred with the agent.** Every message is single-turn, and Teams supplies no history to compensate |
| `ConfigProvider.get()` cached | `_Config` built once inside a lazy `_Runtime` | **Better than designed.** Module-scope construction would fail during Lambda INIT, bypassing the always-200 rule entirely |
| Two Lambdas sharing one image, different handlers | One Lambda | Follows from the synchronous decision |

**Four of the six divergences are the same decision** — synchronous single-Lambda delivery — and two of
them (`DeliveryDispatcher`, `IdempotencyStore`) are genuine reductions in capability rather than
simplifications. They are recorded as such in `unit-of-work-story-map.md`, where FR-9 is marked
**VIOLATED** rather than partial.

---

## 4. Data handled, and what is not retained

| Data | Where it goes | Retained? |
| --- | --- | --- |
| Student's question | Gateway request; retrieval query | **Not stored.** No transcript bucket in this template |
| Model's answer | Bot Framework reply | Not stored |
| Activity id, type, conversation type, validation outcome | CloudWatch, 90 days | Yes — the SECURITY-02 compensating control |
| Message bodies, tokens, secrets | **Nowhere.** Never logged | No |
| Conversation history | Nowhere | **No.** Single-turn |

**Medium-risk data is permitted to and from the gateway**, which is what makes student questions
acceptable here. The same traffic sent directly to a model provider would not be.

**Worth stating because it is easy to assume otherwise**: the scaffold's `TRANSCRIPT_BUCKET` and its
best-effort transcript writes were **not** carried into the rewrite. Nothing in this unit persists a
conversation. If transcripts are wanted for the demo they are new work, not a switch to flip.
