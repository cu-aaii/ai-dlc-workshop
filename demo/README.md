# demo/

The workshop demo, driven from a terminal — the fallback for when the Teams bot isn't ready.

```sh
./demo/demo.sh              # the whole thing
./demo/demo.sh --fast       # no pauses, for a rehearsal
./demo/demo.sh --scene 3    # one scene
./demo/demo.sh --list       # what the scenes are
```

Five scenes: a builder asks in plain language → the catalog offers a governed blueprint → the
Builder MCP plans a deployment → the plan turns out to be a pull request → the deployed knowledge
base answers a real question.

The Teams bot is only the *client* in this story. Scenes 1–4 are the same tool calls the bot
would make, so replacing the bot with a terminal loses the chrome and none of the substance.

## What it does and does not touch

Every mutating call passes `dry_run=true`, so the script cannot open a PR, deploy, or delete.
That is a property of the tools, not of the script being careful — but the script also never
passes `dry_run=false`, so there is no flag to fumble on stage.

Scenes 1–4 need no AWS credentials and no network beyond a local `uv` cache. Scene 5 is the only
one that reads AWS (one SSM read, one `bedrock-agent-runtime` call) and it skips itself with an
explanation when there are no credentials, rather than failing mid-demo.

The demo talks to the real server over real MCP stdio, launched the same way `.mcp.json` launches
it, with `BUILDER_MCP_REPO_ROOT` pinned to this checkout so it demos *this branch's* catalog and
not `main`'s.

## Recording it with asciinema

Written against asciinema 3.x (`brew install asciinema`). A recording is the safe way to demo:
it cannot fail live, and it plays at whatever pace the room needs.

```sh
# Warm the caches first, so the recording doesn't open with uv downloading Python.
./demo/demo.sh --fast >/dev/null

asciinema rec demo/builder-path.cast \
  --title 'Cornell AI Platform — the builder path' \
  --idle-time-limit 2 \
  --command './demo/demo.sh'
```

`--idle-time-limit 2` caps every pause at two seconds on playback, which matters because the
script pauses deliberately between beats. `--overwrite` if you're re-recording.

Play it back, and rehearse the pacing before the room sees it:

```sh
asciinema play demo/builder-path.cast            # as recorded
asciinema play demo/builder-path.cast -s 1.5     # faster
```

During playback: `space` pauses, `.` steps forward one frame while paused — which is how you
talk over a specific line rather than racing the terminal.

A `.cast` is a JSON text file, so it diffs and reviews like source. `demo/*.cast` is gitignored
by default: a recording is an artifact of a rehearsal, and committing one means it goes stale
silently while looking authoritative. Commit one deliberately, if you want a fixed demo for a
session where the laptop might not cooperate.

### Before you upload one

`asciinema upload` publishes to asciinema.org, publicly, and the URL is not a secret once it
exists. The transcript contains the AWS account id, the ingestion bucket name, the SSM parameter
paths, and — if you record scene 5 — a knowledge base id and a real answer from the corpus. None
of that is a credential and most is already in this public repo, but "already in the repo" is not
the same decision as "posted to a third-party site," so make it on purpose.

Nothing in this directory uploads anything.

## Adjusting it

Environment variables, no editing required:

| Variable | Default | Effect |
|---|---|---|
| `DEMO_PAUSE` | `2` | Seconds between beats. `--fast` sets `0`. |
| `DEMO_QUESTION` | `What is the late homework policy?` | The question scene 5 asks. |
| `DEMO_ENVIRONMENT` | `main` | Which environment's SSM parameters scene 5 reads. |
| `DEMO_SHOW_SERVER_LOG` | unset | Set it to see the MCP server's stderr, for debugging. |
| `NO_COLOR` | unset | Set it to drop the ANSI colour. |

Scene 5's question has to be answerable from the corpus in `IngestionBucketName`, for the same
reason `SmokeQuery` does — see `blueprints/knowledgebase/docs/warnings.md`.

Scene 5 uses `bedrock-agent-runtime retrieve`, and there is no model parameter to set, because
**`RetrieveAndGenerate` is not supported on a managed knowledge base** — it fails with *"This
operation is not supported for managed knowledge bases."* Retrieval returns passages; turning
them into prose is the consuming chatbot's job. The blueprint's own deploy-time verifier uses
`retrieve` for the same reason.

## Verified against the live account

Run on 2026-08-04 against `890349359349` / `us-east-1`, with `AWS_PROFILE=ai-dlc-workshop`:
all five scenes, including scene 5 reading knowledge base `I7JT3U0RH7` out of SSM and retrieving
a real passage from the CS1112 syllabus.
