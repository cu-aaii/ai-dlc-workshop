# AgentCore Mandated — Workshop Context and the Resulting Critical Path

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis
**Source of the directive**: Team E, relayed in person, plus Marty Sullivan: *"It should be
CloudFormation."*

Marty Sullivan is named in the participant brief as **Assoc. Director & Principal Solutions
Architect, AI Platform (AI-SEI)** and as the technical contact for the workshop. Treating this as
authoritative platform direction, not a preference to weigh.

---

## 1. The directive, and what it settles

| Directive | Effect |
| --- | --- |
| **Design to use Bedrock AgentCore** | Settled. AgentCore is in scope for this blueprint. |
| **It should be CloudFormation** | Already a hard constraint in `CLAUDE.md`; now reinforced by the platform's principal SA. No CDK, no SAM, no Terraform for the AWS side. |

**My earlier observation is withdrawn.** I had noted that a synchronous fast-lite-model reply is a
Lambda calling the gateway directly, so AgentCore might not be needed in v1 — and that dropping it
would take the ARM64 container build off the critical path. That was a legitimate architectural
observation and it is now moot: AgentCore is a requirement. The ARM64 build is back on the critical
path, and §4 is the consequence.

**The CloudFormation half is already verified and is good news.** Queried directly against the
workshop account, not inferred: `AWS::BedrockAgentCore::Runtime`, `::RuntimeEndpoint`, `::Memory`,
`::Gateway` and `AWS::Bedrock::KnowledgeBase` are all registered and `FULLY_MUTABLE` in `us-east-1`.
AgentCore is deployable in pure CloudFormation with no escape hatch. `FULLY_MUTABLE` also means the
pipeline can update the runtime in place rather than replacing it on every merge.

---

## 2. Workshop context absorbed from the participant brief

Relevant facts, recorded because they change how this blueprint should be scoped.

- **Dates are August 3-4** — today and tomorrow. In person, CIS Building Room 250.
- **Teams-fronted chatbots is an explicitly named target blueprint**: *"Chatbots (incl. Microsoft
  Teams-fronted) — Basic and advanced conversational apps, with Teams as the default frontend for
  internal users."* This work is on the official list, not a side quest.
- **The keystone is a "Cornell Builder"** that selects a blueprint from a description and deploys it.
  Every other blueprint is a building block that keystone deploys. `CLAUDE.md` lists `builder-mcp/`
  as deliberately not built — so this blueprint is a **consumable** for something that does not exist
  yet, which is an argument for keeping its parameter surface clean and generic.
- **Multiple teams, self-organising**, each taking blueprints and breaking them into Units of Work
  and bolts. **Team E exists and is engaged with AgentCore.** See §5.
- AI-DLC vocabulary in use: bolts (sprints), Units of Work (epics), Mob Elaboration, Mob
  Construction. Phases: Inception → Construction → Operations.

### This informs Q2, and points away from my framing

Q2 asked whether this is a `course-chatbot` blueprint or a standalone `teams-bot` blueprint. The
brief says, in the preparation section:

> we won't be solving your unit's specific problems during the workshop — we'll be building
> **reusable platform blueprints**

and names the target as generic conversational apps with Teams as the default internal frontend.

That is a strong signal for **Q2 option B — a standalone, generic `teams-bot` blueprint** rather
than a course-specific one. A course chatbot would then be a *configuration* of it, or a later
blueprint that composes it. Recorded as informing Q2, **not** as answering it — the naming choice
determines the `cornell:blueprint` tag, the directory, the `stacks.yml` key and the stack name, and
that remains the product owner's call.

---

## 3. The unresolved tension: AgentCore versus a synchronous reply

Two decisions now in force pull against each other, and this is the one thing in this document worth
arguing about before the design stage.

**Decided**: reply synchronously with a fast lite model (Q8 → A).
**Now mandated**: route the work through AgentCore Runtime.

The synchronous path becomes:

