# AWS Account Reconnaissance — Deploy Target for the Teams Chatbot Blueprint

**Performed**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (research input)
**Method**: read-only AWS CLI. Every call was `sts get-caller-identity`, `list-*`, `describe-*` or
`get-*`. **Nothing was created, modified or deleted.** No secret value was retrieved — only secret
*names* were listed.

**Account identifiers are deliberately redacted from this file.** This repository is public, and
`CLAUDE.md` records that secret scanning is disabled by enforced org policy. Account IDs are not
secrets, but they enable role enumeration for cross-account probing, so they are referred to below
by role rather than by number.

Two accounts were inspected. The distinction turned out to matter.

| Reference | What it is |
| --- | --- |
| **Account P** | A busy shared **production** account. Inspected first, in error. |
| **Account W** | The **workshop deploy target**. `aidlc-*` stacks live here. |

Identity in both cases was an SSO `sso-admin` role, region `us-east-1`.

---

## 1. The headline: follow-up A is answered, and the answer is A2

`devops-questions.md` follow-up A asked whether "yes, we have agent core" meant a deployed runtime
(**A1**, small path) or an enabled service (**A2**, larger path).

In **Account W**:

```
list-agent-runtimes  ->  { "agentRuntimes": [] }
list-gateways        ->  { "items": [] }
list-memories        ->  { "memories": [] }
```

Empty in Account P as well. Critically, these calls **succeeded** — they returned empty collections
rather than `AccessDeniedException` or a service-not-enabled error. So the AgentCore control plane
is reachable and callable, and **nothing is deployed**.

**This is A2.** The blueprint must **create** the AgentCore runtime, not merely invoke one.
Consequences:

- ARM64 container build is **on the critical path**, so DevOps question 2 is live and needs an
  answer.
- The work includes an ECR image, an execution role, agent code, `AWS::BedrockAgentCore::Runtime`
  and `AWS::BedrockAgentCore::RuntimeEndpoint`.
- No cross-account resource policy question arises, which removes one complication.

### CloudFormation support verified directly

Not inferred from the regional availability API this time — queried against the account itself:

| Resource type | `ProvisioningType` |
| --- | --- |
| `AWS::BedrockAgentCore::Runtime` | `FULLY_MUTABLE` |
| `AWS::BedrockAgentCore::RuntimeEndpoint` | `FULLY_MUTABLE` |
| `AWS::BedrockAgentCore::Memory` | `FULLY_MUTABLE` |
| `AWS::BedrockAgentCore::Gateway` | `FULLY_MUTABLE` |
| `AWS::Bedrock::KnowledgeBase` | `FULLY_MUTABLE` |

All five registered and fully mutable in Account W, `us-east-1`. AgentCore can be deployed inside
the no-click-ops constraint with no escape hatch. `FULLY_MUTABLE` also means updates happen in
place rather than by replacement, which matters for a resource the pipeline will redeploy on
every merge.

---

## 2. The deploy path is live and green

This is better than the Reverse Engineering artifacts assumed. They described the pipeline from
the template; it is actually running.

| Stack | Status |
| --- | --- |
| `aidlc-account-bootstrap` | `CREATE_COMPLETE` |
| `aidlc-main-pipeline` | `CREATE_COMPLETE` |
| `aidlc-main-hello-world` | `UPDATE_COMPLETE` |

**CodeConnections `cu-aaii` is `AVAILABLE`** — the human browser handshake that `CLAUDE.md` warns
about is **already done**. The SSM parameter `/code-connections/cu-aaii` exists, and bootstrap's
`CompleteTheHandshakeHere` output confirms that was the intended mechanism.

Pipeline parameters in Account W match the template defaults exactly:

```
Application               aidlc
Environment               main
Owner                     ai-sei
RemoteGitRepository       cu-aaii/ai-dlc-workshop
SsmCodeStarConnectionArn  /code-connections/cu-aaii
```

The three most recent pipeline executions all report **`Succeeded`**, each triggered by
`Webhook` — on 2026-08-03. The merge-to-deploy path works end to end today.

**Resolves DevOps question 6 completely**: account bootstrapped, handshake complete, pipeline
green.

### The four-tag convention is real, and `cornell:deployment-id` is the stack name

