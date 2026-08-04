# Requirements Clarification Questions, `course-chatbot` blueprint (Track C)

Please answer each question by filling in the letter choice after the `[Answer]:` tag.
If none of the options match, choose the last option (Other) and describe your
preference. Answer in-line in this document. When every question has an answer we
lock the shape of the blueprint and Fermin starts building.

**Answers drafted 2026-08-04 morning (Pete) for track ratification.** Each answer is
tagged either **[settled externally]**, meaning something merged to `main` overnight
already decided it and we are recording the decision rather than making it, or
**[track judgment]**, meaning it is genuinely Track C's call and Fermin or the track
should overrule freely. Six of ten are settled externally.

**Path choice, resolved.** This file previously flagged that we placed `aidlc-docs/`
under `blueprints/course-chatbot/` rather than at the workspace root, and offered to
move. **Keep it here.** Track A independently made the same choice for their component
(`builder-mcp/aidlc-docs/`), so per-component placement is now the de facto convention
at two of three tracks; only Track E's `dashboard` branch uses the root. No move
needed unless facilitators ask.

**Established before writing this**, so we do not re-argue:

- Track C's deliverable is the `blueprints/course-chatbot/` blueprint, not a
  generic bot-building workflow. Track A's builder MCP creates deployment repos
  from this blueprint.
- Workflow shape: one bot registration, one Azure Bot Service, one messaging
  endpoint (Lambda). End users install the Teams app into their own Teams channel
  and talk to it in-channel.
- Cornell has an Azure subscription (confirmed 2026-08-03 approx 14:00 ET).
  Specific subscription ID, RBAC role, resource group, and region still to be
  pinned down before Fermin writes Terraform.

**Added 2026-08-04, and it changes the Azure plan:** the repo's own `CLAUDE.md` now
states that the `azurerm` provider **will not work yet**. It needs a subscription
*plus* Azure RBAC on that subscription, and Global Admin is a directory role only, so
it grants nothing there. The `azuread` provider does work, which is what Track 0's
`entra-probe` blueprint proves. So "Cornell has a subscription" was necessary but not
sufficient: **the RBAC role is the live blocker for anything creating a Bot Service.**
Entra app registration is unblocked; Bot Service creation is not.

## Question 1, demo scope

The blueprint deploys ONE bot instance for the Tuesday demo. What is the bot
grounded in?

A) One course's syllabus and a small handful of readings. Small doc set, easy to
   verify grounding by inspection.

B) A department-level generic doc set that mixes multiple courses. Tests retrieval
   quality but larger surface area for demo failures.

C) Placeholder / synthetic content only, so the demo shows the pipeline end-to-end
   without requiring real academic content or approvals.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A, with one constraint: use a syllabus that is already publicly posted
on a Cornell course site.** [track judgment]

Rationale. A public syllabus gives us real content with zero approval dependency,
which is the only reason C looked attractive. Grounding stays verifiable by
inspection, and a demo that answers a real question about a real course reads
completely differently to a provost-level audience than one answering about
synthetic content. B is out on time: more documents is more retrieval surface to
debug and we have roughly six hours.

**Hard constraint from Track B, and it dictates the mechanics:** SharePoint ingestion
into the knowledge base **does not work and never has.** The last five ingestion jobs
failed with zero documents scanned, on missing Microsoft Graph scopes, and unpinning
it is an Entra admin consent task rather than a code task (Track B retracted their
earlier "working" claim in PR #18). The **S3 managed connector does work.** So the
documents go into the `aidlc-kb-ingestion-*` S3 bucket by hand. Nothing about this
demo can depend on SharePoint.

Note also that CloudFormation never triggers ingestion, so someone has to kick the
ingestion job after the documents land.

## Question 2, retrieval interface with Track B

Track B tunes the Bedrock Knowledge Base. Track C's Lambda has to call it. Which
shape?

A) Direct Bedrock KB call from the Lambda using IAM, `Retrieve` or
   `RetrieveAndGenerate`. Simplest. Couples our Lambda's IAM to B's KB ID.

B) Track B publishes a Lambda (or API Gateway endpoint) that Track C invokes.
   Decouples but adds a hop and a "how do we auth between them" question.

C) Async: Track B produces a periodic snapshot to S3 or DynamoDB, Track C reads
   from there. Loosest coupling, stalest answers.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A. Already built and deployed by Track B; we are ratifying, not
deciding.** [settled externally]

Track B merged PR #13 overnight and implemented exactly option A. Re-opening this
costs hours we do not have, and A was the cheapest option anyway. The published
contract:

