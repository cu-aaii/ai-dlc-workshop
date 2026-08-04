# DevOps Questions — for Dan Klinger

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis
**Purpose**: Questions that only the platform/DevOps owner can answer. These are *inputs* to the
requirements, distinct from `requirement-verification-questions.md`, which asks the product owner
what the bot should do.

Ordered so that the answers that change the architecture come first. Each carries **what changes
depending on the answer** — that is the part worth reading aloud, because it tells Dan why the
question is being asked and lets him volunteer the constraint you didn't know to ask about.

Background for questions 2, 5 and 12 is in `agentcore-placement-note.md`.

---

## Answers received 2026-08-03

From the short list of five. Recorded verbatim in `../../audit.md`.

| # | Question | Answer | Effect |
| --- | --- | --- | --- |
| 1 | Does an AgentCore runtime already exist? | *"Yes, we have agent core."* | **Partially resolved — see follow-up A.** AgentCore is available. Whether a *deployed runtime* exists or the *service* is enabled is still open, and the two produce different templates. |
| 3 | Public Lambda function URL allowed? | *"Yes, we can do lambda."* | **Resolved.** Q7 → option A. The ingress gap has a chosen shape: Lambda function URL, `AuthType: NONE`, JWT validated in the handler. |
| 14 | Who holds Azure Contributor? | *"We're using a dev env for all this so we have complete control."* | **Resolved.** Dev tenant, full control. No external approval dependency. |
| 15 | Which tenant — dev or production? | Same as above. | **Resolved.** Dev tenant for this work. Production promotion is a later, separate decision. |
| 17 | Teams admin and org-publish lead time? | Same as above. | **Resolved.** Self-service in the dev tenant. The org-publish schedule risk is removed, so Q4 scopes beyond personal chat are no longer gated on someone else's approval queue. |
| 10 | VPC required, or public network? | *"I don't know the answer to this."* | **Open. Proceeding on a stated assumption — see below.** |

Additional input: the user supplied `docs/teams bot exploration.json`, the n8n prototype, as a
reference for how the flow was built during testing, while confirming **n8n is not the target**.
Analysed in `prototype-reference-implementation.md`.

### Assumption recorded for question 10 (networking)

Since no VPC requirement is known, the working assumption is **Lambda outside a VPC, with public
internet egress**.

Rationale: the handler must reach three Microsoft endpoints — `login.botframework.com` for JWKS,
`login.microsoftonline.com` for the outbound token, and `*.smba.trafficmanager.net` for replies.
Lambda outside a VPC has internet egress by default and costs nothing extra. Putting it in a VPC
requires private subnets, a NAT gateway with a standing hourly charge, security groups and route
tables — roughly doubling the template — and AgentCore Runtime's default network mode is public
in any case.

This assumption is **cheap to hold and expensive to reverse**, so it is flagged rather than
buried: retrofitting a VPC later means reworking the ingress stack, not adding to it. It needs
confirmation from whoever owns network policy for the account before anything long-lived is
deployed. It is safe for a dev environment.

### Follow-up questions created by these answers

**A. On "yes, we have agent core" — which of these is true?**

- **A1** — a runtime is already deployed and running, and the blueprint should **invoke** it. Then
  we need its runtime ARN, its account, and whether cross-account resource policies are involved.
  This is the small path: an IAM policy and an endpoint reference.
- **A2** — the service is enabled and available, but nothing is deployed, so the blueprint must
  **create** the runtime. This is the larger path: ARM64 container build, ECR repository, execution
  role, agent code, `AWS::BedrockAgentCore::Runtime` and `::RuntimeEndpoint`.

*Why it still matters*: this is the largest single remaining swing in scope, and it is a one-word
answer. Worth getting before design starts.

**B. Which Bedrock models are access-enabled in the dev account?** Per-model access is a console
grant with lead time. Needed regardless of A1 or A2 if Q3 lands on C, D or E.

**C. Since the Lambda path is confirmed — is the ARM64 build question (question 2) still ours to
resolve?** If A1 is true, the container build may not be needed at all for the first version: the
Lambda front door can be a zip-based function or a container, and the agent already exists. If A2
is true, question 2 is on the critical path.

**D. Still open from Tier 2, unaffected by these answers**: account ID and bootstrap status
(question 6), CodeConnections handshake completion (question 6), cost guardrails (question 12),
`cornell:owner` and `cornell:deployment-id` values (question 22).

---

## Tier 1 — Answers that change the design

### 1. What does "we're using Bedrock AgentCore" already mean in practice?

Is there an existing AgentCore runtime, reference repository, or agreed pattern at Cornell that
this should conform to? Or is it a direction that nobody has implemented yet?