```
Teams -> Azure Bot Service
           |
           v
      Lambda  (container image -- cold start #1)
           |
           |  InvokeAgentRuntime
           v
      AgentCore Runtime  (container -- cold start #2)
           |
           |  HTTPS
           v
      api.ai.it.cornell.edu  ->  claude-haiku-4-5
           |
           v
      reply posted back to Bot Framework
```

**Text alternative.** Teams sends to Azure Bot Service, which POSTs to a Lambda running a container
image — the first cold start. That Lambda calls `InvokeAgentRuntime`, reaching an AgentCore Runtime
container — the second cold start. The agent calls Cornell's LiteLLM gateway, which calls
`claude-haiku-4-5`. The reply travels back out to the Bot Framework API. All of it must fit inside
Microsoft's patience window.

**The problem is two container cold starts in series**, plus a gateway hop, plus generation, inside a
budget that wants single-digit seconds. Warm, this is likely comfortable. Cold, it is the failure
mode that produces duplicate replies — because Azure Bot Service retries, and a synchronous handler
that gets retried answers twice.

**Recommendation, now stronger than when I first raised it**: implement the hybrid. Put a hard
timeout of roughly four seconds on the AgentCore call. Under it, reply synchronously exactly as
intended. Over it, return `200 OK` and deliver the answer as a proactive message. This is a small
amount of code, it preserves the intent of the synchronous decision entirely, and it converts an
ugly intermittent failure into a slightly slower answer.

**Also required regardless**: idempotency keyed on the activity `id`, so a retry cannot produce a
second reply. The prototype never needed this because it acknowledged first.

---

## 4. The critical path this creates, specified concretely

AgentCore Runtime needs a container image in ECR before its stack can deploy. The repository has
every piece for this and **has never run any of it**. Six steps, in order.

### Step 1 — Fix the build architecture (two lines)

AgentCore Runtime requires **linux/arm64**. `pipeline/pipeline.yml:203-208` currently declares:

```yaml
Environment:
  ComputeType: 'BUILD_GENERAL1_SMALL'
  Image: 'aws/codebuild/amazonlinux2-x86_64-standard:4.0'
  ImagePullCredentialsType: 'CODEBUILD'
  PrivilegedMode: true
  Type: 'LINUX_CONTAINER'
```

Native ARM build means changing `Type` to `ARM_CONTAINER` and `Image` to an aarch64 standard image
(`aws/codebuild/amazonlinux2-aarch64-standard:3.0` — **confirm the available tag** rather than
trusting this version string). The alternative, cross-building with `buildx` and QEMU on the existing
x86 image, works but is substantially slower and is the wrong trade for a two-day workshop.

This is a change to `pipeline/pipeline.yml`, whose mechanics `CLAUDE.md` says to preserve. Changing
the compute type is not changing the *shape* of the pipeline, so it is within bounds — but it is
Dan's call to make, not something to slip in.

### Step 2 — Add a Build stage

**Clarifying a question that came up: yes, we use this repository — Marty is right.** The confusion
is worth pinning down precisely, because "the build stage isn't in this repo" is half true.

**What already exists here**, all of it committed and lint-clean:

| Component | Location |
| --- | --- |
| The buildspec — login, `docker build`, push, export the digest | `pipeline/codebuild.yml` |
| `ContainerBuildProject` — the CodeBuild project resource | `pipeline/pipeline.yml:191` |
| `ContainerBuildRole` — its service role | `pipeline/pipeline.yml` |
| `ContainerBuildLogs` — its log group | `pipeline/pipeline.yml` |
| `ContainerRepository` — the ECR repository, **deployed and live** as `aidlc-main` | `pipeline/pipeline.yml` |

**What is missing** is only the *stage that invokes them*. The pipeline today is `Source` →
`PipelineDeploy` → `BlueprintDeploy`, with nothing between the second and third. So all the machinery
is here and none of it is reachable — roughly fifteen lines of `Stages:` entry away.

That is also why the ECR repository in the account contains **zero images**: the project that would
push one has never been triggered.

A Build stage goes between `PipelineDeploy` and `BlueprintDeploy`, with a CodeBuild action invoking
`ContainerBuildProject`. `pipeline/codebuild.yml` requires two inputs it does not supply itself:

