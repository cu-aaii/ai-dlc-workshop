# Requirement-to-Unit Map — Track C, the Teams front end of `course-chatbot`

**Generated**: 2026-08-04
**Stage**: INCEPTION — Units Generation (Part 2: Generation)

## Why this is a requirement map and not a story map

`units-generation.md` Step 2 calls for `unit-of-work-story-map.md`, mapping stories to units. **User
Stories was skipped** — the deliverable is a parameterised infrastructure template with a single persona
and no acceptance criteria beyond what requirements already capture, and that skip was approved in
Workflow Planning.

Rather than fabricate stories to fill the artifact, or drop it and lose what it is for, this maps the
**functional and non-functional requirements** from `requirements.md` to units. The artifact's purpose is
to prove nothing is orphaned; requirements serve that purpose using material that actually exists.

**Coverage**: 33 numbered functional requirements plus 4 lettered sub-requirements (FR-3a, FR-7a, FR-8a,
FR-23a) = **37 functional items**, and **9 non-functional**. The Part 1 plan said "33 functional
requirements"; the higher figure is the same set counted honestly.

**Status vocabulary.** `MET` = in the delivered code and verified. `PARTIAL` = mechanism present, scope
narrower than the requirement. `UNMET` = not delivered. `DEFERRED` = consciously moved to the AgentCore
step. `AMENDED` = the requirement itself changed. **`VIOLATED` = the delivered design contradicts it** —
used once, and it is the most important row in this document.

---

## 1. The one violated requirement

**FR-9. Acknowledge before working.** *"The endpoint MUST return `200 OK` before performing any work.
The budget is 10–15 seconds depending on channel; overrun surfaces `504:GatewayTimeout` to the user."*

**Status: VIOLATED by the synchronous design.** The delivered handler validates, retrieves, calls the
gateway, posts the reply, and *then* returns 200. Nothing is acknowledged early, because a single
synchronous Lambda has nothing to acknowledge from — the early-200 pattern is what the Worker Lambda and
async invoke existed to enable, and both were withdrawn.

**What this means in practice**: the requirement is not merely unimplemented, it is structurally
unavailable in this shape. The bot works if the whole round trip fits inside the channel's budget, and
shows the user `504:GatewayTimeout` if it does not. Cold start plus retrieval plus generation is the
exposure.

**Why it was accepted**: for a demo with a fast model and a warm function it fits, and the alternative
was building the worker path in the time available. **It is not acceptable beyond a demo**, and it is
the single strongest argument for restoring U4 and the async hand-off — stronger than idempotency,
which is the reason U4 was originally proposed.

Recorded here rather than in a footnote because a compliance table that silently marks this `PARTIAL`
would be the kind of artifact this workshop exists to stop producing.

---

## 2. Product definition — §1

| Req | Unit | Status | Note |
| --- | --- | --- | --- |
| **FR-1** template not a bot | U2 | **MET** | Behaviour is parameter-driven: `ModelId`, `CourseName`, `GreetingText`, prompt via S3 |
| **FR-2** config as CFN parameters | U2 | **PARTIAL** | Parameters work from the pipeline. **A builder's values do not arrive** — `deployment_create` forwards only `Application`, `Environment`, `Owner` and `pipeline_parameters`, dropping `inputs` (#15 finding 2). Mitigated by mirroring into SSM; the manifest documents it |
| **FR-3** Tier A parameter surface | U2 | **MET** | `SystemPrompt` (via S3), `ModelId`, `GreetingText`, `Owner`, `DeploymentName`. **`TeamsScopes` absent** — personal only, so nothing to select |
| **FR-3a** prompt over 4096 chars | U2 | **MET** | `SystemPromptS3Bucket`/`Key`, with the S3 grant conditional so no wildcard when unused |
| **FR-4** Tier B accommodated without redesign | Retrieval | **MET** | Delivered *and* optional. Was briefly **violated**: a deploy-time SSM-resolved id made the knowledge base a hard prerequisite, which is the opposite of "accommodate without redesign". Now a plain optional parameter with a conditional IAM grant |
| **FR-5** naming | U2 | **MET** | ~~AMENDED~~ — the amendment was **reverted** 2026-08-04. FR-5 as written stands: blueprint `teams-bot`, stack `aidlc-main-teams-bot`. Gate Q1's option set was built on a misreading of the Vision brief §3; the participant brief's catalog names this block "Chatbots (incl. Microsoft Teams-fronted)". The requirement was correct originally |