*Why it matters*: if an AgentCore runtime already exists, the blueprint may only need to **call**
it — an IAM policy and an endpoint ARN. If not, the blueprint has to **deploy** one, which brings
in a container build, an ECR repository, an execution role, and an ARM64 image. Those are
completely different templates and a very different amount of work.

### 2. AgentCore requires **ARM64** containers. Our build project is x86_64. How do we fix that?

`pipeline/pipeline.yml` currently has:

```yaml
ComputeType: 'BUILD_GENERAL1_SMALL'
Image: 'aws/codebuild/amazonlinux2-x86_64-standard:4.0'
```

AgentCore Runtime requires a linux/arm64 image on port 8080 serving `GET /ping` and
`POST /invocations`. Options: switch that project to an ARM compute type and aarch64 image; add a
second ARM-specific project; or cross-build with `buildx` + QEMU emulation (works, slow).

*Why it matters*: `CLAUDE.md` says the pipeline's mechanics were adapted from a known-good
reference and should be preserved, so this is your call rather than an edit made quietly. Also
worth knowing: **that container path has never actually run**, so whoever needs it first pays the
cost of debugging it.

### 3. Is a public HTTPS endpoint acceptable, and in what form?

The bot must expose one public HTTPS URL for Azure Bot Service to POST to. Simplest is a Lambda
function URL with `AuthType: NONE`, authenticated by validating the Bot Framework JWT inside the
handler. Alternatives are API Gateway HTTP API, or REST API with WAF.

Specifically: **is there an SCP or org policy that blocks public Lambda function URLs, or requires
WAF / API Gateway in front of anything internet-facing?**

*Why it matters*: it is the difference between one Lambda resource and a multi-resource front door
with a WAF web ACL. Also: an unauthenticated-at-the-edge endpoint may need a security review even
though the handler authenticates every request.

### 4. Do we get a stable hostname, or is a raw AWS URL acceptable?

A Lambda function URL looks like `https://<id>.lambda-url.us-east-1.on.aws`. A stable name would
be something like `teams-bot.aaii.cucloud.net`.

- Who owns that DNS zone, and can records be created from this AWS account (Route 53), or is it
  delegated elsewhere?
- Is there an ACM certificate path, or a wildcard already issued?

*Why it matters*: the messaging endpoint URL gets written into the Azure Bot Service resource **by
hand or by Terraform**. If the URL changes every time the stack is recreated, that handshake has
to be redone each time. A stable custom domain makes it a one-time configuration. This is the
kind of thing that is cheap to set up now and expensive to retrofit.

### 5. Where does the answer come back from — and may the front door be thin?

Confirm the intended split: a small AWS front door validates the inbound JWT, returns `200 OK`
immediately, and hands off; AgentCore does the thinking; the reply goes out as a **separate**
outbound POST to `{serviceUrl}/v3/conversations/...`.

*Why it matters*: Teams retries if the endpoint is slow or returns anything but `200 OK`, and
users see retries as duplicate messages. Agent inference is not reliably fast. If Dan expects a
single synchronous request/response, that expectation needs correcting now rather than at demo
time.

---

## Tier 2 — AWS account readiness

### 6. Which AWS account, and is it bootstrapped?

- Account ID and alias?
- Has `bootstrap/account-bootstrap.yml` been deployed to it?
- **Has the CodeConnections handshake been completed in the browser?** Until a human finishes it,
  the Source stage fails with a permissions error that never mentions the handshake.

### 7. Is `bedrock-agentcore` permitted, and are quotas sufficient?

Any SCP denying new or unfamiliar services? AgentCore is recent enough that deny-lists sometimes
lag behind. Any service quotas we should request an increase for ahead of the workshop?

### 8. Which Bedrock models are access-enabled in `us-east-1` in that account?

Bedrock requires per-model access grants. We need at minimum an inference model, and an embeddings
model if a Knowledge Base is in scope.

*Why it matters*: model access is a console action with a lead time. Discovering it is missing
during the workshop is avoidable.

### 9. Confirm `us-east-1`, and confirm there is no data-residency constraint

`CLAUDE.md` fixes the region at `us-east-1`. Any Cornell requirement that would conflict —
particularly if course content or student messages are involved?

### 10. Network egress: public, or VPC with NAT?

The bot must reach `login.botframework.com` (JWKS), `login.microsoftonline.com` (token), and
`*.smba.trafficmanager.net` (the reply `serviceUrl`). AgentCore's default network mode is public
internet, and Lambda outside a VPC has internet access by default.

Is that acceptable, or must compute sit in a VPC? If a VPC is required: is there an existing VPC
with NAT and private subnets we should use, or does this blueprint create one?

*Why it matters*: a VPC requirement adds subnets, route tables, a NAT gateway (which has a
standing hourly cost), security groups, and VPC endpoints. It roughly doubles the template and is
the single largest swing in scope on this list.

### 11. Logging and observability

- Default CloudWatch log retention, and is there a central log destination or subscription filter
  we must attach to?
