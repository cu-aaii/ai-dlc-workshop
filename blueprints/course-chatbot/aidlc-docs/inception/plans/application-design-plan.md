# Application Design Plan — `teams-bot`

**Created**: 2026-08-04
**Stage**: INCEPTION - Application Design
**Status**: ⛔ **Two questions outstanding — Q6 and Q13.** Everything else is settled.

## Answers received 2026-08-04

| Q | Answer | Source |
| --- | --- | --- |
| **Q1** | **Separate worker Lambda** | explicit |
| **Q2** | **Async invoke** — "because it's a demo" | explicit |
| **Q3** | Channel-agnostic agent | recommendation accepted by default |
| **Q4** | Normalised envelope | recommendation accepted by default |
| **Q5** | **Stream** — agent emits SSE, worker forwards cumulative updates | explicit |
| **Q6** | ⛔ **outstanding** — explanation added below | — |
| **Q7** | Agent reads its own history from AgentCore Memory | recommendation accepted by default |
| **Q8** | Shared internal module | recommendation accepted by default |
| **Q9** | JWT validation local, but self-contained for later extraction | recommendation accepted by default |
| **Q10** | Python 3.12 on ARM64 | recommendation accepted by default |
| **Q11** | One multi-stage Dockerfile with named targets | recommendation accepted by default |
| **Q12** | Generic message plus correlation ID | recommendation accepted by default |
| **Q13** | ⛔ **outstanding** — question rephrased below | — |

**Defaults recorded explicitly rather than left implied**, per the note at the foot of this document.

### Design consequences of Q1 + Q2 + Q5, recorded now

The chosen combination — separate worker, async invoke, streaming — works, and carries four concrete
implications worth capturing before the artifacts are written:

1. **Three components, two of them Lambdas.** Front door (validate, ack, async-invoke) → worker (invoke
   AgentCore, stream to Teams) → agent (AgentCore Runtime container). Per Q11's note, the two Lambdas can
   share one image with different handlers, keeping the Dockerfile to two named targets.
2. **The worker's timeout must be set explicitly.** It runs for the whole generation plus the streaming
   sequence. Lambda's default is 3 seconds, which would truncate every reply. A deliberate value — on the
   order of 5 minutes — is required.
3. **Async invoke retries twice on error.** This is the internal duplicate-reply source explained under Q6,
   and it exists independently of anything Microsoft does.
4. **Async invoke caps the payload at 256 KB.** A Bot Framework Activity is far smaller, so this is not a
   constraint — recorded only so nobody rediscovers it.

Scope of this stage: **component boundaries, interfaces and orchestration.** Detailed business logic is
deliberately out of scope — that belongs to Functional Design in the CONSTRUCTION phase.

---

## Design Plan

- [ ] Generate `components.md` — component definitions and high-level responsibilities
- [ ] Generate `component-methods.md` — method signatures and input/output types
- [ ] Generate `services.md` — service definitions and orchestration patterns
- [ ] Generate `component-dependency.md` — dependency matrix, communication patterns, data flow
- [ ] Generate `application-design.md` — consolidation of the above
- [ ] Validate design completeness and consistency
- [ ] Verify Security Baseline compliance against the design artifacts before the completion message

---

## The one problem that shapes everything else

Worth stating before the questions, because most of them follow from it.

**The front door has already replied by the time the answer exists.** FR-9 requires `200 OK` within
milliseconds. FR-17 requires the answer to be delivered as a *series of separate outbound POSTs* to Teams.
But a Lambda behind a function URL **returns and freezes** — it cannot keep working after it has responded.

So something has to carry the work after the acknowledgement, and *that* choice determines whether the agent
needs to know anything about Microsoft Teams.

```
   Azure Bot Service
          |  POST activity
          v
   +--------------------+
   |  front door        |  validate JWT, return 200 -- then it FREEZES
   +---------+----------+
             |  ??? <-- Q1/Q2 decide this hand-off
             v
   +--------------------+       +---------------------+
   |  something that    | ----> |  AgentCore Runtime  |
   |  survives the ack  | <---- |  (thinks)           |
   +---------+----------+       +---------------------+
             |  outbound streaming POSTs
             v
   Bot Framework REST API  ---->  user sees the reply
```