- Call `bedrock-agent-runtime` `Retrieve` / `RetrieveAndGenerate` **directly**. There
  is no Lambda, no API Gateway, and no HTTP endpoint in front of the knowledge base.
- Resolve the knowledge base ID from SSM at `/aidlc/main/knowledgebase/knowledge-base-id`.
- Attach the IAM managed policy whose ARN is published at
  `/aidlc/main/knowledgebase/retrieval-policy-arn` to our Lambda's execution role.
  Track B wrote that policy for exactly this purpose, so we do not hand-roll Bedrock
  permissions.
- Also available if useful: `data-source-id`, `ingestion-bucket`, `deployed-commit`,
  `last-ingestion-result`.

Track B **explicitly rejected** CloudFormation `Export` for this handoff, to avoid
lifecycle coupling between their stack and ours. We should honor that rather than
asking them to add one: it is the reason Question 5 below resolves to reading SSM at
runtime instead of taking the KB ID as a template parameter.

## Question 3, agent framework (Strands)

The brief names Amazon Strands as the agent framework. Where does the agent run?

A) Inside the Bot Framework Lambda handler. One Lambda handles Teams auth, agent
   execution, and the KB call. Simplest cold-start path.

B) Behind a second Lambda that the Bot Framework handler invokes. Separates the
   "handle the Teams protocol" concern from "run the agent" concern. Easier to
   test and to swap the agent later.

C) On AWS Bedrock Agents (managed) instead of Strands. Departs from the brief;
   only pick this if the room re-decides.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A for this week.** [track judgment]

B is the better long-term shape and we should say so in the blueprint README, but it
doubles the deploy surface and the IAM wiring for a separation we will not exercise
by Tuesday. A is reversible later; shipping nothing is not.

**Known risk with A, which we should mitigate rather than discover on stage.** Bot
Framework expects the bot to return HTTP 200 to the incoming activity POST promptly.
With one Lambda doing Teams request validation, Strands agent execution, and the KB
call synchronously, a slow first token or a cold start can leave the Teams client
waiting. Two cheap mitigations, both worth doing:

1. Send a typing indicator activity before starting agent work, so the channel shows
   activity while we think.
2. Keep the document set small (Question 1 already does this) and cap the agent to a
   single retrieval round trip.

If we still see timeouts in rehearsal, the escape hatch is to return 200 immediately
and reply with a proactive message, which is the standard Bot Framework pattern for
slow work. Do not build that today, but know it exists.

## Question 4, grounding behavior

When the KB has no relevant chunks for the user's question, the bot should...

A) Say "I don't have information on that" and stop.

B) Answer from the base model but explicitly say the answer is not grounded.

C) Try to reformulate and re-query, then fall back to (A) on the second miss.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A, and this one is not close.** [track judgment]

The Tuesday audience is provost-level. The single worst outcome available to this
demo is the bot confidently producing an ungrounded answer about a real Cornell
course, and option B is a design that invites exactly that while relying on a
disclaimer nobody reads to contain it. "I don't have information on that" is a
*good* demo moment: it shows the guardrail working, which is the thing an
administrator actually wants to see.

C also costs a second round trip against the latency budget in Question 3, for a
marginal recall gain on a document set we deliberately kept small.

## Question 5, blueprint parameters for Track A

Track A's builder MCP creates a deployment repo from this blueprint. What
parameters does our blueprint accept, versus what is hardcoded in the template?

A) Only `Owner` and `DeploymentId`. Everything else (KB id, bot display name,
   region) hardcoded per blueprint.

B) `Owner`, `DeploymentId`, `KBIndexId` (points at B's KB), and `BotDisplayName`.
   Enough to reuse the blueprint across knowledge bases and courses.

C) Above plus per-tenant Teams manifest parameters if any (tenant ID, admin
   email). Only relevant if we ever want the SAME blueprint to deploy for
   different Cornell tenants, which we probably do not this week.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **X. Take `Owner`, `DeploymentId`, and `BotDisplayName` as parameters,
and resolve the knowledge base ID from SSM at runtime rather than as a parameter.**
[settled externally, and it avoids a live defect]

This is B minus `KBIndexId`. Two independent reasons, and the first is the load-bearing
one:

