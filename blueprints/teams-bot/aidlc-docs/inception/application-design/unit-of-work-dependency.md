# Unit of Work Dependencies — Track C, the Teams front end of `course-chatbot`

**Generated**: 2026-08-04
**Stage**: INCEPTION — Units Generation (Part 2: Generation)
**Companion to**: `unit-of-work.md` — read its **Amendment — delivery status** section first, because
four of the ten units below were withdrawn or deferred after the units were defined.

---

## What this document is for

With mob-style serial execution and one PR, these are **not** deployment dependencies between
independently shippable services. Every unit lands in the same stack. What the matrix records is
narrower and more useful: **which unit cannot be started, or cannot be demonstrated, until another is
done.**

That distinction matters because the two are different. `U6` (the agent) could be *written* against a
JSON payload with nothing else in place, but it cannot be *deployed* without `U1`. Conflating those is
what makes a dependency graph look more constraining than the work actually is.

---

## Dependency matrix

Rows depend on columns. **B** = blocks starting, **D** = blocks demonstrating, **·** = no dependency.

| ↓ needs → | U0 | U1 | U2 | U3 | U4 | U5 | U6 | U7 | U8 | U9 | Ret |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **U0** Microsoft chain | — | · | **D** | · | · | · | · | · | · | · | · |
| **U1** Build capability | · | — | · | · | · | · | · | · | · | · | · |
| **U2** Blueprint skeleton | · | **B** | — | · | · | · | · | · | · | · | · |
| **U3** Inbound trust | · | · | **B** | — | · | · | · | · | · | · | · |
| **U4** Idempotency | · | · | **B** | **B** | — | · | · | · | · | · | · |
| **U5** First reply | **B** | · | **B** | **B** | · | — | · | · | · | · | · |
| **U6** Agent runtime | · | **B** | **B** | · | · | · | — | · | · | · | · |
| **U7** Streaming | · | · | · | · | · | **B** | **B** | — | · | · | · |
| **U8** Scope expansion | **B** | · | · | · | · | **B** | · | · | — | · | · |
| **U9** Hardening | · | · | **B** | · | · | · | · | · | · | — | · |
| **Ret** Retrieval | · | · | **B** | · | · | · | · | · | · | · | — |

### Text alternative

Reading each unit's prerequisites in prose, since the matrix above is a visual aid rather than the
record:

- **U0 (Microsoft identity chain)** has no prerequisite for *starting* — it is entirely non-AWS. It
  cannot be *finished* until U2 exists, because the Azure Bot resource's messaging endpoint needs the
  function URL. That is a demonstration dependency, not a starting one, which is why U0 can run
  concurrently with the AWS work despite appearing late in any ordering.
- **U1 (build capability)** depends on nothing. It is the only unit with no prerequisite at all, which
  is why it goes first.
- **U2 (blueprint skeleton)** cannot start until U1, because a Lambda that runs a container image needs
  an image to run.
- **U3 (inbound trust)** cannot start until U2, because there is nothing to validate a request against
  until a function is receiving requests.
- **U4 (idempotency and hand-off)** needs U2 for the table and U3 for the validated activity whose id is
  the idempotency key.
- **U5 (first reply)** needs U2 and U3 on the AWS side, and **U0** on the Microsoft side — it is the
  first unit that requires both halves, which is exactly why it is the first mob checkpoint.
- **U6 (agent runtime)** needs U1 to build its image and U2 for the role and stack to attach it to. It
  needs **neither U3 nor U5**: the agent is channel-agnostic and testable with a JSON payload, which is
  the entire payoff of that design decision.
- **U7 (streaming delivery)** needs U5 for the delivery path it replaces and U6 for something producing
  a stream of tokens to deliver.
- **U8 (scope expansion)** needs U5 for a working reply path and U0 for the manifest that declares the
  new scopes.
- **U9 (hardening)** needs U2, because retention, alarms and concurrency are properties of resources U2
  creates.
- **Retrieval** needs U2 for the role and the deploy-time parameter resolution. It needs nothing else —
  notably not U6, which is why it could ship in step 1.

---

## The critical path

**U1 → U2 → U3 → U5**, with **U0 joining at U5**.

Four units, and everything else hangs off U2. That is the shape worth noticing: **U2 is the
articulation point.** Six of the eleven rows depend on it directly. A problem in U2 stops everything;
a problem anywhere else stops one branch.

**What is deliberately *not* on the critical path:**

- **U6 (the agent)** — it hangs off U1 and U2 but nothing hangs off it except U7. This is the
  channel-agnostic decision paying off: the most interesting engineering in the blueprint is also the
  most isolated.
- **Retrieval** — one edge, to U2. Which is why it could be added late, after the knowledge base turned
  out to be ready, without disturbing anything.
- **U9 (hardening)** — one edge, to U2. Also why it is the easiest thing to drop under time pressure,
  and why the Part 1 plan split the cheap parts inline rather than leaving them all here.

---

## Cross-track dependencies

These are not unit-to-unit and are easy to miss for exactly that reason.

| Dependency | On | Nature | Status |
| --- | --- | --- | --- |
| **Knowledge base id** | Track B's `knowledgebase` blueprint | **Hard, at deploy time.** Resolved from the SSM parameter it publishes, via `AWS::SSM::Parameter::Value<String>` | **Satisfied** — deployed, and the syllabus is indexed |
| Deploy ordering | Track B | `CourseChatbotCloudFormation` runs at **`RunOrder: 2`** so the parameter exists before this stack resolves it | Satisfied |
| Shared template file | Tracks B and D | `infra/course-chatbot.yml` is nominally shared. In practice Track B shipped standalone, so this is currently uncontended | Watch |
| `pipeline.yml` | Every track | High-contention file that deploys on merge | Watch |
| Gateway service key | Gateway operator | Runtime, not deploy — the stack creates the secret resource with a placeholder | **Outstanding** |
| Entra client secret | Whoever holds dev-tenant admin | Runtime, same pattern | **Outstanding** |

**The two outstanding items are both runtime, and both fail the same quiet way.** The stack deploys
green, the bot answers nothing, and the CloudWatch logs say `401`. Neither is a deploy-time gate, which
is precisely why they are worth listing as dependencies rather than as setup steps.

---

## What the delivered subset means for this matrix

Given the amendment in `unit-of-work.md` — U4 and U7 withdrawn, U6 deferred, U0 and U8 not built —
the graph that actually executed was:

**U1 → U2 → U3 → U5**, plus **Retrieval** hanging off U2, with U0 substituted by reusing the existing
Azure registration.

Two consequences follow, and both are edges that *no longer exist* rather than work that was skipped:

1. **U4's edge into U3 is gone**, so nothing consumes the activity id as an idempotency key. The id is
   still threaded through as the correlation id, so restoring the guard is additive rather than a
   rework.
2. **U7's edges into U5 and U6 are gone**, and with them the delivery dispatcher. U8 depended on U5
   *through* that seam; without it, U8 becomes a change to the reply path rather than a third strategy
   alongside two existing ones. **That is the one place where deferring made later work harder rather
   than merely later.**
