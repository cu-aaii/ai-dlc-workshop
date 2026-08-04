# Unit of Work Plan — `teams-bot`

**Created**: 2026-08-04
**Stage**: INCEPTION - Units Generation (Part 1: Planning)
**Status**: ✅ **All questions answered.** Awaiting approval to proceed to Part 2 (generation).

## Answers received 2026-08-04

| Q | Answer | Source |
| --- | --- | --- |
| **Q7** | **Mob-style, whole cross-functional team** — per the participant brief | explicit (brief) |
| **Q4** | **One PR** | explicit |
| **Q9b** | **Everything in the dev environment** — single tenant, single identity | explicit |
| **Q8** | **The team owns U0** — access is available because it is a dev env | explicit |
| Q1 | Risk-retirement ordering | default |
| Q2 | 10 units, about right | default |
| Q3 | Hardening split — `uv.lock` + retention inline, alarm + scanning as a unit | default |
| Q5 | Yes, a partially-working bot on the shared account between units is fine | default |
| Q6 | See the mob revision below — supersedes the original parallel/serial choice | derived |
| Q9 | A human runs the script locally, completing one device-code prompt | default |
| Q10 | Client secret for the workshop; certificate noted as better long-term | default |
| Q11 | Script in `blueprints/teams-bot/scripts/`, run by a person, not CodeBuild | default |
| Q12 | One blueprint, documented as two bounded contexts | default |
| Q13 | Layout as proposed | default |
| Q14 | Manifest at `blueprints/teams-bot/teams-app/manifest.json` in git | default |

---

## Two revisions forced by those answers

### Revision 1 — the parallelism in the table below is wrong. Execution is serial.

The brief is explicit: *"the methodology only works when the entire cross-functional team is in the room. Mob
Elaboration and Mob Construction depend on every perspective being present."* So the team works **one unit at a
time, together** — not on parallel tracks. **Every "Parallel? Yes" in the unit table is withdrawn.**

Three consequences, and the first is the important one:

1. **Ordering matters more, not less.** With serial execution there is no track quietly de-risking something in
   the background, so putting the unproven build path first is now the only thing that de-risks it at all.
   The risk-retirement principle gets *stronger*, not weaker.
2. **Each unit should end in something a non-engineer can evaluate.** The team includes product owners, IT
   service management, security, analysts, designers and business stakeholders. A unit whose only output is "a
   lint rule passes" cannot be validated by a mob. Assessed against that bar:

   | Unit | Demoable to a non-engineer? |
   | --- | --- |
   | U1 build capability | weakly — an image exists in ECR |
   | U2 blueprint skeleton | weakly — a URL returns `200` |
   | U3 inbound trust | poorly — "forged requests are rejected" is hard to show |
   | **U5 first reply** | **yes — the bot says hello in Teams** |
   | U6 agent runtime | moderately — a JSON payload returns a streamed answer |
   | **U7 streaming delivery** | **yes — text appears progressively in Teams** |

   **U5 and U7 are the natural mob checkpoints** — the two "bolts" that end in something the whole room can
   judge. U1–U3 are best treated as one continuous stretch of plumbing rather than three separate
   celebrations.
3. **U0 is the one honest exception.** It is non-AWS, needs Azure and Teams admin credentials, and cannot
   usefully be mobbed. Expect one person to run that script while the room works on AWS.

### Revision 2 — one PR means the build path is not exercised until merge

This is a real consequence worth stating plainly, not a reason to change the decision.

`Environment` is the branch name and the Source stage tracks `BranchName: !Ref Environment` with
`Environment=main`. **So the pipeline only runs on `main`. A PR branch does not trigger it.** With one PR, the
never-executed container build path is first exercised **on merge** — and a failure there turns `main` red in a
repository every other workshop team is also merging into.

**Two things shrink that risk without changing the decision:**