1. **A declared `KBIndexId` input would silently arrive empty.** Track A's
   `deployment_create` only passes `Application`, `Environment`, `Owner`, and the
   manifest's `pipeline_parameters` through to the template. Values declared under
   `inputs` in `blueprint.yaml` are collected from the builder and then **never reach
   the template**. This is a known open defect, documented as finding 2 in PR #15
   against `tiny-chatbot`'s `deployment_name`. It fails silently: green plan, wrong
   stack. If we declare `KBIndexId` as an input we will spend rehearsal debugging an
   empty parameter.
2. **Track B designed SSM as the handoff and rejected CFN `Export` deliberately** (see
   Question 2). Reading `/aidlc/main/knowledgebase/knowledge-base-id` at Lambda
   startup uses their contract as intended, avoids the parameter path entirely, and
   means a knowledge base rebuild does not require redeploying our stack.

Mechanically, in `blueprint.yaml`: `Owner` is injected by Track A automatically, so
declare `deployment_name` and `bot_display_name` under `inputs`, and put anything the
pipeline must resolve (`SourceCommitId`, `ContainerImageUri`) under
`pipeline_parameters`. **Until defect 2 is fixed, treat any `inputs` entry the
template genuinely needs as broken** and either move it to `pipeline_parameters` or
read it at runtime. Worth asking Track A directly whether they intend to fix it today.

C is correctly identified as out of scope: one tenant this week.

Also required by the repo's enforced conventions, so not optional: tag every resource
with all four of `cornell:owner`, `cornell:blueprint`, `cornell:blueprint-version`,
and `cornell:deployment-id`. Untagged resources are invisible to Track E's dashboard
and therefore invisible in demo beat 7.

## Question 6, Teams app distribution

How does the Teams manifest reach end users for the Tuesday demo?

A) Sideload only. Manifest is a build artifact from the pipeline; installation
   is a hand step by whoever demos. Fastest, no Cornell Teams admin dependency.

B) Attempt Cornell Teams admin catalog submission this week. Higher risk of
   missing the Tuesday deadline, but closer to the target-state builder story.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A.** [track judgment, but effectively forced by the calendar]

Catalog submission is an approval queue owned by people outside this room, and we are
asking for a decision on Monday afternoon for a Tuesday 2:00 PM demo. B is not a
schedule, it is a hope. Sideload, and name catalog submission as the documented next
step in the blueprint README so the target-state story is still legible to the
audience without our depending on it.

Sideloading itself requires that Cornell's Teams admin policy permit custom app
upload for the demo account. **Verify that before Tuesday morning**, because if it is
disabled we have neither path and would need to fall back to the Bot Framework
Emulator or Direct Line for the demo.

## Question 7, verify step

Every artifact this room builds gets a verify step that runs on its own.
"Blueprint deploys cleanly" is not the same as "blueprint works." What does the
built-in verify check?

A) Post-deploy: query Bedrock KB with a canned question, check the Bot Service
   `messagingEndpoint` matches Lambda's URL, check the Teams channel is enabled.
   No actual Teams message sent.

B) Above, plus a synthetic Teams-message-to-Lambda test using the Bot Framework
   Direct Line channel or a Bot Framework Emulator test harness.

C) Above, plus a manual "poke the bot in a Teams channel and verify a real
   answer" checklist for the demo runner.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **B as the automated verify step, with C's checklist kept separately as a
demo-runner pre-flight rather than as part of verify.** [track judgment]

Reasoning. A does not actually establish that the bot answers: it confirms three
pieces of configuration agree with each other, which is the "deploys cleanly"
standard this question is explicitly trying to beat. B is the weakest option that
proves an end-to-end answer came back.

Of B's two suggested mechanisms, **use Direct Line, not the Emulator.** The Bot
Framework Emulator is an interactive desktop tool and cannot run unattended in the
pipeline, so it fails the "runs on its own" requirement in the question's own preamble.

C's manual poke is genuinely valuable but it is not a verify step, because it does not
run on its own and cannot gate a deploy. Keep it as a rehearsal checklist.

Design constraints on the verifier itself, worth writing into the blueprint now
rather than retrofitting:

- It runs as a **separate step in a fresh context**, not as a self-check inside the
  thing it verifies.
- It **verifies by executing**: send the synthetic activity, assert on the response
  body, resolve the SSM parameters, probe the live endpoint. A verifier that re-reads
  the template only confirms the author's intent.
- It **flags without fixing**, returning a verdict so the decision stays with the
  caller.

**Cost to flag:** enabling Direct Line means a Direct Line channel plus its key. Per
the repo's new CloudFormation rule, that secret's *resource* goes in the template
using `GenerateSecretString` and its *value* is injected once by CLI with
`put-secret-value`. Do **not** use `SecretString`: `PipelineDeploy` redeploys the
pipeline stack on every merge and would reset the live key back to the placeholder.

