# AI-DLC Turnover — `teams-bot` Blueprint

**Written**: end of workshop day one (late), for resumption on **day two, 2026-08-04**
**Written by**: Claude, for whoever picks this up — most likely a fresh Claude session
**Repo**: `cu-aaii/ai-dlc-workshop`, branch `c/fr266-wip`

> ⚠️ **This file lives in `docs/`, which is NOT gitignored, in a PUBLIC repository with secret scanning
> disabled.** No credential appears below and none should ever be added.

---

## 1. Start here — the one thing to do next

> 🛑 **STOP — this document was written against a checkout 28 commits behind `upstream/main`.**
> Merged 2026-08-04 at `318e92f`. The Terraform stage, the ARM64 container Build stage, `builder-mcp`
> and the Knowledge Base blueprint all **exist** now; several statements below say they do not, and
> §10 told you not to build one of them. **Read
> `aidlc-docs/inception/upstream-reconciliation-2026-08-04.md` first** — it lists every corrected fact
> and the three decisions that gate Units Generation Part 2. Where the two disagree, that document
> wins.

**Everything through INCEPTION is done and approved except the final step of Units Generation.**

The user's exact words ending day one: *"We're ready to proceed to generation. But I'll do that in the
morning."*

**So: Units Generation Part 1 (Planning) is complete and the user has approved proceeding. Part 2
(Generation) has not started.** Do that first. It needs no further questions.

### Part 2 produces three artifacts

Per `aidlc-rules/aws-aidlc-rule-details/inception/units-generation.md` Steps 12–16:

| Artifact | Content |
| --- | --- |
| `aidlc-docs/inception/application-design/unit-of-work.md` | Unit definitions, responsibilities, code organisation strategy |
| `aidlc-docs/inception/application-design/unit-of-work-dependency.md` | Dependency matrix between units |
| `aidlc-docs/inception/application-design/unit-of-work-story-map.md` | **Requirement**-to-unit map — see the note below |

Then: mark the plan checkboxes `[x]`, verify Security Baseline compliance, update `aidlc-state.md`, log to
`audit.md`, and present the completion message in the exact format at Step 16 — which offers *Request Changes*
and *Approve & Continue to CONSTRUCTION PHASE*.

**Important adaptation already agreed**: User Stories was **skipped**, so no stories exist. The story-map
artifact maps the **33 functional requirements** from `requirements.md` to units instead. Do not fabricate
stories and do not silently drop the artifact — this decision is recorded in the plan and in `audit.md`.

**The source of truth for what to generate** is
`aidlc-docs/inception/plans/unit-of-work-plan.md`. Read it in full first. It contains the answered questions,
ten proposed units, and — critically — **two revisions that changed the plan after the questions were
answered** (see §6 below).

---

## 2. Session mechanics — read before touching anything

### Resuming the AI-DLC workflow

`CLAUDE.md` gates the vendored rules on **explicit invocation**. This session is a continuation of an invoked
AI-DLC workflow, so the rules apply.

**Critical path-resolution note**: `core-workflow.md` resolves rule details from four hardcoded paths
(`.aidlc/aidlc-rules/…`, `.aidlc-rule-details/`, `.kiro/…`, `.amazonq/…`) and **none of them exists in this
repo**. Resolve every `common/…` and `inception/…` reference against:

```
aidlc-rules/aws-aidlc-rule-details/
```

**Never edit anything under `aidlc-rules/`** — it is a byte-identical vendored copy, and the re-sync is a
delete-and-replace.

### Hard rules that are easy to violate

- **`aidlc-docs/audit.md` is APPEND-ONLY. Never overwrite it.** Log every user input with the *complete raw
  text*, never summarised, with an ISO 8601 timestamp.
- **Questions are never asked in chat.** They go into `.md` files with `[Answer]:` tags, multiple choice
  A/B/C…, a blank line between options, and **"Other" as the mandatory last option**.
- Every Mermaid or ASCII diagram needs a **text alternative** immediately after it.
- The **Security Baseline extension is ENABLED**, so every stage must verify compliance against its artifacts
  *before* presenting a completion message. Resiliency and property-based testing are **off** — do not load
  their rule files.