---

## 3. Inbound path — §2

| Req | Unit | Status | Note |
| --- | --- | --- | --- |
| **FR-6** public HTTPS endpoint | U2 | **MET** | Function URL, `AuthType: NONE`, AWS-provided address |
| **FR-7** URL stability | U2 | **MET** | Deterministic `FunctionName`; URL is a stack output |
| **FR-7a** endpoint pushed programmatically | — | **UNMET** | `az bot update --endpoint` is run **by hand**. The withdrawn click-ops concession is back in practice. Needs the Cornell-tenant login while the app registration is dev-tenant |
| **FR-8** inbound JWT validation | U3 | **MET** | RS256 **pinned**, `iss`, `aud` from config, `exp`/`nbf` with 300s leeway, `serviceurl` correlation, absent claim fails |
| **FR-8a** negative test | U3 | **MET** | `test_absent_serviceurl_claim_is_a_failure` and `test_mismatched_serviceurl_is_rejected`. Also `alg: none` forgery |
| **FR-9** acknowledge before working | U4 | **VIOLATED** | **See §1** |
| **FR-10** never non-2xx on auth failure | U3 | **MET** | Verified against no-auth, malformed JSON, empty event, oversized body — all `200`. Lazy init exists so an INIT failure cannot bypass it |
| **FR-11** idempotency on activity id | U4 | **UNMET** | U4 withdrawn. Azure retries can produce a duplicate reply; the id is threaded as the correlation id, so restoring the guard is additive |
| **FR-12** activity type handling | U3 | **MET** | Dispatch on `type`, tolerates absent `text`, `membersAdded` filtered on `28:`, unknown types ignored |
| **FR-13** both conversation ID formats | U3 | **PARTIAL** | `parse_activity` preserves both and it is tested. Only personal is exercised end to end; no manifest scopes |
| **FR-14** `serviceUrl` normalised once | U3 | **MET** | One `normalize_service_url`, feeding both the claim check and reply URLs. Confirmed against a live payload carrying the trailing slash |
| **FR-15** JWKS caching | U3 | **MET** | `PyJWKClient(cache_keys=True)`; refreshes on `kid` miss |

---

## 4. Outbound path — §3

| Req | Unit | Status | Note |
| --- | --- | --- | --- |
| **FR-16** delivery seam | U7 | **UNMET** | No dispatcher. **The consequence is real**: adding group/channel later changes the reply path, which is exactly what the seam was designed to prevent |
| **FR-17** personal-chat streaming | U7 | **UNMET** | Withdrawn. All six streaming rules are unexercised, and remain the trap they always were |
| **FR-18** typing + single reply | U5 | **PARTIAL** | Both delivered, and used for **personal** chat — which is the scope FR-18 said would *not* use them. The mechanism is right, the scope inverted |
| **FR-19** reply targets | U5 | **MET** | Reply-to-activity and new-activity URLs both built from the normalised base |
| **FR-20** outbound authentication | U5 | **MET** | `client_credentials`, correct scope, cached with 60s skew |

---

## 5. Agent and model access — §4

| Req | Unit | Status | Note |
| --- | --- | --- | --- |
| **FR-21** AgentCore Runtime mandated | U6 | **DEFERRED** | Mandate stands. `_ask()` is the seam; research established no container is needed (`CodeConfiguration`) |
| **FR-22** container contract | U6 | **DEFERRED** | arm64/8080/`/ping`/`/invocations`/otel apply to the agent image, which does not exist yet |
| **FR-23** all model traffic via the gateway | Retrieval / U5 | **MET** | Anthropic client with the gateway `base_url`. **This also removed the scaffold's violation** rather than documenting it |
| **FR-23a** gateway service key from Secrets Manager | U2 | **PARTIAL** | Resource created with `GenerateSecretString`, read at runtime. **The value is not injected**, so the bot cannot answer until someone does |
| **FR-24** conversation state via AgentCore Memory | U6 | **DEFERRED** | **Worth stating plainly: the bot has no conversation memory at all.** Every message is single-turn. Teams supplies no history, so nothing compensates |
| **FR-25** retrieval via `Retrieve` | Retrieval | **MET** | `Retrieve` only; 10,000-char cap enforced; no S3 access; id resolved at deploy time so the role names one ARN |

