# Integration Test Instructions — teams-bot

**Generated**: 2026-08-04
**Stage**: CONSTRUCTION — Build and Test

## Why this document carries most of the risk

`unit-test-instructions.md` covers 42 tests that need no AWS and no network. They verify a great deal
and they **cannot** verify the three things most likely to break, all listed as ASSERTED in
`../front-door/code/code-generation.md` §6:

1. The image builds for arm64 — **never built, not once.** Docker was unavailable while writing it.
2. The Lambda runs and answers in Teams — **never deployed.**
3. **The gateway accepts this request shape** — never called. This is the sharpest one: a wrong auth
   header is a silent `401`, not an error that explains itself.

Everything below is ordered so that the cheapest test of the riskiest assumption comes first.

---

## Step 0 — Test the gateway with `curl` before anything else

**Five seconds, and it retires the single most likely failure.** The code sends `x-api-key` plus
`anthropic-version: 2023-06-01` to `POST {GATEWAY_BASE_URL}/v1/messages`, which is the Anthropic
convention. The gateway is Anthropic-compatible, so that *should* hold — but LiteLLM proxies commonly
accept `Authorization: Bearer` instead, and no call has been made.

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://api.ai.it.cornell.edu/v1/messages \
  -H 'content-type: application/json' \
  -H "x-api-key: $GATEWAY_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"claude-haiku-4-5","max_tokens":16,
       "messages":[{"role":"user","content":"reply with the single word ok"}]}'
```

| Result | Meaning |
| --- | --- |
| `200` | The shape is right. Nothing to change |
| `401` | **Auth header is wrong.** Retry with `-H "Authorization: Bearer $GATEWAY_KEY"`; if that returns `200`, change the header in `handler.py`'s `_ask` |
| `404` | Wrong path. Try `/v1/chat/completions` — that would mean the gateway exposes the OpenAI-shaped route, not the Anthropic one, and `_ask` needs a different body |
| `400` | Path and auth are fine; the body is wrong. Read the response |

**Do this before merging.** Discovering it after deployment costs a pipeline round trip and looks, in
CloudWatch, exactly like a bad secret.

## Step 1 — Build the image locally

Covered in `build-instructions.md`. It proves arm64 and the dependency resolution with no AWS at all,
and it is most of assumption 1 above.

## Step 2 — Merge, and expect the first merge not to deploy

**This will look like failure and is not.** A CodePipeline execution uses the pipeline structure that
was in place when it *started*. The merge that adds a Build action updates the pipeline, deploys the
already-registered stacks, reports every stage green — and does not run the new action.

```sh
aws codepipeline start-pipeline-execution --name aidlc-main-pipeline
```

Watch the second execution, not the first. Budget for it rather than debugging it.

## Step 3 — Inject both secrets

The stack creates both with `GenerateSecretString` placeholders, so **it deploys green and the bot
authenticates with a random 32-character string.** Symptom: `401` from Microsoft in CloudWatch, no
reply in Teams, and nothing wrong-looking in CloudFormation.

```sh
aws secretsmanager put-secret-value \
  --secret-id aidlc/main/teams-bot/bot-client-secret --secret-string '<entra client secret>'
aws secretsmanager put-secret-value \
  --secret-id aidlc/main/teams-bot/gateway-api-key   --secret-string '<gateway service key>'
```

**Never `SecretString` in the template.** That property is reasserted on every stack update, and
`PipelineDeploy` redeploys on every merge to `main` — so a placeholder there resets the live credential
several times a day. This is why `GenerateSecretString` plus a one-time injection is the pattern.

## Step 4 — Point Azure at the function URL

```sh
aws cloudformation describe-stacks --stack-name aidlc-main-teams-bot \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text
```

Then, **against the tenant that owns the Bot Service resource**:

```sh
az bot update --name <bot> --resource-group <rg> --endpoint <FunctionUrl>
```

> **The tenant trap.** The Bot Service resource and the Entra app registration can live in **different
> tenants** — that is by design, not misconfiguration. `az bot` needs the login for the tenant holding
> the ARM resource; anything touching the app registration or the Teams catalog needs the other. The
> wrong login produces a `Forbidden` an hour into debugging, which is why it is called out here rather
> than left to be rediscovered.

Also confirm `az ad sp create` was run for the app, not just `az ad app create`. The Portal does both
when you click through; the CLI does not, and the omission surfaces far away — at the bot's **first
outbound token call**, with nothing pointing back at the cause.

## Step 5 — The actual integration tests

Ordered so each failure localises to one thing.

| # | Test | Expected | If it fails |
| --- | --- | --- | --- |
| 1 | `curl -sS -o /dev/null -w '%{http_code}' <FunctionUrl>` with no auth | **`200`** | A 5xx means an import-time or INIT failure — check the log group. A 403 means the function URL permission is wrong |
| 2 | CloudWatch for that request | `rejected activity: … reason=missing or malformed Authorization header` | No log line at all means the request never reached the handler |
| 3 | Add the bot in Teams | The greeting appears | Nothing means Azure cannot reach the endpoint — recheck step 4. Two greetings means the `28:` filter is broken |
| 4 | Send "hello" | A reply within ~10s | `504:GatewayTimeout` in Teams means the round trip exceeded the channel budget — see §Performance. A generic failure message plus a reference means an exception; grep the reference in CloudWatch |
| 5 | Send a question the material covers, with `KnowledgeBaseId` set | A grounded answer | `retrieved 0 passage(s)` in the logs with a non-empty knowledge base means the query or the id is wrong |
| 6 | Send something the material does not cover | **A refusal**, not an invention | An invented answer means the grounding block is not reaching the model — this is a demo-credibility failure, not a cosmetic one |
| 7 | Send two messages quickly | Both answered, in order | **A duplicate answer to one message is expected behaviour**, not a bug to chase: there is no idempotency guard (FR-11, U4 withdrawn) |

**Test 6 is the one to run in front of an audience.** The refusal is the guardrail working, and it is
the behaviour that distinguishes this from a chatbot that will confidently invent a due date.

## What cannot be integration tested here

Stated so nobody spends the time looking:

- **Group chat and channel scopes.** Not built (U8). The manifest declares personal scope only.
- **Streaming.** Not built (U7). Replies arrive whole.
- **Multi-turn conversation.** There is no conversation memory at all — every message is independent,
  and Teams supplies no history to compensate. A follow-up like "and when is that due?" will not
  resolve its referent.
- **AgentCore.** Deferred; the model call is still in the Lambda.

## Performance

No SLA, and no load test is planned or warranted at workshop scale — tens of users.

**But one performance property is functional rather than optional**: Teams gives 10–15 seconds
depending on channel before showing the user `504:GatewayTimeout`. Since FR-9 is **violated** — the
handler works and *then* returns 200, because acknowledging first is what the withdrawn worker existed
for — that budget covers the entire round trip: cold start, retrieval, generation, reply.

Measure it once, from the CloudWatch `REPORT` line:

```sh
aws logs filter-log-events --log-group-name /aws/lambda/aidlc-main-teams-bot \
  --filter-pattern 'REPORT' --query 'events[*].message' --output text
```

Watch `Duration` and `Init Duration` separately. **A cold start is the exposure**; a warm invocation
almost certainly fits. If cold starts do breach it, the levers in order of cheapness are: send one
message to warm the function before the demo, lower `MAX_TOKENS`, keep `EFFORT=low`, and only then
consider restoring the worker.
