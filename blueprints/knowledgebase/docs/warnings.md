# Warnings

Things that will cost someone time or money. Roughly in order of how likely they are to bite.

## The verifier is deliberately load-bearing — do not soften it

`IngestionVerifier` is the only thing standing between "green pipeline" and "empty knowledge
base." CloudFormation never ingests through a data source, so without it a stack that indexed
nothing reports `CREATE_COMPLETE`.

The tempting change, when a deploy goes red, is to stop asserting and just start the job. That
makes the red go away and makes the blueprint stop proving anything — permanently and invisibly,
because there is no second signal to notice it with. If the assertions are wrong, fix the
assertions; don't remove them.

## A failed verification turns the shared pipeline red

The verifier failing fails the stack, which rolls back and turns `main` red. That is the intent.

But every merge to `main` deploys to a **shared AWS account**, and every other track reads the
same pipeline. Our track's red is everyone's red.

**No feature branch rehearses it.** The Source stage tracks `BranchName: !Ref Environment`, so
only a branch whose name *is* an `Environment` value has a pipeline at all — and `Environment` is
capped at `[a-z0-9]{1,4}`. `b-knowledgeBase` cannot be one, so pushing to it deploys nothing.

**Anyone with account access can rehearse it by hand**, which is what the template's parameter
defaults are for:

```sh
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name aidlc-test-knowledgebase \
  --template-file blueprints/knowledgebase/infra/knowledgebase.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=test SourceCommitId=local-rehearsal
```

`Environment=test` is four characters, so every name derived from it is distinct from the `main`
ones — stack, both IAM roles, the managed policy, the Lambda, and the `/aidlc/test/knowledgebase/`
SSM path. Nothing collides with a deployed `main` stack. It indexes the same bucket, which is
fine.

**Delete the test stack afterwards.** It bills for storage while it exists.

Without account access, the first real execution is on `main` in the shared account, and only the
verdict is readable — not the failure. Either way, tell the other tracks before merging rather
than after.

## A failed *first* create blocks every subsequent merge

This is the sharpest edge here, and it is CloudFormation's, not ours.

If the stack fails while being **created** for the first time, it rolls back to
`ROLLBACK_COMPLETE`. A stack in that state **cannot be updated** — it has to be deleted before it
can be created again. The CodePipeline CloudFormation action has no `OnFailure: DELETE` option, so
it will not clean up.

So a failed first create means `KnowledgeBaseCloudFormation` fails on **every** later merge, with
an error about the stack's state rather than about whatever actually went wrong. Nobody on this
track can delete a stack. Unblocking it requires someone with account access.

Practically: **have someone from the platform team available for the merge that first creates this
stack.** Subsequent failures are ordinary update rollbacks and recover on their own.

## IAM propagation can fail the first create spuriously

The knowledge base is created moments after the role it assumes. IAM is eventually consistent, so
a first create can fail with a role-assumption or validation error that is pure timing and not a
configuration problem. CloudFormation retries some of these; it does not retry all of them.

If the first deploy fails with anything about the role not being assumable, the fix is to delete
the stack and merge again — see the previous warning about who can do that.

## `ConnectorParameters` is unlintable

`ManagedKnowledgeBaseConnectorConfiguration.ConnectorParameters` is free-form `Json` in the
CloudFormation schema. cfn-lint validates **nothing** inside it. Misspell `bucketName`, or write
`version: 1` where the API wants the string `"1"`, and `tools/check` passes clean while the deploy
fails in the shared account.

This is the single largest risk in the template, and the other reason the verifier exists. Treat
any edit inside that block as untested code.

## Chunking cannot be configured at all, and cfn-lint will not tell you

`ChunkingConfiguration` is **forbidden** with a managed embedding model. The API rejects it:

```
A chunking strategy cannot be specified with a managed embedding model.
Omit chunkingConfiguration to use the default.
```

The CloudFormation schema accepts the block, so `tools/check` passes clean and the failure lands at
`CREATE_FAILED` — which on a first create means `ROLLBACK_COMPLETE` and a blocked pipeline for every
track. An earlier version of this template shipped `ChunkingMaxTokens` and
`ChunkingOverlapPercentage` parameters for exactly this reason: they lint, they read as reasonable,
and they cannot work. This was caught by a by-hand `Environment=test` deploy, not by review.

Tuning chunking means `EmbeddingModelType: CUSTOM`, which means naming an embedding model and
provisioning a vector store.

`KnowledgeBaseConfiguration`'s type and embedding model are still create-only — changing either
replaces the knowledge base and loses the index.