- **Validate the Dockerfile locally first** with `docker buildx build --platform linux/arm64`. That proves the
  image builds for ARM64 and satisfies the AgentCore contract (`/ping`, `/invocations`, port 8080) with no AWS
  involvement at all. It is most of the risk.
- **Expect a fix-up merge and plan for it.** The parts local building cannot prove are the pipeline wiring and
  the `CONTAINER_DIGEST` export. Treating one corrective merge as likely is more useful than being surprised
  by it.

*(Invoking `ContainerBuildProject` directly with `aws codebuild start-build` would test the buildspec without
merging, but the project is declared with `Source: Type: CODEPIPELINE`, so it needs source overrides and
CodeBuild-side repository access that may not be configured. Mentioned as a possibility, not a recommendation
— I have not verified it works here.)*

### Consequence for the unit artifacts

With mob-style execution and a single PR, **units are sequencing and review guidance, not PR boundaries.** The
artifacts will describe them as an ordered work breakdown with explicit completion criteria, which is what is
useful to a mob, rather than as independently shippable increments.

---

---

## Plan

- [x] Generate `aidlc-docs/inception/application-design/unit-of-work.md` — unit definitions and
      responsibilities, including code organisation strategy
- [x] Generate `aidlc-docs/inception/application-design/unit-of-work-dependency.md` — dependency matrix
- [x] Generate `aidlc-docs/inception/application-design/unit-of-work-story-map.md` — **requirement**-to-unit map
      (see the note below)
- [x] Validate unit boundaries and dependencies
- [x] Ensure every functional requirement is assigned to a unit
- [x] Verify Security Baseline compliance across the decomposition before the completion message

**Note on the story map.** User Stories was skipped, so no stories exist. Rather than fabricate them or drop
the artifact, `unit-of-work-story-map.md` will map the **33 functional requirements** from `requirements.md` to
units. That preserves the artifact's purpose — proving nothing is orphaned — using the material that actually
exists.

---

## Decomposition principle proposed

Units are ordered so that **each one retires the largest remaining risk**, not so that the architecture is
built bottom-up. Three consequences:

1. The **never-executed container build path** is proven first, with a throwaway container — before any real
   logic depends on it.
2. The **first visible bot behaviour** arrives early and needs neither the agent nor the gateway.
3. The **agent is built and tested with no Teams involvement at all**, which is the payoff of the
   channel-agnostic decision.

---

## Proposed units

Concrete enough to react to. Adjust rather than invent.

| Unit | Name | Delivers | Proves | Parallel? |
| --- | --- | --- | --- | --- |
| **U0** | Microsoft identity chain | Entra app + secret, Azure Bot Service, MsTeams channel, manifest in git, published to the dev tenant catalog | The bot exists and has somewhere to point | **Yes — from the start**, different skills, no AWS dependency except the endpoint URL |
| **U1** | Build capability | `pipeline.yml` ARM64 + Build stage; a throwaway ARM64 container | The buildspec contract, `CONTAINER_DIGEST` export, ECR push, ARM64 | No — blocks U2 |
| **U2** | Blueprint skeleton | `teams-bot.yml` with Lambda + function URL + roles + tags + outputs; `stacks.yml` + pipeline action | A public URL exists, `tools/check` passes, tags land | No — needs U1 |
| **U3** | Inbound trust | `JwtValidator`, `ActivityNormalizer`, `Logger`, `ConfigProvider`; FrontDoor validates and acks | **Forged requests are rejected**; the `serviceurl` negative test passes | No — needs U2 |
| **U4** | Idempotency + handoff | DynamoDB table, `IdempotencyStore`, async invoke, Worker skeleton | The same activity twice produces one unit of work | No — needs U3 |
| **U5** | First reply | `TokenProvider`, `BotFrameworkClient`, `SingleReplyDelivery`, `conversationUpdate` greeting | **A human sees the bot say hello.** No agent, no gateway | No — needs U4 + U0 |
| **U6** | Agent runtime | Real agent container, `GatewayClient`, AgentCore Runtime + Endpoint + Memory | A JSON payload gets a streamed answer — **tested without Teams** | **Yes — parallel with U3-U5** |
| **U7** | Streaming delivery | `StreamingDelivery`, `DeliveryDispatcher`, Worker wires agent → delivery | Text appears progressively in a personal chat | No — needs U5 + U6 |
| **U8** | Scope expansion | Manifest `groupChat` + `team` scopes, `supportsChannelFeatures`, both conversation-id formats | An `@mention` in a channel gets a reply | No — needs U7 |
| **U9** | Hardening | 90-day retention, validation-failure alarm, reserved concurrency, `uv.lock`, dependency scanning | Security Baseline satisfied in the deployed artifact | **Yes — parallel with U7-U8** |

