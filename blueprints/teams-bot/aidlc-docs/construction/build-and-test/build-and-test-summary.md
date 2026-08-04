# Build and Test — summary

**Generated**: 2026-08-04
**Stage**: CONSTRUCTION — Build and Test (the final CONSTRUCTION stage)
**Unit**: front door

## The documents

| Document | Covers | Verified? |
| --- | --- | --- |
| [`build-instructions.md`](build-instructions.md) | What is built, how to build the arm64 image locally before merging, the lock-file loop, how the image reaches a deploy | Commands run, except `docker buildx` — Docker was unavailable |
| [`unit-test-instructions.md`](unit-test-instructions.md) | The 42 tests, what each file protects, what the suite deliberately does not reach | Command run |
| [`integration-test-instructions.md`](integration-test-instructions.md) | Everything from the gateway `curl` through to messaging the bot in Teams. **Seven numbered tests** | **Nothing verified — never deployed** |

**No separate `performance-test-instructions.md`.** There is no latency or availability SLA and no load
test is warranted at workshop scale, so a standalone document would say only that. The one performance
property that *is* functional — the Teams 10–15 second acknowledgement budget, which FR-9's violation
makes cover the whole round trip — is in `integration-test-instructions.md` §Performance, next to the
command that measures it.

## Where the confidence actually is

This is the useful summary, and it is lopsided on purpose.

**Well covered — 42 tests, no AWS, no network:**

- JWT validation: forged signatures, `alg: none`, wrong audience, wrong issuer, expiry inside and
  outside the 300s skew, and **both FR-8a `serviceurl` cases** — the control the n8n prototype had
  present and non-functional
- The always-200 contract, including an exception injected below the handled paths
- Retrieval degrading to no-passages rather than raising, and query truncation at the 10,000-char cap
- Log-id bounding: newlines cannot forge a log line, and the URL-bound id is left raw so replies do not
  break
- Activity parsing: the `28:` self-greeting filter, absent `text`, both conversation-id formats

**Not covered at all, and no unit test can reach it:**

| Assumption | Status |
| --- | --- |
| The image builds for arm64 | **Never built once.** Docker unavailable while authoring |
| The Lambda runs and answers in Teams | **Never deployed** |
| The gateway accepts this request shape | **Never called.** A wrong auth header is a silent `401` |

**Those three are the demo risk in its entirety.** Step 0 of the integration document tests the third
one with a five-second `curl`, which is the highest-value action available before merging.

## Run order

```sh
# 1. Riskiest assumption, cheapest test -- integration-test-instructions.md Step 0
curl ... /v1/messages          # expect 200

# 2. Everything that needs no AWS
bash tools/check
uv run --python 3.13 --with 'PyJWT[crypto]>=2.8,<3' --with 'anthropic>=0.92,<2' \
    --with boto3 --with pytest pytest blueprints/teams-bot/tests -q

# 3. arm64 image, locally -- build-instructions.md
docker buildx build --platform linux/arm64 --target teams-bot -t teams-bot:local \
    blueprints/teams-bot

# 4. Merge. Then START A SECOND EXECUTION -- the first will not deploy this stack
aws codepipeline start-pipeline-execution --name aidlc-main-pipeline

# 5. Inject both secrets, point Azure at the FunctionUrl, then the seven tests
```

**Steps 1 to 3 need no AWS access and no merge.** They are the whole of what can be proven from a
laptop, and they should all pass before the PR is opened.

## Three failures that look like something else

Each has cost time already, in this repository or in the prototype.

1. **A green pipeline that deployed nothing.** A CodePipeline execution uses the structure in place
   when it *started*, so the merge that adds a Build action updates the pipeline and skips the new
   action while reporting every stage green. **Expected. Start a second execution.**
2. **A green deploy that answers nothing.** Both secrets are created with `GenerateSecretString`
   placeholders, so the bot authenticates with a random string until they are injected. CloudFormation
   looks perfect; CloudWatch says `401`.
3. **A `Forbidden` from `az`, an hour in.** The Bot Service resource and the Entra app registration can
   live in different tenants, by design. Each command needs the right login.

## Stage assessment

**This is the one CONSTRUCTION stage with no retrospective problem.** Functional Design, NFR
Requirements, NFR Design, Infrastructure Design and Code Generation all ran after the code they
describe. Build and Test does not: the 42 tests exist, `tools/check` is green, and what is missing —
the end-to-end path through Teams — is genuinely the next thing to do rather than something skipped.

**What would most improve confidence, in order:**

1. Run integration Step 0. Five seconds, retires the riskiest assumption.
2. Build the image locally. Proves arm64 and dependency resolution with no AWS.
3. Deploy and run the seven tests, particularly **test 6** — the refusal on ungrounded material, which
   is the guardrail working and the best thing to show an audience.
4. Restore the worker Lambda. Closes FR-9, FR-11, FR-16 and FR-17 together, and makes the
   acknowledgement budget stop being a functional risk. Ahead of AgentCore, which adds capability where
   this fixes correctness.