### AWS access

```sh
export AWS_PROFILE=sso-admin-890349359349      # the WORKSHOP account
```

- The **`default` profile is expired AND points at a busy production account.** Do not use it.
- Workshop account has `aidlc-account-bootstrap`, `aidlc-main-pipeline`, `aidlc-main-hello-world` deployed and
  green; CodeConnections `cu-aaii` is `AVAILABLE`; ECR repo `aidlc-main` exists and holds **zero images**.

### Before any push

```sh
tools/check
```

`uv` is the only prerequisite. **Never run bare `cfn-lint`** — `--region` takes `nargs='+'`, so
`cfn-lint --region us-east-1 <paths>` silently lints nothing and exits 0. A literal `--` before paths is
mandatory; `tools/check` handles it.

---

## 3. Exact stage state

| Stage | State |
| --- | --- |
| Workspace Detection | ✅ complete |
| Reverse Engineering | ✅ complete, **approved** |
| Requirements Analysis | ✅ complete, **approved** |
| User Stories | ⏭️ **SKIPPED** (infrastructure template, single persona) |
| Workflow Planning | ✅ complete, **approved** |
| Application Design | ✅ complete, **approved** |
| **Units Generation Part 1 (Planning)** | ✅ complete, **approved to proceed** |
| **Units Generation Part 2 (Generation)** | ⬜ **NOT STARTED — do this next** |
| CONSTRUCTION phase (6 stages) | ⬜ all EXECUTE, none started |
| Operations | ⬜ placeholder |

**Risk level recorded for the project: HIGH.** Reasons, all still true: the container build path has never
executed; the pipeline self-deploys and its recovery procedure is undocumented; `main` deploys to a shared
account; multiple teams merge into one repo in parallel; nearly everything is a first for this repository.

---

## 4. Every decision already made — do NOT re-ask these

### Requirements (Q1–Q26 in `requirement-verification-questions.md`)

| | Decision |
| --- | --- |
| Blueprint name | **`teams-bot`** — generic and reusable, not course-specific |
| Capability | **Tier A** — prompt-configured (system prompt, model, greeting, scopes). Tier B (retrieval) a stretch goal |
| Teams scopes | **C** — personal + group chat + channel, **`@mention` required**. No RSC |
| Ingress | **Lambda function URL**, free AWS-provided address, `AuthType: NONE`, JWT validated in the handler |
| Response delivery | **Teams response streaming** in personal chat; ack + typing + single reply elsewhere |
| Model access | **LiteLLM gateway only** (`https://api.ai.it.cornell.edu`) — **hard constraint** |
| State | Conversation history via **AgentCore Memory** |
| Agent runtime | **Bedrock AgentCore — MANDATED** by Team E. CloudFormation only (Marty) |
| Tenant | **Dev tenant / dev environment**, single identity |
| Identity | Single-tenant Entra app + **client secret** in Secrets Manager (`aidlc/main/teams-bot-*`) |
| Microsoft provisioning | **Scripted, with one interactive OAuth consent** — see §5 |
| Secret rotation | Out of scope for v1 |
| Container build | Wired **in the same PR** |
| Delivery | **One PR to `main`**, reviewed by **Marty Sullivan** |
| Tag validation | **DEFERRED** — user is supplying a tagging doc. Four `cornell:*` tags stand meanwhile |
| Med-risk data | **Permitted, to and from the gateway.** Gateway-routed traffic is compliant. Settled — **do not reopen** |
| Load / availability | Workshop scale. No latency or availability SLA |
| Extensions | Security Baseline **ON**; Resiliency **off**; Property-based testing **off** |

### Application Design (Q1–Q13 in `application-design-plan.md`)