All four tag keys are in use in Account W, carried by both hello-world resources:

| Tag | Observed value |
| --- | --- |
| `cornell:owner` | `ai-sei` |
| `cornell:blueprint` | `hello-world` |
| `cornell:blueprint-version` | `0.1.0` |
| `cornell:deployment-id` | `aidlc-main-hello-world` |

So `cornell:deployment-id` is populated with the **stack name**, and `cornell:owner` defaults to
`ai-sei`. **Resolves DevOps question 22** — no invention needed, follow the observed pattern.

Note for the design stage: hello-world's stack-level `Tags` is empty (`[]`). The tags are applied
per-resource inside the template. That works, and it is also why every new resource type must be
tagged by hand — including the `AWS::SSM::Parameter` tags-as-map asymmetry. Stack-level tags would
propagate automatically. Not a requirement, but worth a deliberate decision when the blueprint
introduces a dozen resources instead of two.

Also observed: hello-world takes a `SourceCommitId` parameter (currently commit `416891b`) and a
`BlueprintVersion` (`0.1.0`), alongside `Owner`, `Application`, `Environment`.

---

## 3. Account W confirms every "absent" finding from Reverse Engineering

The RE artifacts asserted these from reading templates. Now verified against the live account.

| Thing | Account W reality |
| --- | --- |
| Deployed application compute | **None.** One Lambda exists and it is a StackSet-managed org-access function, not ours. |
| ECS clusters | **None.** |
| Load balancers | **None.** |
| Container images | ECR repository `aidlc-main` **exists and contains zero images.** |
| Secrets consumed | **No secrets at all** in Secrets Manager. |
| Knowledge bases | **None.** |
| Public HTTPS ingress | **None** — no function URLs, no API Gateway, no ALB. |

The ECR result is the sharpest confirmation of the RE finding: the repository was created by
`ContainerRepository`, so that part of the template has deployed successfully — and it has never
received an image. The build path is provisioned and unexercised, exactly as documented.

---

## 4. New finding: there is no DNS zone and no certificate in Account W

This **reverses** the optimistic read I formed while looking at Account P.

| | Account P (production) | **Account W (workshop)** |
| --- | --- | --- |
| Route 53 public zones | `scl.cucloud.net`, `ssit.cucloud.net`, `cornell-concert.com` | **none** |
| ACM certificates | many, incl. three `*.ssit.cucloud.net` wildcards | **none** |

So a stable custom hostname such as `teams-bot.<something>.cucloud.net` is **not** available in the
workshop account today. Getting one requires either a hosted zone here plus delegation from
whoever owns `cucloud.net` — a cross-team request with its own lead time — or issuing a
certificate validated against a zone that lives elsewhere.

**Why this matters more than it looks.** The Azure Bot Service messaging endpoint URL is
configured **once, by hand or by Terraform, on the Azure side**. If it is the raw AWS-provided URL:

- a Lambda function URL is `https://<id>.lambda-url.us-east-1.on.aws`
- that identifier **changes if the function is replaced**, not merely updated

Every change of URL means going back into Azure and reconfiguring the bot. For a workshop where
stacks may be torn down and recreated, that is a recurring manual step in the middle of an
otherwise automated path — and it is precisely the kind of click-ops the repository exists to
avoid.

**Recorded as a requirement candidate, not a decision**: the ingress resource should be one whose
URL survives redeployment, or the URL should be an explicit stack output that the Azure-side
provisioning step consumes rather than a value transcribed by a human. This is a genuine design
constraint that neither the research documents nor the RE artifacts surfaced.

---

## 5. Bedrock model availability

Listable in Account W, `us-east-1` — foundation models include `anthropic.claude-sonnet-5`,
`anthropic.claude-opus-4-7`, `anthropic.claude-opus-4-5`, `anthropic.claude-sonnet-4-5` and the
Claude 3 Haiku family.

Cross-region **inference profiles** are also present (`us.anthropic.claude-sonnet-4-6`,
`us.anthropic.claude-opus-4-7`, and others). These matter: for several current models an inference
profile is the *supported* invocation path rather than the bare model ID, so the design should
expect to reference a profile.

Embeddings models available include `amazon.titan-embed-text-v1`, `cohere.embed-v4:0` and
`amazon.nova-2-multimodal-embeddings-v1:0` — relevant only if Q3 selects retrieval.