`DataDeletionPolicy: RETAIN` softens the data-source case — the already-indexed vectors survive a
data-source replacement — but the new data source still ingests from zero.

## Managed knowledge base billing does not stop

Per-GB-stored plus per-retrieve, continuously, whether or not anyone is using it. **This is the
first thing in this repo that costs money while idle**, which is why no teardown story exists
anywhere here: S3 and SSM were near-free, so nobody needed one.

Practically: if the workshop ends and the stack stays up, it keeps billing. Someone with account
access has to delete `aidlc-main-knowledgebase`, and nothing in the pipeline will remind them.

## `SmokeQuery` couples the deploy to the corpus

If the bucket's contents change so that the default question is no longer answerable, **every
deploy fails** — including deploys that have nothing to do with this blueprint, because the whole
`BlueprintDeploy` stage goes red.

Change `SmokeQuery` in the same PR that changes the corpus. It is passed explicitly from
`pipeline/pipeline.yml`, so that means editing two files.

## The 900-second ceiling bounds corpus size

The verifier polls for up to 240s waiting for the data source and 550s waiting for ingestion,
inside a 900s Lambda timeout. One syllabus is seconds. A few thousand documents would time out
mid-verification and **fail a deploy that was actually fine** — the worst kind of failure, because
it looks like the thing it is monitoring broke.

Before this blueprint takes real volume, the shape has to change: a Step Functions wait loop, or
fire-and-forget plus a CloudWatch alarm on ingestion failure. Both give up the "green deploy is
the acceptance test" property, which is only worth giving up once someone has CLI access to check
things another way.

## A custom resource that never answers is worse than one that fails

CloudFormation waits for the custom resource's response. If the Lambda dies without sending one —
module-level import error, invocation timeout, dropped HTTP PUT — the stack does not fail, it
**waits**, and nobody on this track can cancel a stuck stack.

The handler is written against that specifically: clients and imports are built inside the `try`
so a startup failure still reports `FAILED`, every poll loop is bounded by
`get_remaining_time_in_millis()` rather than a fixed iteration count, botocore timeouts are pinned
short so one hung call cannot consume the budget, and `send()` retries.

If you edit the handler, preserve those four properties. Moving `boto3.client(...)` back to module
scope is the easy mistake — it reads as cleaner and converts a diagnosable red into a hang.

## Inline Lambda code is capped at 4096 characters

Hard CloudFormation limit. The handler is **3814 characters** — about 280 to spare. That is not
much: two or three added lines will exceed it, and the failure is a template that stops deploying.

There is **no S3-bundle fallback** without CLI access, so outgrowing the cap forces the
container-image path, which means wiring the currently-unused `ContainerBuildProject` and a Build
stage first. Check the count before adding to the handler:

```sh
uv run python -c "import re;t=open('blueprints/knowledgebase/infra/knowledgebase.yml').read();i=t.index('ZipFile: |');print(len('\n'.join(l[10:] for l in t[t.index(chr(10),i)+1:t.index('      Tags:',i)].rstrip().split(chr(10)))))"
```

## `BlueprintVersion` is duplicated and unchecked

The literal `0.1.0` appears in both the template default and `pipeline/pipeline.yml`'s
`ParameterOverrides`. Nothing validates that they agree, so bumping one and not the other makes
the `cornell:blueprint-version` tag lie. Bump both in the same PR.

## Two tagging gaps are real, not oversights

`aws resourcegroupstaggingapi get-resources --tag-filters
'Key=cornell:deployment-id,Values=aidlc-main-knowledgebase'` returns the knowledge base, both
roles, the managed policy and the SSM parameters. It does **not** return:

- **the data source** — `AWS::Bedrock::DataSource` has no `Tags` property at all. Mirrored into
  `/aidlc/main/knowledgebase/data-source-id` instead. Delete that parameter and the data source
  becomes invisible to inventory.
- **the ingestion bucket** — created outside IaC, untagged. See `assumptions.md`.

## `AWS::Bedrock::KnowledgeBase` takes `Tags` as a map

Not the usual list of `Key`/`Value` pairs. Same trap as `AWS::SSM::Parameter`, and every other
resource in this repo uses the list form, so copying a tag block between resources here will fail
in one direction or the other.

## This is close to the first `Type: MANAGED` CloudFormation anywhere

No AWS example uses it, so the template is assembled from the resource schema and the API docs
rather than from a working sample. cfn-lint clean is a weaker signal than usual here.