| | Decision |
| --- | --- |
| Delivery owner | **Separate worker Lambda** — the agent stays channel-agnostic |
| Hand-off | **Lambda async invoke** (`InvocationType: Event`) |
| Agent | **Channel-agnostic** — has never heard of Teams |
| Contract | **Normalised `Envelope`**, not raw Activity JSON |
| Streaming | Agent emits **SSE**; worker forwards cumulative updates |
| Idempotency | **DynamoDB table**, three-state conditional writes |
| History | **The agent** reads its own from AgentCore Memory |
| Code sharing | **Shared internal module** (`src/shared/`) |
| JWT validation | **Local** to this blueprint, but self-contained for later extraction |
| Language | **Python 3.12 / ARM64** |
| Dockerfile | **One multi-stage file, two named targets** (`lambda`, `agent`) |
| Error UX | **Generic message + correlation ID** (the activity `id`) |
| Code style | **No Cornell convention exists** — follow `validate_stacks.py` and `hello-world.yml` |

### Units Generation (Q1–Q14 in `unit-of-work-plan.md`)

| | Decision |
| --- | --- |
| Execution model | **Mob-style** — whole cross-functional team, **serial, one unit at a time** |
| PRs | **One PR** |
| Azure | **Everything in the dev environment**, single identity |
| U0 owner | **The team** — access available because it is a dev env |
| Ordering | **Risk retirement** — prove the build path first |
| Units | **10**, treated as *sequencing guidance, not PR boundaries* |
| Hardening | Split — `uv.lock` and log retention inline; alarm + dependency scanning as a unit |
| Partial deploys | **Acceptable** between units |
| Provisioning script | `blueprints/teams-bot/scripts/`, **run by a person**, not CodeBuild |
| Manifest | `blueprints/teams-bot/teams-app/manifest.json` **in git** |
| Bounded contexts | One blueprint, documented as two contexts |

---

## 5. Gotchas that have already cost time — carry these forward

### Repository / pipeline

- ~~**`ContainerBuildProject` is x86_64**~~ / ~~**There is no Build stage**~~ — **BOTH OBSOLETE
  2026-08-04.** Upstream added a second, ARM64 build project (`ARM_CONTAINER`,
  `amazonlinux2-aarch64-standard:3.0`) *and* a `Build` stage that invokes it, with `CONTAINER_CONTEXT`
  added alongside `CONTAINER_TARGET` so each component names its own build context. `tiny-chatbot` and
  `builder-mcp` both build through it, so the digest contract is proven by example rather than
  theory. Model this blueprint's Build action on one of those instead of writing it from scratch.
- **`codebuild.yml` needs `CONTAINER_TARGET` and `DATE_TAG`** (usually `#{GitRepository.AuthorDate}`) supplied
  by the Build action. It exports `CONTAINER_DIGEST` as a full `<repo>@sha256:…` reference.
- **The pipeline only runs on `main`.** `Environment` is the branch name and Source tracks
  `BranchName: !Ref Environment`. **A PR branch does not trigger it**, so the build path is first exercised on
  merge. Validate the Dockerfile locally first with `docker buildx build --platform linux/arm64`.
- **A CodePipeline execution uses the structure in place when it *started*.** So the first merge adding a
  Build stage will update the pipeline, deploy `hello-world`, report every stage `Succeeded`, and **not deploy
  `teams-bot`**. That is the repo's documented silent-failure shape — it looks alarming and is benign. Start a
  second execution manually. **Flagged as expected behaviour to confirm, not verified.**
- **`AWS::SSM::Parameter` takes `Tags` as a map**, unlike every other resource.
- **Stack names must be `<application>-<environment>-<name>`** or `BuildPipelineRole` refuses them with an
  opaque authorization error.
- **`validate_stacks.py` fails in both directions** — a template must be in `stacks.yml` *and* have a matching
  pipeline action.
- **Observed tag values**: `cornell:owner=ai-sei`, `cornell:deployment-id=<stack name>`.

### Bot Framework / Teams

- **The prototype's `serviceurl` check silently did nothing.** The claim is **`serviceurl` (lowercase `u`)`**;
  the code read `payload.serviceUrl` (camelCase), which is always `undefined`, and a `&&` guard turned the
  check into a skip. **Absence of the claim must be a FAILURE.** A negative test is mandatory (FR-8a).
- **The prototype's reply URLs relied on an undocumented trailing slash** on `serviceUrl`. Normalise once,
  reuse for both the claim check and URL construction.
