# Architecture Note — Where Bedrock AgentCore Fits, and What the Ingress Gap Actually Is

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (research input, not a design decision)
**Status**: Findings only. Every choice below remains open in
`requirement-verification-questions.md`.

This note exists because two things came up mid-stage that the Reverse Engineering artifacts
could not answer: what the "no HTTPS ingress" finding concretely means for this work, and
whether Amazon Bedrock AgentCore is the answer to it. Both are recorded here so the Requirements
and Design stages inherit the research rather than repeat it.

---

## 1. What "no HTTPS ingress" means concretely

The Reverse Engineering assessment recorded this as the largest gap:

> Public HTTPS ingress — the bot cannot receive Bot Framework activities without one.

Restated without the abstraction:

**Microsoft Teams is the client. Your bot is the server.** The direction of the first request is
the whole point.

1. A user types a message in Teams.
2. Teams hands it to **Azure Bot Service**.
3. Azure Bot Service looks up the **messaging endpoint** configured on the bot resource — a
   single field holding one public HTTPS URL, e.g. `https://example.org/api/messages`.
4. Azure Bot Service **POSTs** a Bot Framework Activity JSON document to that URL, with an
   `Authorization: Bearer <JWT>` header.
5. It expects `200 OK` back, quickly. Anything else, or too slow, and it **retries** — which
   users see as duplicate replies.

Everything the bot does afterwards is a *separate, outbound* call from your side to
`{serviceUrl}/v3/conversations/{conversationId}/activities`. That direction is easy; outbound
HTTPS from AWS needs no ingress at all.

**The gap is step 3.** There is no URL to put in that field, because this repository has never
deployed anything that accepts an inbound request. Every stack to date is S3, IAM, SSM,
CodePipeline and CodeBuild — control-plane and storage resources. Nothing terminates TLS.
Nothing has a hostname. Nothing is listening.

So the gap is not "the code isn't written yet". It is that the **first architectural element the
bot needs does not have a precedent in this repository**: no Lambda has run, no API Gateway
exists, no function URL, no load balancer, no certificate, no DNS record. The container build
path that would produce a Lambda image is defined but has never been invoked.

### Why this is the largest gap and not just the first task

Three of the repository's hard constraints intersect exactly here:

| Constraint | Consequence at the ingress point |
| --- | --- |
| Everything is IaC through GitHub, no click-ops | The endpoint must be created by CloudFormation, so its URL is an output — not something typed into a console |
| Lambda means container images | The dormant ECR/CodeBuild path must be activated before any Lambda can exist |
| Secrets only in Secrets Manager | The handler must read the bot credential at runtime; no stack has ever read a secret |

And one thing sits outside all of them: the messaging endpoint URL has to be written into an
**Azure** resource. That is a cross-cloud handshake with a manual or Terraform-shaped step in
the middle, and this repository has no non-AWS provisioning of any kind.

### The security control that lives at this boundary

The endpoint is public. Anyone can POST to it. The only thing separating a real Teams activity
from a forged one is validation of that inbound JWT, and it is more specific than ordinary JWT
validation:

- RS256, keys from `https://login.botframework.com/v1/.well-known/keys`
- `iss` is `https://api.botframework.com`
- `aud` is the bot's client ID
- `exp` / `nbf` within tolerance
- **the `serviceurl` claim (lowercase `u`) must equal `body.serviceUrl`**

That last check is the one that matters most and the one most easily lost. It is what stops an
attacker who has obtained a valid token from redirecting the bot's replies to a `serviceUrl` they
control. Any design that delegates inbound auth to a generic JWT validator **will not perform
this check**, because it is a Bot Framework-specific correlation between a claim and the request
body — not a standard OIDC assertion. See §2.

---

## 2. Does Bedrock AgentCore close the gap?

**No. AgentCore is the brain, not the front door.** It is very likely the right choice for the
agent logic, and it is not a substitute for a Bot Framework-speaking endpoint.

### Why it looks like it might

AgentCore Runtime is genuinely reachable over the public internet. Its default network mode is
public, and it is invoked at a real HTTPS URL:

