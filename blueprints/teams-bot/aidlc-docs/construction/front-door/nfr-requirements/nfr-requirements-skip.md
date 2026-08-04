# NFR Requirements — SKIPPED, with justification

**Date**: 2026-08-04
**Stage**: CONSTRUCTION — NFR Requirements (per-unit)
**Unit**: front door
**Decision**: **SKIP**, and consequently **NFR Design is also skipped**

## The skip criteria, checked rather than asserted

`core-workflow.md` gives NFR Requirements these criteria:

> **Execute IF**: Performance requirements exist · Security considerations needed · Scalability concerns
> present · Tech stack selection required
> **Skip IF**: No NFR requirements · **Tech stack already determined**

| Criterion | This unit |
| --- | --- |
| Performance requirements exist | **No SLA**, by decision. Workshop scale, tens of users |
| Security considerations needed | **Yes — but already handled.** The Security Baseline extension is enabled and was verified against the delivered artifacts at the Units Generation gate. That verification found three non-compliant rules, fixed two, and produced a dated exception for the third. Re-deriving security NFRs here would duplicate it |
| Scalability concerns present | No. Reserved concurrency 10, no state, no datastore |
| Tech stack selection required | **No — determined.** Python 3.13, arm64 Lambda container, CloudFormation, LiteLLM gateway, Bedrock `Retrieve`. Every one was fixed by an earlier decision or a repo constraint |

**And nine NFRs already exist**, in `requirements.md` §6, produced at comprehensive depth during
Requirements Analysis. A second set at unit level would restate them.

`core-workflow.md` also says NFR Design's own skip criterion is "NFR Requirements was skipped", so that
stage skips as a consequence rather than as a separate judgement.

## What the skip does NOT excuse

Skipping the stage does not make the existing NFRs correct. **Two of the nine have justifications that
the synchronous-delivery decision voided**, and that re-assessment is the real work this stage would
otherwise have done. It is recorded here rather than lost:

### NFR-4 (latency) — justification void

`requirements.md` says: *"No SLA. **Streaming removes the latency constraint**, so model choice is a
quality decision rather than a speed one."*

**Streaming was withdrawn.** So the 10–15 second Teams acknowledgement budget is live again, and model
choice is a **latency** decision once more. That is why `ModelId` defaults to `claude-haiku-4-5` and why
`MAX_TOKENS` is 1024 rather than 4096 — both are latency controls, not quality choices, and neither is
described that way in the requirement they implement.

### NFR-7 (cold starts) — justification void

`requirements.md` says: *"Acceptable, **because streaming decouples them from the acknowledgement
deadline**."*

Without streaming there is nothing decoupling them. A cold start now consumes the same budget the model
call needs, and **this compounds FR-9**, which is already marked VIOLATED because a synchronous handler
cannot acknowledge before working. Cold start plus retrieval plus generation, inside 10–15 seconds, is
the actual exposure.

**Mitigation available and not implemented**: keeping the function warm, or accepting that the first
message of a session may time out while subsequent ones do not. Neither is in the template.

### Consequence

**Both corrections belong in `requirements.md` §6, not here** — the requirement text is what a future
reader will quote, and it currently gives a reason that no longer holds. Recorded as outstanding work
rather than silently applied, because `requirements.md` was approved by the user and amending an
approved artifact is not this stage's call to make unilaterally.

## Logged

This skip and its justification are logged in `aidlc-docs/audit.md`, per the requirement that skipped
stages be recorded with their reasoning.