- **The acknowledgement budget is 10–15 seconds, channel-dependent**; overrun shows the user
  `504:GatewayTimeout`. Never return non-2xx on auth failure — it causes endless retries.
- **Streaming is one-on-one chats only.** Updates must be **cumulative** ("A brown" → "A brown fox"), rate
  limited to **1/second** with 1.5–2s buffering, sequential, and **`streamSequence` must be absent on the
  final message**.
- **`membersAdded`/`membersRemoved` must be filtered on the `28:` bot prefix**, or the bot greets itself.
- **Conversation ids differ**: personal `a:xxx`, channel/group `19:xxx@thread.tacv2`.
- **Manifest v1.25 needs top-level `"supportsChannelFeatures": "tier1"`** for `team` scope. The Developer
  Portal GUI does not expose it and its validator **wrongly rejects it** inside the `bots` object — which is
  why the manifest is authored as a file in git.
- **Worker Lambda timeout must be set explicitly.** The 3-second default would truncate **every** reply. Use
  ~5 minutes.
- **Lambda async invoke retries twice on error** — an internal duplicate source independent of Microsoft's
  retries. This is why there are two idempotency guards.

### Microsoft-side CLI (from `Teams Admin CLI Automation - Findings 2026-08-03.md`, live-tested)

- **`az ad app create` does not create the service principal — `az ad sp create` is a separate mandatory
  step.** The Azure Portal does both when you click through the app-registration blade, so the omission is
  easy and the symptom is remote: the app exists, the secret is issued, `az bot create` accepts the app ID,
  and then the bot's **first outbound token request** fails with nothing pointing back at the cause. Highest
  time-loss risk in U0.
- **`az rest` cannot make the App Catalog calls.** It authenticates as the "Azure CLI" first-party app, whose
  scopes are fixed by Microsoft and exclude `AppCatalog.*`. **A global admin still gets `403`** — it is a
  client-app limitation, not a privilege gap, and the error reads like a permissions problem. Use the
  **Microsoft Graph Command Line Tools** public client (`14d82eec-204b-4c2f-b7e8-296a70dab67e`) with
  device-code flow, then plain `curl`.
- **Verify first-party client IDs against the directory before building on them.** Teams PowerShell is
  `1fec8e78-bce4-4aaf-ab1b-5451cc387264` (verified). A GUID web search offers for the same purpose,
  `5170baac-d33f-4ab5-bc04-6ac2a602c700`, **does not exist in the tenant** and was likely fabricated.
- **`Get`/`Update-M365TeamsApp -Id` wants the *catalog* id**, not the manifest/external id.
- **The Teams PowerShell docs' parameter metadata is wrong** — `-AppInstallType` and friends are a separate
  parameter set and throw if combined with `-AppAssignmentType`/`-Groups`.
- **The app package zip needs `manifest.json` + `color.png` + `outline.png` at the zip ROOT**, no subfolder.
- Catalog publish (`POST /appCatalogs/teamsApps`) and group scoping (`Update-M365TeamsApp -Groups`) are both
  **confirmed working live** with a delegated device-code token. Only the one browser consent is manual.
- **That one browser consent is permanent for group scoping — do not design around removing it.** Settled
  2026-08-04 by closing all three routes: app-only `401`s, Teams Administrator escalation changes nothing,
  and `Connect-MicrosoftTeams -AccessTokens` fails structurally (module needs a third resource token,
  `https://substrate.office.com`; the parameter accepts exactly two). **The refresh-token pattern that makes
  publish viable in CI cannot be extended to scoping.**
- **Setup Policies *are* app-only automatable** (confirmed live, full round trip). Useless here — publishing
  to the catalog makes sideloading moot — but it proves the wall is **endpoint-specific**, so Microsoft's
  app-only exclusion list predicts correctly in **both** directions and can be trusted for other cmdlets.
- **The only open research question is `New-TeamsApp` under app-only auth.** Not on the exclusion list, never
  exercised. If it works, catalog publish becomes fully unattended and §9 reopens. Cheap to test with the
  existing certificate harness — the highest-value remaining hour on the Microsoft side.