### Why U5 is placed where it is

U5 is the first unit a non-engineer can see working, and it deliberately requires **neither the agent nor the
gateway**. A `conversationUpdate` greeting is a configured constant. If the workshop runs short, U0–U5 is a
demonstrable Teams bot deployed through the governed pipeline — which proves the *platform* thesis even without
a model in the loop.

### U0 is a script, not a runbook — updated 2026-08-04

Two research documents reshaped this unit, the second by **live testing** what the first could only reason
about. They have since been consolidated into one:
`docs/teams-chatbot-docs/Teams Admin CLI Automation - Findings 2026-08-03.md`.

**Everything in U0 is scriptable.** The only human step is **one device-code browser prompt**:

| Step | Mechanism | Confirmed |
| --- | --- | --- |
| Entra app + secret | `az ad app create` / Graph | documented |
| **Service principal** | **`az ad sp create`** | documented — **separate mandatory step, see gotcha 1** |
| Azure Bot Service + MsTeams channel | `az bot create`, `az bot msteams create` | read-tested |
| Messaging endpoint | `az bot update --endpoint` | — |
| Manifest + icons + zip | plain files in git | **live, zero portal use** |
| Publish to catalog | Graph `POST /appCatalogs/teamsApps` | **live, `201`** |
| Scope to an Entra group | `Update-M365TeamsApp -Groups` | **live, round trip** |

**Six gotchas worth building into the script from the start**, all discovered the hard way in that document:

1. **`az ad app create` is not enough — `az ad sp create` is a separate mandatory step.** Registering the
   application and creating its service principal are two distinct directory objects. The Azure Portal does
   both when you click through the blade, so anyone who has only done this in the GUI will assume one command
   suffices. Omit it and everything *looks* fine — the app exists, the secret is issued, `az bot create`
   accepts the app ID — and the failure appears much later at the bot's **first outbound token request**, with
   nothing pointing back at the missing object. Put both calls in the script from the first commit; this is the
   single most likely way to lose an afternoon in U0.
2. **`az rest` cannot do the catalog calls.** It authenticates as the "Azure CLI" first-party app, whose scope
   set is fixed by Microsoft and excludes `AppCatalog.*`. This is a **client-app** limitation, not a privilege
   gap — a global admin still gets `403`. Use the **Microsoft Graph Command Line Tools** public client
   (`14d82eec-204b-4c2f-b7e8-296a70dab67e`) with device-code flow, then plain `curl`.
3. **`Get`/`Update-M365TeamsApp -Id` wants the *catalog* id, not the manifest id.** The manifest id fails with
   `NotAllowed: This app is not available for admin management`.
4. **The Teams PowerShell docs' parameter metadata is wrong.** `-AppInstallType` and friends are a *separate*
   parameter set; passing them alongside `-AppAssignmentType`/`-Groups` throws. Omit them when only touching
   availability.
5. **The zip needs `manifest.json` + `color.png` + `outline.png` at the zip root** — no subfolder.
6. **Verify any first-party client ID against the directory before building on it.** The Teams PowerShell
   client is `1fec8e78-bce4-4aaf-ab1b-5451cc387264`, verified empirically. A GUID that web search offers for
   the same purpose, `5170baac-d33f-4ab5-bc04-6ac2a602c700`, **does not exist in the tenant at all** and was
   most likely fabricated. Client IDs are exactly the kind of value that looks authoritative and is not.