- **May we log Teams message bodies?** See question 15.
- Is there an existing dashboard or alarm convention these resources should feed?

### 12. Cost guardrails on the shared account

Is there a budget or billing alarm? This would be the first thing deployed here that costs money
per request rather than per month — Bedrock inference and AgentCore both bill on use, and the
account is shared by everyone at the workshop.

### 13. Is `cloudformation-deploy-role` staying on `AdministratorAccess`?

Reverse Engineering flagged this. `BuildPipelineRole` narrows what the *pipeline* can target, but
the role it assumes is unbounded. Worth an explicit decision before anything long-lived is
deployed, and worth knowing whether an SCP above it will surprise us on a new service.

---

## Tier 3 — The Microsoft half

This is the part with no home in the current repository. `CLAUDE.md` designates
Terraform-from-CodeBuild as the mechanism for non-AWS resources, and records that it is
deliberately not built yet.

### 14. Who holds **Contributor on the Azure resource group**?

Creating the `Microsoft.BotService/botServices` resource requires Azure RBAC Contributor on the
target resource group. This is a **separate privilege** from Entra app registration and from Teams
admin — the research confirmed all three are independent axes, and that any tenant member can
already create app registrations. This one is the bottleneck. Is it you?

### 15. Which tenant — dev or the real Cornell tenant?

The research was done in a dev tenant. Do we build and demo in dev first, then promote? Or
straight into the production tenant?

*Related, and important*: AgentCore's JWT inbound auth writes some JWT claims **including
Subject** to CloudTrail, and AWS explicitly warns against PII in that field. If the bot ends up
handling real student data, what may and may not be used as a user identifier, and what may be
logged, needs a position — potentially a FERPA question rather than a technical one.

### 16. Single-tenant app with a client secret, or user-assigned managed identity?

Multi-tenant bot creation was **retired after 2025-07-31**, so multi-tenant is not an option.
That leaves single-tenant with a client secret, or a user-assigned managed identity.

- Is there a Cornell policy against long-lived client secrets?
- If a secret: it goes in AWS Secrets Manager (hard constraint). Is there an existing path prefix
  convention, a KMS key to use, and an expected rotation cadence? Entra secrets expire — who gets
  the reminder?

### 17. Who is the Teams admin, and what is the lead time on org publish?

**Sideloading a Teams app reaches personal scope only.** Group chat and channel support require
publishing to the organization *with Teams admin approval*. That is a hard prerequisite, not an
optimization.

- Who approves it?
- How long does approval typically take?
- Can availability be scoped to a specific group during testing?

*Why it matters*: if the goal includes channel or group-chat use and approval takes a week, that
is a schedule fact we need today, not later.

### 18. Terraform from CodeBuild — acceptable now, or manual runbook for v1?

If Terraform: where does the Azure credential live, and is OIDC federation from AWS to Entra
available, or is it a stored secret? Note the org allowed-actions policy permits
`hashicorp/setup-terraform@*`, so the GitHub Actions side is already unblocked.

If manual: fine for v1, but it means a documented runbook and a click-ops exception recorded
explicitly rather than assumed.

### 19. Bot Framework SDK v4 support ended 2025-12-31. Any position?

The successor is the Microsoft 365 Agents SDK. The alternative is to skip the SDK entirely and
validate the JWT ourselves — the validation rules are fully documented in our research, and the
handler only needs to do JWT validation plus two HTTP calls. Fewer dependencies, no deprecated
SDK, more code we own.

---

## Tier 4 — Process and ownership

### 20. May we deploy to `main`, or stand up a parallel environment first?

Every merge to `main` deploys to the shared account. A parallel environment is available, but
`Environment` is capped at `[a-z0-9]{1,4}` — four characters, no hyphens — because it is
interpolated into stack names and into the IAM prefix the deploy role is scoped to. So the branch
would need a name like `tbot`.

### 21. Who reviews the PRs?

Nobody can approve their own, and branch protection requires one human approval. During a
two-day workshop that is worth arranging in advance.

### 22. Tagging: who is `cornell:owner`, and what is the `cornell:deployment-id` scheme?

All four `cornell:*` tags are mandatory on every resource and feed inventory and the cost
dashboard. `cornell:owner` and `cornell:deployment-id` arrive as stack parameters, so the
pipeline has to pass real values. What are they?

---

## Quick reference — the five that block everything else

If the conversation is short, these are the ones to get:

1. **Does an AgentCore runtime already exist, or are we deploying one?** (Q1)
2. **Public Lambda function URL — allowed, or must it be API Gateway/WAF?** (Q3)
3. **Who has Azure Contributor on the resource group?** (Q14)
4. **Who is the Teams admin, and how long does org publish take?** (Q17)
5. **VPC required, or is public-network compute fine?** (Q10)