```
https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<url-encoded-agent-arn>/invocations?qualifier=DEFAULT
```

It also supports two inbound authentication mechanisms, configured at `CreateAgentRuntime`:

- **IAM SigV4**, the default
- **OAuth 2.0 JWT bearer** — `authorizerType: CUSTOM_JWT`, with
  `customJwtAuthorizer: {discoveryUrl, allowedAudience, allowedClients}`, IdP-agnostic

Since Azure Bot Service will POST to any HTTPS URL you give it, and since it sends a bearer
token, the shape superficially matches.

### Why it does not work as the messaging endpoint

Four reasons, in descending order of how hard they are to work around:

1. **The `serviceurl` claim check would be silently lost.** `customJwtAuthorizer` validates a JWT
   generically against an OIDC discovery document — issuer, audience, expiry, signature. It has
   no mechanism to assert that a claim inside the token matches a field inside the request body.
   Pointing it at Bot Framework metadata would authenticate the token and still leave the bot
   open to reply-redirection. This is a real control, deliberately documented in the research,
   and losing it silently is the worst possible failure mode.

2. **SigV4 is unavailable to the caller.** Azure Bot Service cannot produce an AWS Signature v4
   header. That removes the default and best-supported auth path entirely.

3. **Response contract mismatch.** Teams needs a fast, bare `200 OK` and nothing else — the
   actual answer arrives later via a separate outbound POST. AgentCore Runtime is built to return
   the agent's output, and supports SSE streaming (`Content-Type: text/event-stream`) for
   long-running work. Agent invocations can legitimately run for minutes. Teams will have retried
   several times by then.

4. **Discovery-URL shape.** Bot Framework's OIDC metadata is served at the non-standard path
   `https://login.botframework.com/v1/.well-known/openidconfiguration`. Whether
   `customJwtAuthorizer` accepts it is untested and beside the point given (1).

There is also a privacy note that belongs in the record: **AgentCore's JWT inbound auth writes
some JWT claims, including Subject, to CloudTrail.** AWS explicitly warns against putting PII in
that field. For a course chatbot with a FERPA dimension, that constrains what may be used as a
user identifier — relevant to Q20.

### The shape that does work

A small Bot Framework-speaking front door, with AgentCore behind it:

```
+---------------------------+
|  Microsoft Teams client   |
+-------------+-------------+
              |
              v
+---------------------------+
|   Azure Bot Service       |   holds ONE field: the messaging endpoint URL
+-------------+-------------+
              |  POST Activity JSON + Bearer JWT
              v
+-------------------------------------------------------+
|  AWS front door  (Lambda / API Gateway - Q7)          |
|                                                       |
|   1. validate JWT, INCLUDING serviceurl vs serviceUrl |
|   2. return 200 OK immediately                        |
|   3. hand the work off asynchronously                 |
+-------------+-----------------------------------------+
              |  InvokeAgentRuntime, SigV4, same account
              v
+-------------------------------------------------------+
|  Bedrock AgentCore Runtime                            |
|   ARM64 container in ECR, port 8080                   |
|   GET /ping  ->  {"status": "Healthy"}                |
|   POST /invocations                                   |
+-------------+-----------------------------------------+
              |
              v
+---------------------------+     +---------------------------+
|  Bedrock model inference  |     |  Bedrock Knowledge Base   |
+---------------------------+     +---------------------------+
              |
              |  reply, outbound from AWS
              v
+-------------------------------------------------------+
|  Bot Framework REST API                               |
|  POST {serviceUrl}/v3/conversations/{id}/activities   |
+-------------------------------------------------------+
```

**Text alternative.** The Teams client sends to Azure Bot Service. Azure Bot Service holds a
single messaging-endpoint URL and POSTs Activity JSON with a bearer JWT to it. That URL resolves
to an AWS front door, which does exactly three things: validates the JWT including the
`serviceurl`-to-`body.serviceUrl` correlation, returns `200 OK` immediately, and hands the work
off asynchronously. The work is performed by a Bedrock AgentCore Runtime — an ARM64 container in
ECR listening on port 8080, serving `GET /ping` and `POST /invocations` — invoked with SigV4 from
inside the same AWS account. That runtime calls Bedrock model inference and, if retrieval is in
scope, a Bedrock Knowledge Base. The answer is delivered by a separate outbound POST from AWS to
the Bot Framework REST API at `{serviceUrl}/v3/conversations/{conversationId}/activities`.