- `CONTAINER_TARGET` — the Dockerfile target to build, since the buildspec uses `--target`
- `DATE_TAG` — documented as usually `#{GitRepository.AuthorDate}`

The action needs a `Namespace` so its exported variable can be referenced downstream, matching the
convention every existing action already follows.

### Step 3 — Write the Dockerfile, following AWS's own pattern

Multi-stage with a **named target**, because the buildspec builds `--target $CONTAINER_TARGET`.

**The hard contract** (from the AgentCore Runtime troubleshooting documentation):

- **ARM64** compatible
- expose port **8080** — *"additional ports will be supported soon"*, so 8080 is not yet negotiable
- `/invocations` path available
- handle the expected payload format

Plus `GET /ping` returning `{"status": "Healthy"}` for health checks.

**The reference Dockerfile AWS publishes** for exactly this, which is worth following rather than
inventing:

```dockerfile
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY <agent_module>/ ./<agent_module>/

ENV PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", \
     "uvicorn", "<agent_module>.agent_runtime:app", \
     "--host", "0.0.0.0", "--port", "8080"]
```

Five things in there worth calling out:

1. **`uv` is the base image**, and this repository already standardises on `uv` — `tools/check` uses
   it and `validate_stacks.py` carries PEP 723 inline metadata. The toolchain matches with no new
   dependency to introduce.
2. **`uv sync --frozen` requires a `uv.lock`.** The Reverse Engineering assessment recorded that
   nothing in this repository is version-pinned and there is no lockfile — technical debt item 4. A
   lockfile is therefore *new work*, and it happens to **close that finding** rather than add to it.
   Worth doing properly rather than reaching for a loose `requirements.txt`.
3. **`opentelemetry-instrument` wraps the entrypoint**, which is what enables AgentCore
   Observability. Cheap to include now, annoying to retrofit once something is misbehaving in
   production.
4. **`PYTHONUNBUFFERED=1`** so logs stream rather than sitting in a buffer — the difference between
   useful and useless CloudWatch output during a workshop.
5. **FastAPI plus uvicorn is the expected shape.** AWS's phrasing is that existing agents *"just need
   a FastAPI wrapper"* to become AgentCore-compatible, so the agent logic and the HTTP surface stay
   cleanly separable.

**Two AgentCore Runtime behaviours worth knowing before designing the agent:**

- **Each session runs in a dedicated microVM, for up to 8 hours.** Session isolation is per-user by
  construction, which is a genuinely helpful property under a medium-risk data classification — one
  user's session cannot see another's.
- **VPC connectivity is supported.** So if the still-open networking question comes back requiring
  private networking, AgentCore can accommodate it without redesign.

### Step 4 — Plumb the digest through

`pipeline/codebuild.yml` declares `exported-variables: ['CONTAINER_DIGEST']` and sets it from
`docker inspect --format='{{index .RepoDigests 0}}'`, so its value is a full immutable image
reference of the form `<repo-uri>@sha256:...` — directly usable as an image URI.

The blueprint's CloudFormation action then passes it via `ParameterOverrides` as
`#{<BuildNamespace>.CONTAINER_DIGEST}`, and the blueprint template declares a matching parameter.
Pinning to a digest rather than a tag is the right default: it makes each deployment reproducible and
means a stack update cannot silently pick up a different image.

### Step 5 — Write the blueprint template

`AWS::BedrockAgentCore::Runtime` plus `::RuntimeEndpoint`, an execution role, and the Lambda front
door with its function URL. Requirements already established elsewhere and easy to lose:

- all four `cornell:*` tags on every resource, and `AWS::SSM::Parameter` takes `Tags` as a **map**
- every parameter passed explicitly from the pipeline; defaults exist only for hand-deployment
- deterministic `FunctionName` so CloudFormation never replaces the function and the URL survives
- the function URL exported as a **stack output**
- the AgentCore execution role needs `secretsmanager:GetSecretValue` for the gateway key, and egress
  to `api.ai.it.cornell.edu`
- AgentCore's JWT inbound auth writes claims including Subject to CloudTrail, which AWS warns against
  for PII — under a medium-risk classification this needs a decision, and SigV4 inbound auth from the
  Lambda avoids it entirely