**The one human step is confirmed permanent, which is worth knowing before designing the script.** Do not
build U0 expecting to remove the device-code prompt later. Availability scoping has no unattended path by any
route: app-only 401s, Teams Administrator escalation changes nothing, and `Connect-MicrosoftTeams
-AccessTokens` fails structurally because the module needs a third resource token and the parameter accepts
exactly two. So the script should be written to make the one interactive login **obvious and pleasant** —
prompt clearly, fail clearly if the token has expired mid-run, and be safely re-runnable from any point —
rather than written as a temporary shape awaiting full automation. Idempotency matters more than it would if
this were headed for CI.

**One capability the research settled that U0 does not need**, recorded so nobody re-tests it: Setup Policies
(the "Upload custom apps" sideloading grant) **are** app-only automatable, confirmed live. It is irrelevant
here because publishing to the org catalog makes sideloading unnecessary. Its value is as evidence — it proves
the wall is endpoint-specific rather than module-wide, which is what makes the remaining `New-TeamsApp`
question worth an hour.

**Also confirmed live**: tenant app settings show
`isUserPersonalScopeResourceSpecificConsentEnabled: true`, which is partial evidence for admin question 13 —
RSC is not switched off tenant-wide.

---

# Questions

## Section 1 — Story Grouping and Unit Boundaries

### Q1. Is the risk-retirement ordering right, or would you rather build architecturally?

A) **Risk-retirement order as proposed** — prove the build path first, visible value early, agent in parallel
B) **Architectural order** — build front door, then worker, then agent, in the order requests flow
C) **Visible-value-first** — reorder so a greeting appears as early as possible, accepting more rework

[Answer]:

**Recommendation: A.** The two things most likely to consume a day unexpectedly are the unproven build path and
the Microsoft chain, and A starts both immediately.

### Q2. Are the unit boundaries the right size?

Each unit above is intended as a "bolt" — hours, not days, ending in something demonstrable.

A) **About right** — 10 units
B) **Too granular** — merge some (say U3+U4, U7+U8)
C) **Too coarse** — split further

[Answer]:

### Q3. Should U9 (hardening) be its own unit, or folded into each unit as it goes?

A) **Its own unit at the end** — simpler to track, but risks being cut if time runs out
B) **Folded into each unit** — each unit ships its own retention, alarms, pinning. Slower per unit, nothing gets
dropped
C) **Split** — the cheap parts (`uv.lock`, retention) inline; the rest as a unit

[Answer]:

**Recommendation: C.** `uv.lock` is required by U1 anyway (`uv sync --frozen` will not run without it), and log
retention is one property on a resource. The alarm and dependency scanning are genuinely separate work.

---

## Section 2 — Dependencies and Integration

### Q4. One PR, or one PR per unit?

Q18 settled "a PR pushed to `main`", and Marty said he would review it — singular. But ten units in one PR is a
large review, and `main` deploys to a shared account on every merge.

A) **One PR at the end** — one review, but a big diff and no intermediate deployment feedback
B) **One PR per unit** — small reviews, incremental deployment, tests the pipeline repeatedly. Needs Marty
available ~10 times
C) **A PR per milestone** — say three: U1+U2 (pipeline and skeleton), U3–U5 (a working greeting bot), U6–U9 (the
agent and streaming)

[Answer]:

**Recommendation: C.** It gets deployment feedback early — which matters most for U1, the unproven path — without
asking for ten review cycles in two days. **Worth confirming with Marty**, since it changes what he is agreeing
to review.

### Q5. Is a partially-functional bot deployed to the shared account acceptable between units?

After U2, `main` has a public endpoint that returns `200` to everything and does nothing else.

A) **Yes** — harmless, and getting it deployed early is the point
B) **No** — hold the blueprint out of `stacks.yml` until it does something useful
C) Deploy it, but scope availability in Teams so only the team can reach it