The front door is deliberately small: JWT validation, a fast acknowledgement, and a handoff. It
holds no agent logic. That keeps the Bot Framework-specific security surface in one auditable
place and leaves AgentCore free to be replaced or reused.

Note that this makes **Q8 largely self-answering**: if AgentCore is the backend, the work is not
reliably fast, so acknowledge-then-reply-proactively is the only safe pattern.

---

## 3. Two pieces of good news for this repository

### CloudFormation support exists

Verified available in `us-east-1`:

| Resource type | Availability |
| --- | --- |
| `AWS::BedrockAgentCore::Runtime` | Available |
| `AWS::BedrockAgentCore::RuntimeEndpoint` | Available |
| `AWS::BedrockAgentCore::Gateway` | Available |
| `AWS::BedrockAgentCore::Memory` | Available |
| `AWS::Bedrock::KnowledgeBase` | Available |
| `AWS::SecretsManager::Secret` | Available |

This matters more than it sounds. The no-click-ops constraint has no escape hatch, so a service
without CloudFormation coverage would have been disqualifying regardless of its merits. AgentCore
can be deployed entirely within the existing governed path.

`AWS::BedrockAgentCore::Memory` is also directly relevant to **Q9** — conversation state may not
need a hand-built DynamoDB table.

### The dormant container path finally has a reason to exist — but it is the wrong architecture

AgentCore Runtime requires the agent to be packaged as a container in ECR meeting a specific
contract:

- **ARM64**
- port **8080**, bound to `0.0.0.0`
- `GET /ping` returning `{"status": "Healthy"}`
- `POST /invocations`

This maps directly onto `ContainerRepository`, `ContainerBuildProject`, `ContainerBuildRole` and
`pipeline/codebuild.yml` — the components Reverse Engineering flagged as *defined but never
invoked*. Technical debt item 2 becomes the critical path.

**With one problem.** `pipeline/pipeline.yml` currently declares:

```yaml
Environment:
  ComputeType: 'BUILD_GENERAL1_SMALL'
  Image: 'aws/codebuild/amazonlinux2-x86_64-standard:4.0'
```

That is **x86_64**. So the build path is not merely untested — it is currently the wrong
architecture for AgentCore. Resolving it means either switching that project to an ARM compute
type and aarch64 image, adding a second ARM project, or cross-building with `buildx` and QEMU
(slow). Any of the three is a change to `pipeline/pipeline.yml`, whose mechanics `CLAUDE.md`
instructs be preserved — so it is a decision to be taken deliberately, not a quiet edit.

This is captured as a DevOps question rather than resolved here.

---

## 4. What this note does not decide

Nothing. Specifically still open, and asked in `requirement-verification-questions.md`:

- whether AgentCore is used at all — it depends entirely on the capability chosen in **Q3**
  (an echo bot needs no agent runtime whatsoever)
- the ingress shape — **Q7**
- n8n's fate — **Q6**
- conversation state, now including AgentCore Memory as an option — **Q9**
- whether the container path is activated in this work or a preparatory PR — **Q17**

The recommendation embedded above is only this: **whatever the backend turns out to be, a
Bot Framework-speaking front door is required, and it cannot be delegated to AgentCore's own
authorizer without losing the `serviceurl` check.**

---

## Sources

AWS documentation, retrieved 2026-08-03, via the AWS Knowledge MCP server: Bedrock AgentCore
`InvokeAgentRuntime` API reference, AgentCore Identity inbound authentication, AgentCore Runtime
container service contract, and CloudFormation regional resource availability for
`us-east-1`. Microsoft-side behaviour is from the repository's own research documents under
`docs/teams-chatbot-docs/`, not re-derived here.