### Step 6 — Register it, in both places

Add the template to `pipeline/stacks.yml` **and** add the matching action to `pipeline/pipeline.yml`.
`pipeline/validate_stacks.py` fails the build in both directions, so a registered-but-unwired
blueprint is caught at review time rather than deploying nothing silently.

### Honest assessment of the size of this

Steps 1, 2, 4 and 6 are mechanical and small. Step 3 is small if the agent is simple. Step 5 is the
real work. **The risk is not volume, it is that steps 1-4 have never executed even once** — the
`CONTAINER_TARGET`/`DATE_TAG` in, `CONTAINER_DIGEST` out contract is unproven, and the ECR repository
in the account contains zero images. Budget debugging time for the first image to land, and prove
that path with a trivial container before wiring the real agent to it.

---

## 5. Coordination risk: multiple teams, one repository, one shared account

Team E is engaged with AgentCore, and the brief says teams self-organise across the blueprint list.
`CLAUDE.md` states everyone works in this one repository and that **every merge to `main` deploys to
a shared AWS account**.

That makes `pipeline/pipeline.yml` a **high-contention file**. Any team adding a blueprint edits it,
and any team needing a container build now wants to add a Build stage to it. Three specific hazards:

1. **Merge conflicts in the stage list.** Two teams adding stages or actions to the same `Stages:`
   block will conflict, and the resolution is not always obvious to whoever merges second.
2. **The pipeline self-deploys.** `PipelineDeploy` runs before `BlueprintDeploy`, so a bad merge to
   `pipeline.yml` can leave the pipeline unable to deploy the fix. The Reverse Engineering assessment
   flagged that this recovery path is **not documented anywhere**. With one team that is a tolerable
   risk; with several teams merging in parallel over two days it is a live one.
3. **Stack name collisions.** Names must follow `<application>-<environment>-<name>` or
   `BuildPipelineRole` refuses them with an opaque authorization error. Two teams choosing the same
   `<name>` would collide in a shared account.

### RESOLVED 2026-08-03 — Marty: open a PR on this repository and he will review

Coordination goes through review rather than through a separate agreement. That settles ownership and
means no special process is needed.

Two residual points, both now smaller:

- **The duplication risk is mitigated, not eliminated.** If Team E opens its own Build-stage PR, Marty
  will see both and can reconcile them. Worth mentioning the Build stage in the PR description so it
  is visible as a shared change rather than looking like a blueprint-local detail.
- **The pipeline self-deployment recovery path is still undocumented.** `PipelineDeploy` runs before
  `BlueprintDeploy`, so a merged change that breaks `pipeline.yml` can leave the pipeline unable to
  deploy its own fix. Review makes this much less likely; it does not make it impossible. Someone
  should know how to deploy `pipeline/pipeline.yml` by hand before two days of parallel merging
  begins.

`tools/check` runs `cfn-lint` plus the bidirectional registry reconciliation, so it will catch a
malformed template or an unregistered blueprint before review. It will not catch a semantically valid
pipeline change that breaks the pipeline.

---

## 6. Open questions this changes

| Question | Status now |
| --- | --- |
| DevOps 2 — ARM64 build | **On the critical path.** Native `ARM_CONTAINER` recommended over cross-build. Needs Dan. |
| Q8 — synchronous reply | Stands, but the hybrid fallback and activity-`id` idempotency move from advisable to strongly recommended, because AgentCore adds a second cold start. |
| Q2 — blueprint naming | Brief points toward a generic `teams-bot`; still the product owner's call. |
| Q3 — capability | Now the main open question. AgentCore is mandated regardless, so this determines what the agent *does*, not whether it exists. |
| Retrieval route R1/R2/R3 | Unchanged and still open. AgentCore does not resolve the Bedrock Knowledge Base routing conflict. |
| Gateway key scope | Unchanged: must cover chat **and** embeddings, and the AgentCore execution role must be able to read it. |
| **New** — shared Build stage | Who adds it, and does Team E need it too? Ask Marty. |
