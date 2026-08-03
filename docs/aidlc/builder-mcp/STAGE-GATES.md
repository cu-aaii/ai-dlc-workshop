# Stage Gates — what we chose vs. what we walked into

The mob's front door to the AI-DLC workflow for `builder-mcp`. For each stage: **what the
method offers**, **what we actually chose**, and — the important column — **what we walked
into** without anyone deciding it.

A *walked-into* decision is not necessarily wrong. It is a decision nobody made on purpose,
which means nobody checked it. Ratifying one takes ten seconds; discovering it in production
takes a week.

**Four gates are open.** They are listed at the bottom in the order the method runs them.

---

## 🔵 INCEPTION

### Workspace Detection — ✅ done

| | |
|---|---|
| **Available** | greenfield vs brownfield; where AI-DLC docs live |
| **Chosen** | brownfield (deploy path exists) |
| **⚠️ Walked into** | docs live at `builder-mcp/aidlc-docs/`, not repo root. My call, unratified — six tracks share this repo and a root `aidlc-docs/` would collide. If other tracks put theirs at root, the repo ends up inconsistent. |

### Reverse Engineering — ✅ skipped, defensibly

| | |
|---|---|
| **Available** | analyze the existing system, or rely on existing docs |
| **Chosen** | skipped — `CLAUDE.md`, `README.md`, `pipeline/README.md` already document the deploy path |
| **⚠️ Walked into** | nothing significant |

### Requirements Analysis — ⚠️ done with defects

| | |
|---|---|
| **Available** | minimal / standard / comprehensive depth; extension opt-ins |
| **Chosen** | standard depth; 9 questions answered by the mob (Q1 A, Q2 AgentCore, Q3 all-six-today, Q5 skip, Q8 Python, Q9 spec + 6 audiences) |
| **⚠️ Walked into** | **(a)** Three extension opt-ins — security, resiliency, property-based testing — were **never presented**. Mandatory at workflow start. → **GATE 1** <br> **(b)** Product-proposal decisions **D1–D4** treated as settled. That document says of itself: a proposal for discussion, not a plan of record. The mob never voted on them. <br> **(c)** **Q4 was never answered** — I assumed `restart_deployment` = retry-at-current-version. <br> **(d)** **Q6 and Q7 were answered "A, I think"** — tentative, never firmed up. |

### User Stories — ❌ skipped, never ratified

| | |
|---|---|
| **Available** | five breakdown approaches: user-journey, feature, persona, domain, epic |
| **Chosen** | *nothing* — I skipped the stage |
| **⚠️ Walked into** | The seven tools came from the mob's **brainstorm list**, not from stories. Consequence: **there are no personas and no acceptance criteria**, so we cannot say whether these are the *right* seven tools, and nothing defines "working" for UAT. The method says ALWAYS execute for new user-facing features with multiple personas — this has at least three. → **GATE 2** |

### Workflow Planning — ⚠️ done retroactively

| | |
|---|---|
| **Available** | which stages execute, at what depth |
| **Chosen** | reconstructed after the fact in [execution-plan.md](inception/plans/execution-plan.md) |
| **⚠️ Walked into** | the plan describes what already happened rather than steering it. Its value now is the honest map, not the planning. |

### Application Design — ❌ skipped, never ratified

| | |
|---|---|
| **Available** | component boundaries, methods, service-layer design |
| **Chosen** | *nothing* |
| **⚠️ Walked into** | Five modules (`catalog`, `github_ops`, `aws_ops`, `patching`, `spec_export`) — my design alone. Also the **`dry_run` two-step as the confirm UX**, which is a consequence chain nobody chose end-to-end: AgentCore → stateless transport → no MCP elicitation → dry_run. Choosing AgentCore silently chose the UX. → **GATE 3** |

### Units Generation — ❌ skipped, never ratified

| | |
|---|---|
| **Available** | one unit, or decompose into several independently buildable units |
| **Chosen** | *nothing* |
| **⚠️ Walked into** | **One unit.** This is the expensive one: a single unit means one person builds it. Decomposed — catalog / GitHub integration / AWS ops / spec export — several people could have built in parallel. It is *why* Track A had one keyboard on it. → **GATE 3** |

---

## 🟢 CONSTRUCTION

### NFR Requirements — ❌ skipped — **the real gap**

| | |
|---|---|
| **Available** | latency, throughput, concurrency, availability, security targets |
| **Chosen** | *nothing* |
| **⚠️ Walked into** | **No stated targets of any kind.** How many builders at once? How fast must `blueprint_search` return? What happens at the GitHub API rate limit (60/hr unauthenticated — which is what the catalog loader uses today off-repo)? The backlog's speed-check item exists precisely because there is no number to check against. → **GATE 4** |

### Functional / NFR / Infrastructure Design — ⚠️ done as code

| | |
|---|---|
| **Chosen** | AgentCore stack, IAM role, Cognito authorizer, pipeline wiring |
| **⚠️ Walked into** | Cognito client-credentials (my ⭐; P2 unanswered), Runtime-only topology (P1 unanswered), `us-east-1`, shared ECR, arm64. All are live in a template that is in an open PR. |

### Code Generation — ⚠️ out of order

| | |
|---|---|
| **Available** | Part 1 plan with checkboxes → **approval gate** → Part 2 generate |
| **⚠️ Walked into** | I generated directly. The mob never saw a code plan before the code existed. |

### Build and Test — ✅ done

22 tests green · HTTP smoke stateful *and* stateless · arm64 image builds · `cfn-lint` clean.
**⚠️ Walked into**: tests cover pure logic only; GitHub and AWS edges are dry-run paths only.

---

## 🟡 OPERATIONS

Handed off to Marty per [deploy/HANDOFF.md](../../../packages/builder-mcp/deploy/HANDOFF.md). **Nothing is deployed.**
PR #9 targets `builder-mcp`, not `main`, so merging it will not deploy either.

---

## The four open gates, in method order

| Gate | Stage | Question file | Blocks |
|---|---|---|---|
| **1** | Requirements Analysis (defect) | [extension-opt-in-questions.md](inception/requirements/extension-opt-in-questions.md) | Everything — these are meant to be enforced from workflow start |
| **2** | User Stories | [story-generation-plan.md](inception/plans/story-generation-plan.md) | Acceptance criteria; whether the 7 tools are the right 7 |
| **3** | Application Design → Units Generation | *(opens after Gate 2)* | Parallel work; module ownership |
| **4** | NFR Requirements | *(opens after Gate 3)* | Speed check, cost spec, rate-limit behaviour |

Gates 1 and 2 are open now and can be answered in the room. Gate 3 needs stories to map units
onto (the method makes Application Design a hard prerequisite of Units Generation). Gate 4 is
last because targets are cheapest to state once the units exist.
