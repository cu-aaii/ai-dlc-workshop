# teams-bot

**"Chatbots (incl. Microsoft Teams-fronted) — basic and advanced conversational apps, with Teams
as the default frontend for internal users."** That is the participant brief's catalog entry, and
this is that building block. Track C.

A person messages the bot in Teams and gets an answer. Everything behind Teams runs on AWS.

**It is a template, not a bot.** What any deployment answers questions *about* is set by its
`SystemPrompt` parameter, which the Cornell Builder writes into a deployment repo as a reviewable
file. A course assistant, a departmental helpdesk and an internal FAQ are the same blueprint with
different prompts — so nothing here is course-specific, and the default prompt is deliberately
generic.

## Shape of a request

```
Teams client
  └─> Azure Bot Service            Microsoft side, one-time registration per bot
        └─> Lambda Function URL    public, AuthType: NONE
              └─> handler          validates the Bot Framework JWT, incl. the serviceurl claim
                    ├─> Bedrock Retrieve    optional, in-account, SigV4
                    ├─> LiteLLM gateway     all model traffic, no exceptions
                    └─> Bot Framework API   the reply
```

**Text alternative.** A Teams client sends a message; Azure Bot Service POSTs a Bot Framework
activity to the Lambda Function URL. The handler validates the request's JWT — signature, issuer,
audience, expiry, and the `serviceurl` correlation — and rejects anything that fails. For a valid
message it optionally retrieves passages from a Bedrock knowledge base, calls Cornell's LiteLLM
gateway for an answer, and posts that answer back through the Bot Framework API. One synchronous
Lambda invocation does all of it.

## Three constraints worth knowing before changing anything

- **All model traffic goes through Cornell's LiteLLM gateway.** Never Bedrock inference directly.
  That routing is what makes medium-risk data permissible; it is a hard constraint.
- **The handler always returns `200`** — including on a rejected token. A 4xx makes Azure Bot
  Service retry a request that can never succeed, forever.
- **Retrieval is `Retrieve` and nothing else.** `RetrieveAndGenerate` and `AgenticRetrieveStream`
  invoke a Bedrock foundation model internally, which would move generation off the gateway.

## Retrieval is optional

`KnowledgeBaseId` empty means the bot answers from its system prompt and says so when it does not
know. Set it and answers are grounded in retrieved passages, with the execution role granted
`bedrock:Retrieve` on that one knowledge base and nothing else.

To point it at the knowledge base the [`knowledgebase`](../knowledgebase/) blueprint deploys:

```sh
aws ssm get-parameter --name /aidlc/main/knowledgebase/knowledge-base-id \
  --query Parameter.Value --output text
```

...then pass that id as `KnowledgeBaseId`.

## What has to happen before it answers anything

The stack deploys green without these and then answers nothing, so they are easy to miss.

1. **Inject both secret values.** The template creates them with `GenerateSecretString`
   placeholders, so the bot authenticates with a random string until they are replaced.
   ```sh
   aws secretsmanager put-secret-value \
     --secret-id aidlc/main/teams-bot/bot-client-secret --secret-string '<entra client secret>'
   aws secretsmanager put-secret-value \
     --secret-id aidlc/main/teams-bot/gateway-api-key --secret-string '<gateway service key>'
   ```
2. **Point the Azure bot at the stack's `FunctionUrl` output.**
   ```sh
   az bot update --name <bot> --resource-group <rg> --endpoint <FunctionUrl>
   ```
   Mind which tenant each command runs against: the Bot Service resource and the Entra app
   registration can live in **different** tenants, and that is by design rather than a
   misconfiguration.

## Layout

```
Dockerfile              one named target: teams-bot. CONTAINER_CONTEXT = blueprints/teams-bot
blueprint.yaml          the Builder MCP manifest
infra/teams-bot.yml     the stack
infra/azure/            Terraform for the Microsoft side -- NOT BUILT, a README only
src/handler.py          the front door
src/botframework.py     inbound trust, outbound tokens, replies. No teams-bot imports, so it
                        lifts cleanly for a future Slack or web front end
src/requirements.lock   exact pins; the image installs from this, not requirements.txt
tests/                  42 tests, no AWS and no network
aidlc-docs/             the AI-DLC record for this blueprint
```

## Tests

```sh
uv run --python 3.13 --with 'PyJWT[crypto]>=2.8,<3' --with 'anthropic>=0.92,<2' \
    --with boto3 --with pytest pytest blueprints/teams-bot/tests -q
```

The `serviceurl` cases are **required**, not optional coverage. That check was present and
non-functional in the n8n prototype — it read `payload.serviceUrl` (camelCase) against a claim
actually named `serviceurl`, so it always compared against `None` and a truthiness guard turned it
into a silent skip. It is the control that stops an attacker holding a valid token from redirecting
the bot's replies.

## Known gaps

Recorded rather than left to be discovered. Detail in
[`aidlc-docs/inception/application-design/unit-of-work-story-map.md`](aidlc-docs/inception/application-design/unit-of-work-story-map.md).

| Gap | |
| --- | --- |
| **FR-9 violated** | The handler works, then returns 200 — it cannot acknowledge first, because that is what the withdrawn worker Lambda existed for. Fine inside the 10–15s Teams budget, `504:GatewayTimeout` outside it |
| **No idempotency guard** | An Azure retry can produce a duplicate reply |
| **No delivery seam** | Group and channel scopes would change the reply path rather than adding a strategy |
| **No conversation memory** | Every message is single-turn, and Teams supplies no history to compensate |
| **Base image unpinned** | Dated exception to SECURITY-10, expires 2026-08-05: [`docs/decisions/0001`](../../docs/decisions/0001-course-chatbot-base-image-unpinned-for-demo.md) |

**Restoring the worker Lambda closes the first three at once**, which makes it the highest-value
next change — ahead of moving the model call onto AgentCore, because that adds capability while this
fixes correctness.