### Gateway

- The key in `~/.claude/settings.json` is a **virtual key scoped to `llm_api_routes`**, which is why
  `/v1/models` shows only chat models and `/model/info` returns 403. **The gateway does have ~12 embedding
  models.** The bot's key must be scoped for whatever it needs.
- Gateway model IDs use **gateway naming** (`amazon.titan-text-embeddings.v2`), not Bedrock's native IDs.
- The gateway is hosted in **AWS us-east-1** — same region as the workshop account.

---

## 6. Two revisions applied AFTER the unit questions were answered

**Read these before generating the unit artifacts** — they changed the plan's shape.

1. **Parallelism withdrawn.** Mob construction is **serial** — whole team, one unit at a time. Every
   "Parallel? Yes" in the unit table is void. Consequences: risk-retirement ordering matters *more*; each unit
   should end in something a **non-engineer** can evaluate (the mob includes product owners, ITSM, security,
   analysts, designers, stakeholders); **U5 and U7 are the real mob checkpoints** — the bot saying hello, and
   text appearing progressively. U1–U3 are one stretch of plumbing, not three celebrations. **U0 is the
   exception** — non-AWS, needs admin credentials, cannot be mobbed.
2. **One PR means units are sequencing guidance, not PR boundaries.** Describe them as an ordered work
   breakdown with explicit completion criteria.

---

## 7. Open dependencies — with owners

