# docs/decisions/

Decisions with consequences, one file each, `NNNN-short-title.md`. Not a design doc folder — a
record of choices made on purpose, so that six months from now the question is "why did we choose
this" and not "did anyone choose this?"

The distinction is the useful one from
[`docs/aidlc/builder-mcp/STAGE-GATES.md`](../aidlc/builder-mcp/STAGE-GATES.md): a decision
**chosen** was checked by somebody; a decision **walked into** was not. Writing one down takes ten
seconds. Track A shipped with `dry_run` as its confirm UX because choosing AgentCore silently
chose a stateless transport, which silently ruled out MCP elicitation — a consequence chain nobody
decided end to end. That is what this directory is for.

## Format

Keep it to one page. Anything longer is a design doc and belongs with the code it describes.

```markdown
# NNNN — <the decision, as a statement>

**Status**: proposed | accepted | superseded by NNNN
**Date**: YYYY-MM-DD
**Deciders**: who was actually in the room

## Context
What forced a choice. What constrained it.

## Decision
What we're doing, in the present tense.

## Alternatives
What else was on the table, and the specific reason each lost. This is the section
that has value later — "we didn't consider it" and "we considered it and it was worse"
are different answers to the same future question.

## Consequences
What this makes easy, what it makes hard, and what it commits us to. Name the thing
that would make us revisit it.
```

## First one up

Track D — **what the blocks in a deployment use to talk to each other, and how one unit's
deployment is prevented from reaching another's.** It is the hardest open question in the workshop,
its deliverable is explicitly "a decision with the trade-offs written down, plus a working
example," and the whole roadmap past this week (composing separate blocks instead of one bundled
blueprint) depends on the answer. The working example goes in
[`blueprints/course-chatbot/`](../../blueprints/course-chatbot/); the trade-offs go here.

Also worth recording, because each is currently load-bearing and unratified: the blueprint
manifest schema, the choice of `deployed_by: pipeline` mirroring by hand rather than generating
pipeline actions from `stacks.yml`, and whichever shape track E picks for a unit's view of its own
deployments.