**Text alternative.** Azure Bot Service POSTs an activity to the front door, which validates the JWT and
returns `200 OK`, after which it freezes. Some component that survives past that acknowledgement must then
invoke the AgentCore Runtime, receive its output, and make the outbound streaming POSTs to the Bot Framework
REST API so the user sees a reply. Questions 1 and 2 decide what that component is and how it is triggered.

---

# Section 1 — Component Boundaries

## Q1. Who performs the outbound delivery to Teams?

This is the most consequential question in the design.

A) **A separate worker Lambda.** Front door validates and acknowledges, then hands off to a worker. The
worker invokes AgentCore, consumes its output, and does the Teams streaming. **The agent stays completely
generic — prompt in, text out — and all Teams knowledge lives in one place.**

B) **The AgentCore container does its own delivery.** Front door acknowledges and invokes AgentCore
asynchronously; the agent calls the Bot Framework API itself as it generates. Fewer moving parts and the
most natural fit for token-by-token streaming — but the agent becomes **Teams-aware**, needs the Entra
credentials, and is no longer reusable by a non-Teams blueprint.

C) **Front door does everything in one Lambda**, acknowledging via a separate mechanism. Not really
available — see the freeze problem above. Listed for completeness.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A.** It keeps AgentCore a generic agent that a future Slack or web blueprint could reuse,
and confines the Bot Framework contract — JWT rules, streaming sequence numbers, `serviceUrl` handling — to a
single component that can be tested on its own. The cost is one extra Lambda and a slightly longer path to
first token. B is defensible if you would rather have fewer components and accept a Teams-specific agent.

## Q2. How is the work handed off past the acknowledgement?

Depends on Q1 but worth deciding explicitly.

A) **Lambda asynchronous invoke** (`InvocationType: Event`) — simplest, no extra infrastructure. AWS retries
twice automatically; a dead-letter target is configurable.

B) **SQS queue** between front door and worker — explicit retry policy, a real DLQ, visible backlog,
natural throttle. One more resource, slightly more latency.

C) **EventBridge** — good for fan-out to future consumers; more indirection than this needs today.

D) **Step Functions** — overkill for a single call, but gives per-step visibility.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: B (SQS)** if you want operational visibility and a DLQ for failed activities, **A** if you
want the smallest possible first version. Given this is the repository's first compute and the build path is
unproven, A is the lower-risk starting point and B is a clean upgrade later.

## Q3. Is the agent Teams-aware or channel-agnostic?

A) **Channel-agnostic.** The agent receives normalised text plus context and returns text. It knows nothing
about Teams, Bot Framework, or activity types.

B) **Teams-aware.** The agent receives the raw Bot Framework Activity and handles Teams specifics itself.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A**, and note it is largely implied by Q1=A. It also makes the agent independently
testable without constructing Bot Framework payloads.

---

# Section 2 — Component Methods and Interfaces

## Q4. What is the contract between the front door and the agent?

A) **A normalised envelope** — e.g. `{conversation_id, user_id, text, history_key, system_prompt_ref}`. The
front door translates Bot Framework into this shape. Clean boundary, and the agent's `/invocations` payload
becomes stable and documentable.

B) **The raw Activity JSON**, passed through unchanged. Zero translation work, but couples the agent to Bot
Framework and makes A in Q3 impossible.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A.**

## Q5. Does the agent stream its output, or return it complete?

AgentCore Runtime supports both a JSON response and Server-Sent Events (`text/event-stream`).

A) **Agent streams (SSE); the worker forwards chunks to Teams.** The user sees text appear as it is
generated — the real point of FR-17. More complex: the worker must buffer to Teams' 1-per-second limit and
accumulate cumulative text.

B) **Agent returns the complete answer; the worker sends one informative update then the final message.**
Much simpler. The user sees a progress indicator and then the whole answer at once — still no timeout risk,
but less impressive than true streaming.