[Answer]:

**Recommendation: A.** An endpoint that validates nothing and stores nothing is not a meaningful attack surface,
and deploying early is exactly how the U1 build-path risk gets retired.

### Q6. Should U6 (agent) really run in parallel, given it needs U1's build path?

U6 needs the container build to work, so it cannot be *deployed* before U1 — but it can be *written and tested
locally* against a container built by hand.

A) **Yes, parallel** — write and test locally, deploy once U1 lands
B) **No, strictly after U1** — simpler to coordinate, less parallelism

[Answer]:

**Recommendation: A**, if more than one person is working. **B** if it is one person, since context-switching
would cost more than the parallelism saves.

---

## Section 3 — Team Alignment and Ownership

### Q7. How many people are working on this, and with what split?

This determines whether the parallelism in the table is real or theoretical.

A) **One person** — parallel tracks are fiction; sequence everything
B) **Two** — one on AWS, one on the Microsoft chain. The natural split, and U0 needs different knowledge
C) **Three or more** — AWS, Microsoft, and agent tracks all genuinely concurrent
D) The whole team, mob-style — AI-DLC "Mob Construction"

[Answer]:

### Q8. Who owns U0 — the Microsoft side?

It needs Azure Contributor on the resource group and Teams admin for the catalog publish. You confirmed you
hold both in the dev tenant.

A) **You** personally
B) **Dan** or another platform person
C) Split — scripted parts by whoever writes the script, the two manual steps by you

[Answer]:

---

## Section 4 — Technical Considerations

### ~~Q9. Is the `New-TeamsApp` spike worth 30 minutes?~~ — **WITHDRAWN 2026-08-04**

**No longer needs asking.** `docs/teams-chatbot-docs/Teams Admin CLI Automation - Findings 2026-08-03.md`
already answers the underlying question by **live test**, and by a different route than the spike proposed.

Catalog publish works via **Graph** `POST /appCatalogs/teamsApps` with a zip body — confirmed `201 Created`
against the dev tenant. Availability scoping to an Entra group works via **`Update-M365TeamsApp -Groups`** —
confirmed with a full add-then-remove round trip. Neither needed the `New-TeamsApp` directory-role theory.

**What the answer actually is**: both steps require a **delegated** token, obtained once through **device-code
flow**, valid ~70 minutes. So the Microsoft side is *fully scripted with one interactive login* — not
unattended, and not GUI clicking either.

### Q9 (replacement). Where does the one interactive login happen?

Given that U0 is now a script needing one device-code consent rather than a click-through runbook:

A) **A human runs the script locally**, completes the device-code prompt in a browser, and the script does the
rest. Honest about the one human step; nothing sensitive enters CI.

B) **CodeBuild runs it**, with a cached refresh token or a service account. **Not recommended** — this
smuggles a user identity into CI, and the Entra research explicitly argues that a no-MFA admin service account
is a *worse* posture than a manual step.

C) A human runs it now; revisit automation only if Microsoft ships application permissions for
`appCatalogs/teamsApps`.

[Answer]:

**Recommendation: A, recorded as C's position long-term.** One browser prompt, once per bot, run by whoever
holds Teams admin — and the script is reviewable in git like everything else.

### Q9b. Which Azure identity does U0's script use? (This one is a real trap)

The findings document surfaced something operationally important: **the existing Bot Service resource and the
Entra app registration live in different tenants**, and this is *by design*, not a misconfiguration.

- the ARM resource + subscription (`JCB IT NSS`) are homed in **Cornell's** tenant
- `properties.msaAppTenantId` on that same resource points at the **dev** tenant, with
  `msaAppType: SingleTenant`
- so `az login --tenant <cornell>` is needed for anything touching **ARM / Bot Service**, and the dev-tenant
  login for anything touching **Entra app registrations, the Teams catalog, or tenant settings**

