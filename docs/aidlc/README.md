# docs/aidlc/ — the AI-DLC record

One subdirectory per track. These are **historical artifacts**: they record how something was
built, in the vocabulary of the AI-DLC methodology the workshop teaches. They are not a task
list, and nothing here gates any work.

| Track | Directory | Produced |
|---|---|---|
| A — Cornell Builder | [`builder-mcp/`](builder-mcp/aidlc-state.md) | Aug 3 2026: inception through construction |

## Read these as a record, not a backlog

`builder-mcp/aidlc-state.md` and `builder-mcp/STAGE-GATES.md` were written mid-workflow, so
they are phrased in the present tense of that moment — four gates "OPEN", two inception stages
"REOPENED", stories "awaiting mob approval". **Construction finished.** The package is written,
tested and documented; that framing is a snapshot of where the method stood on the morning of
day one, not the state of the code.

What those documents are still good for is the honest column: `STAGE-GATES.md` separates what
the mob *chose* from what it *walked into* without anyone deciding — one unit instead of four
(which is why Track A had one keyboard on it), `dry_run` as the confirm UX arriving as a
consequence of picking AgentCore, no NFR targets of any kind. Those are real and worth reading
before the next track repeats them. The gate numbers are not.

## Paths in these documents predate the monorepo

They were written when the package lived at `builder-mcp/` and these docs at
`builder-mcp/aidlc-docs/`. Prose references like `builder-mcp/src/builder_mcp/server.py` now
mean `packages/builder-mcp/src/builder_mcp/server.py`. Only the clickable links were repointed
— rewriting the bodies of documents being kept as a record would bury the change that mattered
under a hundred lines of path churn.

## Where the live documentation is

| | |
|---|---|
| Contracts that must not drift | [`packages/builder-mcp/SPEC.md`](../../packages/builder-mcp/SPEC.md) |
| Decisions, gotchas, glossary | [`builder-mcp/PROJECT-KNOWLEDGE.md`](builder-mcp/PROJECT-KNOWLEDGE.md) |
| Deployment runbook | [`packages/builder-mcp/deploy/HANDOFF.md`](../../packages/builder-mcp/deploy/HANDOFF.md) |
| Known gaps and next work | [`packages/builder-mcp/BACKLOG.md`](../../packages/builder-mcp/BACKLOG.md) |

`PROJECT-KNOWLEDGE.md` is the exception to "historical" — it is a decision log that stays
useful, which is why it lives here rather than in an archive.

## Starting a track's own record

Make `docs/aidlc/<track>/`. Don't put one at the repo root: six tracks share this repo and a
single root-level `aidlc-docs/` was the collision that sent Track A's docs under its component
in the first place.

The methodology itself is vendored and read-only — see the AI-DLC section of the repo
`CLAUDE.md` for how it is invoked and why it is invocation-gated.