C) **Start with B, upgrade to A later.** Ship the pattern, refine the experience.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A if the demo needs to look good, C if the priority is landing something today.** Worth
knowing: Teams requires **cumulative** text and caps updates at 1/second with 1.5–2s buffering, so A's
benefit over B is real but bounded — the user sees a few incremental updates, not per-token typing.

---

# Section 3 — Service Layer and Orchestration

## Q6. Where does idempotency state live? (FR-11 requires it)

### Explained in plain terms, 2026-08-04 — you asked what this is for

**"Idempotency" just means: doing the same thing twice has the same effect as doing it once.**

Here is the problem it solves. **Azure Bot Service will sometimes send you the same message twice.** Not
because of a bug — by design. If it does not get a `200 OK` quickly enough, or the network hiccups, it assumes
delivery failed and retries. Your bot cannot tell a retry from a new message, because they are byte-identical
— *except* that the activity `id` is the same.

Without protection, the user types one question and **gets answered twice.**

**Your choice of async invoke adds a second, internal source of the same problem.** AWS Lambda asynchronous
invocation **automatically retries twice** if the function errors. So if the worker fails halfway through
replying — a gateway blip, a timeout — Lambda re-runs it, and the user can see a partial reply followed by
another attempt. This source is entirely internal and has nothing to do with Microsoft.

**And streaming makes the symptom worse, not better.** Teams permits **one concurrent streaming response per
chat**. A duplicate invocation starts a second stream in the same chat, which **errors** rather than merely
duplicating. So the visible failure is a broken-looking bot, not just a repeated answer.

**What the fix actually is**: before doing any work, write the activity `id` to a small store with a
"only if it isn't already there" condition. If the write fails, this is a duplicate — return `200` and stop.
A TTL of an hour is ample, since retries happen within seconds.

Concretely that is **one DynamoDB table with a TTL attribute** — roughly 15 lines of CloudFormation — and
**one conditional `PutItem`** in the worker. It is genuinely small.

**Honest read for a demo**: the probability is low, because you acknowledge instantly and rarely time out.
But the scenario where it does bite is precisely a live demo on conference wifi. Given that the failure is
visible on a screen in front of people, ~20 lines is cheap insurance.

---

The activity `id` must be recorded so a retried activity cannot produce a second reply.

A) **DynamoDB table** with a TTL — the conventional choice; explicit, cheap, easy to reason about. Adds one
resource, and would be the repository's first database.

B) **AgentCore Memory** — already in the design for conversation history, so no new resource. Fit for
purpose is uncertain; it is designed for conversational context, not deduplication keys.

C) **Skip it for v1** and accept the small chance of a duplicate reply.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A.** It is a small table with an obvious key, and the semantics are exactly right. B risks
misusing a memory service as a lock. C is tempting but duplicate replies are the most visible failure mode a
user will encounter.

## Q7. Who reads conversation history?

A) **The agent reads it itself** from AgentCore Memory, keyed on conversation and user. The worker passes
only a key. Keeps memory concerns inside the agent.

B) **The worker reads history and passes it in the payload.** The agent stays purely functional — same input
always yields the same output — which is easier to test, but the worker gains a dependency on the memory
store.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A**, since AgentCore Memory is part of the AgentCore runtime and sessions are already
per-user isolated. Choose B if you want the agent to be a pure function.

---

# Section 4 — Dependencies and Coupling

## Q8. How is code shared between the front door and the agent?

Both need some of the same things — configuration loading, structured logging, possibly types.

A) **A shared internal module** inside `blueprints/teams-bot/`, imported by both. No duplication; both
images include it.

B) **Deliberate duplication** — each component self-contained, no shared module. Simpler dependency graph,
some copy-paste.

C) **One image serving both roles**, with behaviour selected by an environment variable or entrypoint. Least
build work, but the Lambda then carries the agent's dependencies and cold-starts more slowly.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A.**

## Q9. Should the JWT validation be reusable by future blueprints?