Two independent tenant references on one resource. `az` holds both logins side by side; switching is
`az account set --subscription …` with no re-login.

A) **Mirror that arrangement** — ARM in Cornell's tenant, bot identity in the dev tenant, as today
B) **Put everything in the dev tenant** for the workshop — one identity, simpler script, but diverges from the
existing working setup
C) Not sure — needs Jason or whoever owns the subscription

[Answer]:

**Recommendation: B if a fresh resource group in the dev tenant is available**, because a single identity makes
the script dramatically simpler and this is a demo. **A** if the intent is to build on the existing PoC
resource. Either way the script must be explicit about which identity each step uses — this is exactly the kind
of thing that produces a baffling `Forbidden` an hour into debugging.

### Q10. Certificate or client secret for the bot's outbound auth?

Raised by the Entra research and recorded as an open choice in `application-design.md` §6a. A certificate
removes risk R-3 (secrets expire silently, months later) at the cost of `TokenProvider` signing a client
assertion instead of sending a secret.

A) **Client secret** — matches the prototype, less code, carries the expiry risk
B) **Certificate** — no expiry surprise, more code in one component
C) Decide during Infrastructure Design

[Answer]:

**Recommendation: C**, leaning A for the workshop. The choice is contained entirely within `TokenProvider`, so
deferring it costs nothing and changing it later touches one component.

### Q11. Scripted Microsoft provisioning — where does the script live and run?

The research recommends a small idempotent script over a Terraform stage: ~4 resources created once, and
`azuread_application_password` would write the secret into Terraform state, colliding with the
Secrets-Manager-only constraint.

A) **A script in `blueprints/teams-bot/scripts/`, run by a human** with `az` locally. Simplest; honest about
being one-time
B) **A script invoked from CodeBuild** — closer to the no-click-ops ideal, needs Azure credentials available to
CodeBuild
C) **Terraform anyway**, accepting the state problem or working around it

[Answer]:

**Recommendation: A for v1.** B is the better end state but requires putting Azure credentials into the AWS
pipeline, which is a security conversation this workshop does not need. C is explicitly argued against by the
research.

---

## Section 5 — Business Domain

### Q12. Is `teams-bot` one bounded context, or does the agent belong to a different one?

Relevant because the agent is channel-agnostic and the Knowledge Base team owns a neighbouring capability.

A) **One context** — the whole blueprint is "Teams-fronted conversational app"
B) **Two** — "Teams channel adapter" and "conversational agent", with the agent a candidate to become its own
blueprint later
C) Do not model it; it is one blueprint

[Answer]:

**Recommendation: B as a note, A in practice.** The design already draws that line — the agent has no path to
any Teams component. Recording it as two contexts inside one blueprint documents the seam without prematurely
splitting the deliverable.

---

## Section 6 — Code Organisation

### Q13. Confirming the layout from Application Design

```
blueprints/teams-bot/
  infra/teams-bot.yml
  src/frontdoor/ | worker/ | agent/ | shared/
  scripts/                    <- Microsoft-side provisioning (Q11)
  Dockerfile                  <- two targets: lambda, agent
  pyproject.toml + uv.lock
  README.md                   <- the one-time onboarding runbook
```

A) **Confirmed**
B) Changes needed — describe

[Answer]:

### Q14. Where does the Teams manifest live?

The research establishes that authoring it as a file is **better** than the Developer Portal, which has a bug
rejecting `supportsChannelFeatures`.

A) `blueprints/teams-bot/teams-app/manifest.json` plus icons, zipped by a script
B) Outside the repo, managed by hand
C) In `scripts/` alongside the provisioning script

[Answer]:

**Recommendation: A.** It becomes reviewable like everything else, and it is the only way to get
`supportsChannelFeatures` in reliably.

---

## After answers

I will analyse for vagueness, contradictions and combined options; raise follow-ups if any appear; then ask for
approval before generating the three unit artifacts.

**Blank answers will be treated as accepting the stated recommendation**, recorded explicitly.
