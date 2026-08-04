# course-chatbot

The workshop MVP blueprint: an instructor asks for "a chatbot my students can ask questions
about my course material" and gets this. It bundles the Teams frontend, the document pipeline
and retrieval into **one** blueprint — composition of separate blocks is the next thing on the
roadmap, so this week one request deploys one blueprint.

Three tracks land here:

| Track | Owns | Where it goes |
|---|---|---|
| B — documents → searchable knowledge | Bedrock Knowledge Base: ingestion, chunking, retrieval tuning | `infra/` + retrieval in `src/` |
| C — Microsoft Teams chatbot | Azure Bot Framework front end, AWS backend | `infra/azure/` (Terraform) + `infra/` |
| D — how blocks talk, and stay separated | the seam between the three pieces | a decision in [`docs/decisions/`](../../docs/decisions/) + a working example here |

## ⚠️ Not deployable yet

Only `src/` exists. Nothing here deploys, and nothing here is advertised to a builder — by
design, not by omission:

- **No CloudFormation template.** `infra/` holds a README and nothing else.
- **No `Dockerfile` target.** `src/handler.py` says it runs as the root Dockerfile's
  `course-chatbot` target. The target name is right; **"root" is not** — `CLAUDE.md` states there is
  no root `Dockerfile`, and each component keeps its own in its own directory with the Build action's
  `CONTAINER_CONTEXT` pointing at it. So this one belongs at `blueprints/course-chatbot/Dockerfile`,
  and it has not been written.
- **No `pipeline/stacks.yml` entry and no pipeline actions**, so `tools/check` stays green.
- **No `blueprint.yaml`.** Deliberate: the manifest is the contract `blueprint_search` returns,
  and a manifest naming a template that doesn't exist would advertise a blueprint whose
  `deployment_create` produces a PR that cannot deploy. `pipeline/validate_stacks.py` now fails
  on that, so add the manifest in the same PR as the template — the way
  [`hello-world`](../hello-world/) has it.

## Wiring it up

Four steps, in this order. The middle two are what the PR checks enforce.

1. **`infra/course-chatbot.yml`** — Lambda (container image) + Function URL + transcript
   bucket + execution role. All four `cornell:*` tags on every resource; `DeploymentName` as a
   parameter, not a hardcoded name (see the note on `hello-world`'s `singleton: true`).
2. **Register it** in `pipeline/stacks.yml` as `deployed_by: pipeline`.
3. **Add the actions** in `pipeline/pipeline.yml` — a `Build` action for the image target and a
   `BlueprintDeploy` action passing every parameter explicitly. A registered template with no
   action deploys nothing while every stage reports success; `validate_stacks.py` fails on it
   rather than letting you find out from an empty console.
4. **`blueprint.yaml`** — the manifest, with `template:` pointing at step 1.

## What `src/handler.py` already does

One question in, one answer out, over a Function URL. Stateless: the conversation lives in the
client and is passed back on every request, so the function scales without session affinity.
The caller holds no model credentials — Bedrock is reached with the execution role.

It answers **only from its system prompt** and says so when a question needs course specifics.
That is the hole track B fills: there is no retrieval call in there yet, and the prompt tells
the model to refuse rather than invent a due date. Adding retrieval means a Knowledge Base
query before `_ask()` and grounding instructions in `SYSTEM_PROMPT`.

Transcripts are best-effort: a failed S3 write is logged and never costs a student a reply.

### What the template has to supply

| Variable | | |
|---|---|---|
| `MODEL_ID` | **required** | the handler raises `KeyError` at import without it |
| `AWS_REGION` | runtime-set | Lambda provides it; `BEDROCK_REGION` overrides for a cross-region model |
| `COURSE_NAME` | optional | goes into the system prompt; defaults to "this course" |
| `TRANSCRIPT_BUCKET` | optional | unset disables transcript writes entirely |
| `DEPLOYMENT_ID` | optional | recorded in each transcript — pass the real deployment id |
| `MAX_TOKENS` / `EFFORT` / `LOG_LEVEL` | optional | `EFFORT` defaults to `low`, the latency lever |

Plus IAM: Bedrock model invocation, and `s3:PutObject` scoped to the transcript bucket.

`requirements.txt` deliberately omits `boto3` — the AWS Lambda Python base image ships it — so
the `Dockerfile` target must build on that base image rather than the `uv` image the
`builder-mcp` target uses.

## Pinning

`requirements.txt` is a floating range, not a lockfile: a floor at the SDK version carrying the
Bedrock Messages API client, a ceiling to keep a major release out of an unrelated PR's image
build. A blueprint that reaches production wants a lockfile; this one is optimised for two days
of movement.