## Question 8, bot identity credential (Azure side)

The Lambda validates incoming Bot Framework requests using the bot's Microsoft
App ID and a credential. Which credential?

A) Federated identity credential from AWS to Entra. No secret in AWS Secrets
   Manager, no secret to rotate. Requires Cornell tenant policy to permit
   cross-cloud federation.

B) Client secret in AWS Secrets Manager. Standard pattern, works regardless of
   tenant policy, but a secret exists that has to be rotated.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **B.** [track judgment, constrained by an unknown we cannot resolve in
time]

A is the better security posture and we should record it as the target state. But it
depends on Cornell tenant policy permitting cross-cloud federation, and that is a
question we would have to ask an Entra admin and then wait on. We already have one
Entra admin dependency on the critical path (Track B's SharePoint scopes, unresolved
since yesterday) and that is the one that shows what waiting costs. B works
regardless of tenant policy.

**Implementation is not free, and the rule is new as of this morning.** The secret's
resource is declared in CloudFormation with `GenerateSecretString`; the real value is
injected once out of band via `put-secret-value`. Never `SecretString`, for the
`PipelineDeploy` reset reason described in Question 7. Getting this wrong produces a
bot that works until the next unrelated merge to `main`, which is the worst possible
time to find out.

## Question 9, security extensions

Should the AI-DLC security baseline rules be enforced for this blueprint?

A) Yes, enforce as blocking constraints. Recommended for anything that touches
   real user data, which a course chatbot may.

B) No, skip. Reasonable for a two-day workshop demo with synthetic content only.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A, with an explicit definition of what "enforce" means by Tuesday: every
finding is recorded and has a named owner, not every finding is closed.** [track
judgment, and there is a room-level question underneath it]

B's premise does not hold for us. Option B is scoped to "synthetic content only," and
Question 1 chose real, if public, course content. More importantly, Teams hands the
bot a user identity in every incoming message payload, so this blueprint handles
personal data whether or not the documents are sensitive.

**What Track A's experience tells us to expect, and it is worth the room hearing.**
Track A enforced this baseline and their current verdict is still **NON-COMPLIANT**,
with finding F2 open (no object-level authorization: any token holder can act as any
NetID) and F7 and F8 deferred. Their extension treats deferred items as blocking until
the owning track closes them. So if Track C also enforces and also does not finish,
the demo has two tracks carrying a red security verdict.

That is an argument for naming the standard now rather than for skipping it. A
recorded, owned, triaged finding is a defensible story to a provost-level audience and
is genuinely what beat 4's target state describes. An unrecorded one is not. But
somebody should raise the two-red-verdicts question with the facilitators today rather
than letting it surface during rehearsal.

## Question 10, resiliency extensions

Should the AI-DLC resiliency baseline rules be applied?

A) Yes, as design-time guidance. Recommended for anything that will outlive the
   workshop.

B) No, skip. Reasonable for a workshop demo.

X) Other (please describe after `[Answer]:` below)

`[Answer]:` **A.** [track judgment, low cost]

The question says design-time guidance, not a blocking gate, so the cost is reading it
and writing down what it changes. Track A ran it and produced
`construction/resiliency-assessment.md`, which is a real artifact and reasonable demo
material. Cheap, and it is the difference between a demo and something a unit could
adopt.

---

## Open items these answers create

Not questions for the track, but things that now need an owner and a name against
them. Listed here so they do not evaporate.

| Item | Blocks | Who to ask |
|---|---|---|
| Azure RBAC role on the subscription. `Microsoft.BotService/botServices/write` specifically. Global Admin does not grant it. | All Bot Service creation. Hard blocker for the Azure half. | Track 0 / Marty |
| Whether Track A intends to fix the `inputs`-never-reach-template defect today | Whether Question 5's SSM workaround is permanent or temporary | Track A (Tim / Jai) |
| Teams admin policy permits custom app sideload for the demo account | Question 6's only remaining path | Cornell Teams admin, via facilitators |
| Someone loads the public syllabus into the S3 ingestion bucket and triggers an ingestion job. CloudFormation will not do it. | Question 1's grounding | Track C, coordinate with Track B |
| Direct Line channel enabled plus its key seeded via `put-secret-value` | Question 7's automated verify | Track C, needs the Azure RBAC above |
| Two tracks potentially carrying NON-COMPLIANT security verdicts into the demo | Nothing technically; it is a narrative risk for beat 4 | Facilitators, today |
