# Code Generation — the front door unit

**Generated**: 2026-08-04
**Stage**: CONSTRUCTION — Code Generation (per-unit)
**Unit**: front door
**Status**: ⚠️ **RETRO-FITTED.** The code existed before this stage ran.

---

## What this document is, stated before anything else

`core-workflow.md` defines Code Generation as two parts: *"Part 1 — Planning: create detailed code
generation plan with explicit steps"*, then *"Part 2 — Generation: execute approved plan to generate
code, tests, and artifacts"*, with user approval between them.

**Neither part happened in that order.** The code was written first, across three commits, without a
plan, without the approval gate, and before `core-workflow.md` had been read in this session. So this
document cannot be the plan it is supposed to be.

What it is instead: **an honest reconstruction** — what was built, what a plan would have said, and
where the absence of one actually cost something. A workshop teaching this methodology should not have
its own artifacts imply the process was followed when it was not, so the deviation is the first thing
on the page rather than a footnote.

**Where the plan would have helped and did not** — three specific places, all found later and all
recorded elsewhere:

1. **Packaging.** Container-versus-zip was settled by a character count at 11:40 on demo day rather
   than by Infrastructure Design. It came out the same way, but by accident.
2. **The knowledge base coupling.** A deploy-time SSM-resolved id made the blueprint undeployable
   without another blueprint, violating FR-4. A plan reviewed against requirements would have caught
   that before it shipped.
3. **The directory.** The whole unit was built in `blueprints/course-chatbot/` and had to be moved.

## 1. What was generated

| Artifact | Lines | Purpose |
| --- | --- | --- |
| `src/botframework.py` | ~250 | Inbound trust, outbound tokens, replies. Imports only PyJWT and the stdlib — no blueprint import, so it lifts for a future Slack or web front end |
| `src/handler.py` | ~270 | The front door: validate → retrieve → ask → reply → 200 |
| `src/requirements.txt` | 24 | Declared dependency ranges, the file a human edits |
| `src/requirements.lock` | 36 | All 20 transitive packages at exact versions; what the image installs |
| `tests/test_botframework.py` | ~215 | 22 tests: JWT validation, activity parsing, log-id bounding |
| `tests/test_handler.py` | ~348 | 20 tests: the always-200 contract, `_body`, `_retrieve`, `_dispatch`, config |
| `infra/teams-bot.yml` | ~420 | The stack: Lambda, function URL, 2 secrets, 2 SSM parameters, log group, role, 3 conditional policies, metric filter, alarm |
| `Dockerfile` | ~37 | One named target, arm64, Lambda base image |
| `blueprint.yaml` | ~77 | The Builder MCP manifest |

**42 tests, all passing. `tools/check` green.**

## 2. Design decisions taken while writing, that no earlier stage had made

These are the ones a Code Generation plan would have surfaced for approval. Recorded now because they
are load-bearing and were made by the author alone.

| Decision | Why | Where it is now documented |
| --- | --- | --- |
| **Lazy `_Runtime`** rather than module-scope init | Module-scope failure happens during Lambda INIT, *before* `handler` runs — so the function returns 5xx regardless of the always-200 rule, and Azure retries forever. Found by writing a test, not by design | Functional Design §3, as "better than designed" |
| **`log_id` separate from `activity_id`** | The id is attacker-controlled and logged before auth passes. Sanitising the one used for reply URLs would break replies, since Bot Framework ids legitimately contain `\|` | 6 tests in `test_botframework.py` |
| **Unconfigured `BOT_APP_ID` refuses everything** | The alternative reading — "validation disabled" — turns a misconfigured deployment into an open relay on a public URL | Functional Design §1, row 2 |
| **Retrieval inside `_ask()`, not in the caller** | An agent should own its grounding, so the AgentCore swap moves retrieval and generation together | Functional Design §2 |
| **Passages wrapped in numbered `<passage N>` tags** | Delimiting makes a passage containing instruction-like text visibly data rather than instruction | Functional Design §2 |
| **`GreetingText` read with `or`, not a `.get` default** | The stack passes it unconditionally, so unset arrives as `""` — a `.get` default would be skipped and greet nobody | Comment at the code |

