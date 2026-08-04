# User Stories Assessment

Mandatory Step 1 of the User Stories stage. Run 2026-08-03, after the stage had already been
skipped once — this is the assessment that should have gated that skip.

## Request Analysis

- **Original Request**: build the Cornell Builder MCP — the conversational front door that
  turns plain-language intent into a governed deployment.
- **User Impact**: **Direct.** This *is* the builder's entire interface to the platform.
  There is no other surface; if the tools are wrong, the product is wrong.
- **Complexity Level**: **Complex.** Seven tools, three external systems (GitHub, AWS,
  MCP clients), two new data contracts, and a governance invariant that must hold for every
  tool forever.
- **Stakeholders**: builders (instructors, unit developers), review-gate approvers, platform
  operators (AI-SEI), security review, and Track E (inventory/cost) as a downstream consumer.

## Assessment Criteria Met

- [x] **High Priority — New User Features**: every tool is new user-facing functionality.
- [x] **High Priority — Multi-Persona System**: at least three distinct personas with
      conflicting needs (a builder wants speed; a reviewer wants scrutiny; an operator wants
      inventory and cost control).
- [x] **High Priority — Customer-Facing API**: the seven-tool surface is consumed directly by
      every builder's Claude client. SPEC C3 already treats renaming a tool as a contract
      change — that is API-grade commitment made without stories.
- [x] **High Priority — Cross-Team Project**: Tracks 0, B, C, D and E all touch or depend on
      this work.
- [x] **Medium Priority — Security Enhancements**: the credential-custody model (builder holds
      nothing, server holds everything) is a user-visible security posture.
- [x] **Benefits**: acceptance criteria for the demo, a defensible answer to "are these the
      right seven tools?", and shared understanding across six tracks.

## Decision

**Execute User Stories**: **Yes.**

**Reasoning**: this clears four separate High Priority indicators, any *one* of which triggers
ALWAYS-EXECUTE under the method. The original skip was not a judgement call that went the
other way — no assessment was performed at all. The concrete cost of the skip is already
visible: the tool surface was derived from a brainstorm list rather than from user needs, so
there is no test for whether it is complete or correct, and nothing defines "done" for
Tuesday's demo beyond "it ran".

## Expected Outcomes

- **Acceptance criteria** that make the demo pass/fail rather than vibes-based.
- **A completeness check on the tool surface** — stories will show which builder needs no tool
  serves (candidate gap: nobody can *list their own deployments*, and nobody can delete one).
- **Persona-driven validation of the `dry_run` UX**, which was inherited from a hosting
  decision rather than chosen for users.
- **Story→unit mapping** that makes Gate 3 (Units Generation) answerable, and with it the
  possibility of parallel work.