---

## 6. Deployment and repository — §5

| Req | Unit | Status | Note |
| --- | --- | --- | --- |
| **FR-26** container build stage | U1 | **MET** | `CourseChatbotContainer` on `ArmContainerBuildProject`, with `CONTAINER_TARGET`, `CONTAINER_CONTEXT`, `DATE_TAG` |
| **FR-27** ARM build architecture | U1 | **AMENDED** | Intent met, literal text obsolete: upstream **added** `ArmContainerBuildProject` rather than converting the x86 one |
| **FR-28** digest pinning | U1 | **MET** | `#{CourseChatbotContainer.CONTAINER_DIGEST}`, never a tag |
| **FR-29** registration in both places | U2 | **MET** | `stacks.yml` + matching action; `validate_stacks.py` enforces both directions. Also required removing the `MANIFEST_EXEMPT` entry |
| **FR-30** all four `cornell:*` tags | U2 | **MET** | Every taggable resource. SSM uses the map form, everything else the list form |
| **FR-31** every parameter explicit | U2 | **MET** | 16 of 16, verified programmatically against `ParameterOverrides` |
| **FR-32** one PR to `main`, reviewed | — | **PENDING** | Two commits pushed to the fork; **the PR is not open**. Cross-fork now, since `main` requires zero approving reviews but team membership to merge |
| **FR-33** `tools/check` passes | U1–U9 | **MET** | Green, including the new bidirectional manifest check |

---

## 7. Non-functional — §6

| Req | Status | Note |
| --- | --- | --- |
| **NFR-1** region `us-east-1` | **MET** | |
| **NFR-2** CloudFormation only for AWS | **MET** | No CDK, SAM or Terraform for any AWS resource |
| **NFR-3** serverless, container images | **MET** | And the no-Docker alternative was measured and rejected: 4114 chars against the 4096 inline cap |
| **NFR-4** latency, no SLA | **JUSTIFICATION VOID** | NFR-4 says *"streaming removes the latency constraint, so model choice is a quality decision rather than a speed one."* **Streaming was withdrawn, so the constraint is back.** Model choice is now a latency decision again — which is why `claude-haiku-4-5` is the default |
| **NFR-5** availability, no SLA | **MET** | |
| **NFR-6** workshop scale | **MET** | Streaming's 1/second budget no longer consumed, since there is no streaming |
| **NFR-7** cold starts acceptable | **JUSTIFICATION VOID** | Rested on streaming decoupling cold start from the acknowledgement deadline. Without streaming a cold start eats the 10–15s budget directly. **Compounds FR-9** |
| **NFR-8** public egress, no VPC | **MET** | Confirmed reachable; gateway is in AWS `us-east-1` |
| **NFR-9** deploys identically by hand and by pipeline | **PARTIAL** | Holds, with one caveat: a hand deploy must pass the SSM parameter *path* for the knowledge base id, and fails at resolution if the knowledgebase stack is absent |

---

## 8. Orphan check

**Every one of the 37 functional items and 9 non-functional items above is assigned to a unit or
explicitly marked as having no owning unit.** Three have no unit and that is deliberate, not an
oversight:

| Req | Why no unit |
| --- | --- |
| **FR-7a** | An operational step against Azure, not AWS work. Belonged to U0, which was substituted by reusing the existing registration |
| **FR-32** | A delivery act, not a build activity |
| **NFR-\*** | Cross-cutting by nature; constrain every unit rather than belonging to one |

**No requirement is unassigned. No unit exists without a requirement justifying it.**

### Tally

| | Count |
| --- | --- |
| MET | 25 |
| PARTIAL | 6 |
| DEFERRED | 3 |
| UNMET | 4 |
| AMENDED | 2 |
| **VIOLATED** | **1** |
| Justification void | 2 |

**The four UNMET plus the one VIOLATED are one coherent gap, not five scattered ones**: FR-9, FR-11,
FR-16 and FR-17 all follow from withdrawing the worker and the async hand-off, and FR-7a is Microsoft-side.
Restoring the worker closes four of the five, which makes it the highest-value single piece of work
remaining — ahead of AgentCore, because AgentCore adds capability while the worker fixes correctness.