## 3. What a plan would have said, and what it would have changed

Reconstructed honestly rather than back-dated. Against `requirements.md`, a plan for this unit would
have listed roughly:

```
[ ] botframework.py: JwtValidator, ActivityNormalizer, TokenProvider, BotFrameworkClient
[ ] handler.py: FrontDoor dispatch, always-200 contract
[ ] IdempotencyStore + DynamoDB table                      <- NOT BUILT
[ ] Worker Lambda + async invoke                           <- NOT BUILT
[ ] DeliveryDispatcher + StreamingDelivery                 <- NOT BUILT
[ ] Agent container + GatewayClient + AgentCore resources  <- DEFERRED
[ ] Tests, including the mandatory FR-8a negative cases
[ ] Template, manifest, registry entry, pipeline actions
```

**Three of the eight would have been marked "not built" at plan time**, which is the point: the plan
would have made the reduction a decision to approve rather than an outcome to discover. As it went, the
gaps were found afterwards by writing the story map — which is how FR-9 came to be marked **VIOLATED**
rather than quietly passed over.

## 4. Deviations from Application Design

Six, listed with assessments in Functional Design §3. Summarised by kind:

- **Four follow from one decision** — synchronous single-Lambda delivery. Two of those four are genuine
  losses rather than simplifications: no delivery seam (FR-16) and no idempotency guard (FR-11).
- **One is an improvement** on the design: lazy initialisation.
- **One is neutral**: `reply_to_id` omitted from the activity, needed only for channel thread replies.

## 5. Code quality notes

**No repository code style exists** — that was established at Application Design (Q13), so the
convention followed is the one visible in `pipeline/validate_stacks.py` and `packages/builder-mcp`:
comments that explain *why*, named failure modes, and no restating of what the code plainly does.

**What the comments are for here.** Several carry information that is expensive to rediscover and
invisible in the code: that the emitter's claim is `serviceurl` and not `serviceUrl`; that a `.get`
default is skipped when a stack passes an empty string; that sanitising the URL-bound id breaks
replies. Those are the comments worth keeping. Anything merely narrating the next line is not.

**Known rough edges, not cleaned up:**

- `handler.py` mixes concerns slightly — `_Config` does both env reading and S3 fetching. Fine at this
  size; the seam to split is `_load_prompt`.
- No type checking is run anywhere in `tools/check`, so the annotations are documentation rather than
  a verified contract.
- `_ID_UNSAFE`'s allowlist was derived from observed Bot Framework ids plus the spec, not from an
  exhaustive list of what Microsoft may emit. A legitimate id containing something outside it would be
  mangled **in logs only** — never in the reply URL — so the failure mode is a confusing log line, not
  a broken bot. Bounded, but a guess.

## 6. What is verified, and what is only asserted

The distinction matters more than the test count.

| Claim | Basis |
| --- | --- |
| JWT validation rejects forged, expired, wrong-audience and mismatched-`serviceurl` tokens | **Verified** — 22 tests against a real RSA keypair |
| `handler` returns 200 on every failure path | **Verified** — no-auth, malformed JSON, empty event, oversized body, and an exception injected into `_dispatch` |
| Retrieval degrades without losing the answer | **Verified** — no id, throwing client, and query truncation |
| The log id cannot forge a log line or break reply URLs | **Verified** — 6 tests |
| The template is valid CloudFormation | **Verified** — cfn-lint clean |
| Every template parameter is passed explicitly | **Verified** — 17 of 17, cross-checked programmatically |
| The image builds for arm64 | **ASSERTED.** Docker is not available on the authoring machine. Never built, once |
| The Lambda runs and answers in Teams | **ASSERTED.** Never deployed |
| The gateway accepts this request shape | **ASSERTED, and this is the riskiest one.** `x-api-key` plus `anthropic-version` against `/v1/messages` is the Anthropic convention and the gateway is Anthropic-compatible, but no call has been made. A wrong auth header is a silent `401` |

**The bottom three are the demo risk**, and no amount of unit testing touches them. They belong to
integration testing, which is the next stage.