The Bot Framework validation ruleset — including the `serviceurl` check that was silently broken in the
prototype — is the most security-critical code here, and any future Teams-fronted blueprint needs exactly the
same logic.

A) **Local to this blueprint for now.** Blueprints are leaves by convention; premature sharing creates
coupling. Extract later if a second Teams blueprint appears.

B) **Build it as a shared library from the start**, in a location other blueprints can consume.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A**, consistent with the repository's "blueprints as leaves" convention — but written as a
**self-contained module with no blueprint-specific imports**, so extraction later is a file move rather than
a refactor.

---

# Section 5 — Design Patterns and Constraints

## Q10. Language and runtime — confirming rather than asking

Python 3.12 on ARM64 is implied by AWS's AgentCore reference (uv + FastAPI + uvicorn) and by the repository's
existing Python tooling. Confirm, or state a preference.

A) **Python 3.12** for both the front door and the agent
B) Python for the agent, a different language for the front door Lambda
C) Something else

[Answer]:

**Recommendation: A.**

## Q11. One Dockerfile or two?

`pipeline/codebuild.yml` builds with `--target $CONTAINER_TARGET`, so a multi-stage Dockerfile with **named
targets** is the shape the existing build machinery already expects.

A) **One multi-stage Dockerfile with two named targets** — `frontdoor` and `agent`. Fits the buildspec
naturally, shares base layers. Requires two Build actions, or one action per target.

B) **Two separate Dockerfiles.** Clearer separation, more duplication, and the Build stage needs to know
about both.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: A** — the `--target` flag exists precisely for this, and it is the least fighting with
machinery that has never been run.

**Note**: if Q1 = A (separate worker Lambda), there are potentially **three** artifacts — front door, worker,
agent. The front door and worker are both small Lambdas and could reasonably share one image with different
handlers, which would keep this to two targets. Flagging so the answer to Q1 is applied consistently.

## Q12. How visible should failures be to the user?

When something breaks — the gateway is down, AgentCore times out, retrieval fails — what does the user see in
Teams?

A) **A generic apology message** posted to the conversation: "Sorry, I couldn't answer that just now."
Honest, and the user knows the bot is alive.

B) **Silence.** Log the error; post nothing. Safest from a data-leakage standpoint, but the user thinks the
bot is broken.

C) **A generic message plus a correlation ID** the user could quote when reporting it. Best for a workshop
where people will actively be debugging.

X) Other (please describe after [Answer]: tag below)

[Answer]:

**Recommendation: C.** SECURITY-09 and SECURITY-15 require that no internal detail reaches the user, which a
correlation ID satisfies — it is meaningless to an attacker and directly useful to whoever reads the logs.

## Q13. Is there an existing internal code style or scaffold to follow?

### Rephrased in plain terms, 2026-08-04 — the original question was too vague

What I was asking: **does Cornell have a house style for writing code that I should follow?** Things like a
linting configuration, a preferred project layout, a template repository, naming conventions, or a docstring
style.

**Why I asked at all**: this repository currently contains **no runtime application code** — only a 217-line
validator script. So whatever I write here becomes the pattern that every future blueprint copies. If a
standard already exists, it is much cheaper to follow it now than to have twelve blueprints written my way
and then get corrected.

**"There isn't one" is a completely fine answer** — probably the most likely one, given the platform is new.

A) **No convention exists / no preference.** I will use idiomatic modern Python consistent with the existing
`validate_stacks.py` — type hints, small single-purpose functions, comments only where a reader would
otherwise assume wrongly — and mirror the CloudFormation style already in `hello-world.yml`.

B) **There is a convention** — point me at the repo, doc or config and I will follow it.

[Answer]:

---

## After answers are received

I will analyse them for vagueness, contradictions and combined options; raise follow-up questions if any are
found; then generate the five design artifacts under `aidlc-docs/inception/application-design/` and verify
Security Baseline compliance before presenting the completion message.

**Anything left blank I will treat as accepting the recommendation shown**, and I will record that explicitly
rather than leaving it implied.