**Caveat, and it is a real one**: `list-foundation-models` reports what exists in the region, not
what this account is *entitled to invoke*. Per-model access grants are a separate control and
could not be verified read-only without actually invoking a model, which would incur cost and
constitutes an action rather than an observation — so it was not done. **DevOps question B stands.**

---

## 6. Account P observations worth keeping

Account P is not the deploy target, but it is where the reference pipeline came from, and it shows
what the platform team actually operates. Useful context for design review.

- **~285 CloudFormation stacks**, ~110 ECS clusters, following `<app>-<env>-pipeline` /
  `<app>-<env>-service` with environments `dev`, `test`, `main`. This is the origin of the
  `Environment` naming, and every value is ≤4 characters — which is where the
  `[a-z0-9]{1,4}` pattern comes from.
- **Public HTTP ingress there is ECS Fargate behind shared internet-facing ALBs.** Also four
  API Gateway **REST (v1)** APIs, all `prod-*`. **Zero HTTP APIs (v2). Zero Lambda function URLs
  across the entire account.**
- Secrets convention is `<app>/<env>/<name>`, e.g. `ssit-documentdb/dev/mongodb-atlas-source`.
  A bot credential would fit as `aidlc/main/teams-bot-client-secret`.
- Tag keys there are `Application`, `Environment`, `Cost Center`, `Documentation`, `Version`,
  `ContactEmailParam`. **No `cornell:*` keys anywhere** — the four-tag scheme is new to Account W,
  so it will not collide, and the inventory tooling that consumes it does not exist yet either.
- Connection ARNs are resolved from SSM under `/github-connections/<Org>` there, versus
  `/code-connections/<Org>` in the workshop repo. Different prefix, same idea; bootstrap creates
  its own, so nothing is broken.

### The question this raises about "yes, we can do lambda"

Across ~285 stacks and 20 Lambda functions in the production account, **not one Lambda has a
function URL**, and every public HTTP entry point is an ALB or an API Gateway REST API.

That does not contradict the answer — Lambda is clearly permitted, and `CLAUDE.md` states
serverless-first with Lambda meaning container images. But it does suggest "we can do lambda" may
mean *Lambda is available* rather than *we routinely expose Lambda publicly*. Two consequences
worth putting in front of the DevOps owner rather than assuming past:

1. A public Lambda function URL with `AuthType: NONE` would be the **first** unauthenticated-at-the-edge
   endpoint in either account. That may attract a security review that an ALB or API Gateway
   deployment would not.
2. The team's operational muscle memory — dashboards, alarms, runbooks, log conventions — is built
   around ECS behind an ALB. Q7 option D is the pattern they actually run, and it happens to align
   with AgentCore needing a container image anyway.

This is **not** a recommendation to override the serverless-first constraint. It is a flag that
Q7's answer has an operational dimension the question did not capture, and that confirming it
costs one sentence now versus a rework later.

---

## 7. Net effect on the open questions

| Question | Before | After |
| --- | --- | --- |
| DevOps follow-up A — runtime or service? | Open | **A2 — service enabled, nothing deployed.** Blueprint must create the runtime. |
| DevOps 2 — ARM64 build | Open, possibly moot | **Live and on the critical path**, because A2. |
| DevOps 6 — bootstrap, handshake | Open | **Resolved.** Bootstrapped; `cu-aaii` connection `AVAILABLE`; three green webhook runs today. |
| DevOps 22 — tag values | Open | **Resolved.** `cornell:owner=ai-sei`, `cornell:deployment-id=<stack name>`. |
| DevOps 4 — stable hostname | Assumed easy | **Harder than assumed.** No zone, no cert in Account W. New constraint on ingress choice. |
| DevOps B — Bedrock model access | Open | **Still open.** Region is well stocked; per-account entitlement not verifiable read-only. |
| DevOps 12 — cost guardrails | Open | Still open. Nothing observed either way. |
| Q7 — ingress shape | Answered "Lambda" | Answered, with a **new operational caveat** and a **URL-stability constraint**. |

Nothing in this reconnaissance changes a product decision. `requirement-verification-questions.md`
remains unanswered and `requirements.md` is not generated.