| # | Item | Owner | Blocks |
| --- | --- | --- | --- |
| D-2 | A gateway **service key for the bot** (not a person's key) | Gateway operator | Deployment, not design |
| D-3 | **Tagging guidance document** | **The user** — promised | Q19 stays deferred |
| D-4 | `KnowledgeBaseId` + timeline | Knowledge Base team | **Tier B only** — out of v1 scope |
| D-5 | Does another team also need the **Build stage**? | **Marty** | Merge conflicts in `pipeline.yml` |
| D-6 | Cost guardrails on the shared account | Dan Klinger | Advisory only |

**Also worth chasing**: nobody has documented the **manual pipeline recovery procedure**. If a merge breaks
`pipeline/pipeline.yml`, the pipeline cannot deploy its own fix and someone must deploy the template by hand.

---

## 8. ⚠️ Unresolved and not part of the workflow — credential exposure

Reported at the start of day one. **Still outstanding.** Independent of the AI-DLC gates.

| Location | Credential |
| --- | --- |
| `docs/teams-chatbot-docs/Research into in-tenant setup.md` | Entra app **client secret**, a test-user **password**, an **n8n bearer token** |
| `.mcp.json` | A **GitHub PAT** |
| `~/.claude/settings.json` | The **LiteLLM gateway key** (outside the repo — lower urgency) |

**`git check-ignore` confirms neither `docs/` nor `.mcp.json` is gitignored.** Both are currently untracked, so
nothing is committed — but `git add .` would commit them, into a **public repo with secret scanning disabled**.

**Recommended order**: rotate all of them (assume burned) → gitignore `.mcp.json` → scrub the research document,
replacing values with placeholders.

**Note for the app registration**: whatever `aud` the bot validates against should be a **newly issued
registration**, not the one whose secret is exposed.

---

## 9. Artifact index

### The living documents — read these first

| Path | Purpose |
| --- | --- |
| `aidlc-docs/aidlc-state.md` | **Current state.** Stage progress, decisions, open dependencies |
| `aidlc-docs/audit.md` | **Append-only** history of every input and action |
| `aidlc-docs/inception/plans/unit-of-work-plan.md` | **The input to the next action** |

### Requirements

`aidlc-docs/inception/requirements/`

| File | Purpose |
| --- | --- |
| `requirements.md` | **33 FRs, 9 NFRs**, Security Baseline table, assumptions, risks |
| `requirement-verification-questions.md` | Q1–Q26 with answers |
| `agentcore-placement-note.md` | Why AgentCore is the brain, not the front door |
| `response-delivery-and-timeouts.md` | The 10–15s budget; Teams streaming contract |
| `prototype-reference-implementation.md` | n8n analysis — 10 mechanics confirmed, **2 defects found** |
| `model-access-options.md` | Gateway vs Bedrock; the R1/R2/R3 retrieval routes |
| `knowledge-base-integration.md` | Managed KB; **use `Retrieve`, not `AgenticRetrieveStream`** |
| `blueprint-configuration-surface.md` | Why Q3 was reframed; the MCP writes parameters into a repo |
| `multi-party-scope-path.md` | Group/channel expansion cost |
| `account-reconnaissance.md` | Read-only AWS findings (account IDs redacted — public repo) |
| `ingress-explained.md` | Plain-language explainer written for administrators |
| `devops-questions.md` | Questions for Dan, with answers received |

### Application Design

`aidlc-docs/inception/application-design/` — `components.md`, `component-methods.md`, `services.md`,
`component-dependency.md`, `application-design.md` (consolidation + Security Baseline verification).

### Plans

`aidlc-docs/inception/plans/` — `execution-plan.md`, `application-design-plan.md`, `unit-of-work-plan.md`.

### Reference documents (inputs, not outputs)

`docs/teams-chatbot-docs/` — four tracked research documents, plus one untracked (see §8).
**`Teams Admin CLI Automation - Findings 2026-08-03.md` is by far the most valuable**: it is
**live-tested**, it corrected several earlier conclusions, and it now **also contains the former
`Entra CLI Automation - Research 2026-08-03.md`**, which was folded into it and deleted. Citations to
that filename elsewhere in the AI-DLC artifacts have been repointed; if you find one that wasn't, the
content is in the findings document. It absorbed a second round of live testing on 2026-08-04 — the
`-AccessTokens`/Substrate dead end, Setup Policies confirmed app-only, push-install confirmed live, and
the `az ad sp create` gotcha.
`docs/Participant Brief - Invited Attendees (2).html` — workshop context, team model, blueprint list.
`docs/teams bot exploration.json` — the n8n prototype export (checked: contains no secrets).

---

## 10. Things NOT to do

- **Do not reopen med-risk data handling.** Confirmed twice, bidirectionally, and closed. Admin question 14 is
  withdrawn and marked "do not ask this."
- **Do not reopen gateway reachability from AWS.** Confirmed by the user; A-2 struck, D-1 closed.
- **Do not re-ask any decision in §4.**
- **Do not edit `aidlc-rules/`.**
- **Do not overwrite `audit.md`.**
- **Do not propose Bedrock-direct inference.** All model traffic routes through the gateway — hard constraint.
- **Do not propose `AWS::Bedrock::KnowledgeBase`** for retrieval. It embeds the user's query via a direct
  Bedrock call with no way to redirect it, which the gateway mandate forbids. The KB team owns that anyway.
- ~~**Do not build a Terraform stage.**~~ **WITHDRAWN 2026-08-04 — the stage exists.** Marty built it
  (PR #12) and `CLAUDE.md` now makes Terraform the *required* path for Azure/Entra, at
  `blueprints/<name>/infra/azure/`. The secret-in-state objection is answered by the repo's own
  pattern: declare the secret resource in CloudFormation, inject the value out of band, never generate
  it in Terraform. **What Terraform still cannot do is catalog publish and availability scoping** — no
  provider covers them, and the generic msgraph provider is app-only-mode only. See decision **D1** in
  `aidlc-docs/inception/upstream-reconciliation-2026-08-04.md`; note `azurerm` is blocked today for
  want of an Azure subscription and RBAC assignment, so the Bot Service half cannot be Terraform yet.
- **Do not suggest ROPC** (a no-MFA admin service account) for Teams catalog automation. It is a *worse*
  posture than a manual step.
- **Do not write a credential into any file.**

---

## 11. One-line summary for the morning

> INCEPTION is complete and approved except **Units Generation Part 2**. Read
> `aidlc-docs/inception/plans/unit-of-work-plan.md`, generate the three unit artifacts (mapping **requirements**
> to units, since User Stories was skipped), verify Security Baseline compliance, log to `audit.md`, and present
> the Step 16 completion message offering CONSTRUCTION. No questions outstanding.
