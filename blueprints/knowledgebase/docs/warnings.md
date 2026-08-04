# Warnings

Things that will cost someone time or money. Roughly in order of how likely they are to bite.

## A bad data source HANGS the deploy instead of failing it

**Read this before editing `ConnectorParameters`.** It is the worst failure mode in this blueprint,
and it is worse than the red pipeline everything else here is designed around.

A malformed connector body does not fail the stack. Bedrock marks the data source `FAILED` within a
second, and **CloudFormation keeps reporting `CREATE_IN_PROGRESS`** — observed for over twenty
minutes against a data source that had already failed. The CloudFormation handler does not appear to
treat `FAILED` as terminal.

So the deploy does not go red. It sits there. `BlueprintDeploy` stalls, and because every track
shares this pipeline, **nobody's blueprint deploys until it times out or someone with account access
intervenes.** The verifier never runs, so none of its five assertions help — the data source it
depends on never reaches `AVAILABLE`.

The only way to see it is from outside CloudFormation:

```sh
aws bedrock-agent list-data-sources --knowledge-base-id <id>          # status: FAILED
aws bedrock-agent get-data-source --knowledge-base-id <id> \
  --data-source-id <ds> --query 'dataSource.failureReasons'
```

Which is exactly what nobody on this track can do. Hence: **rehearse any `ConnectorParameters` edit
with a by-hand `Environment=test` deploy, and check the data source status in Bedrock rather than
trusting the stack.** `tools/check` cannot see inside that block at all.

## `bucketOwnerAccountId` is required, and the docs say otherwise

The AWS managed-connector reference marks `connectionConfiguration.bucketOwnerAccountId`
**"Conditional — required for cross-account access."** That is wrong. Omitting it for a bucket in
the *same* account fails validation:

```
1 validation error detected: Value at 'connectionConfiguration.bucketOwnerAccountId'
failed to satisfy constraint: Member must not be null
```

An earlier version of this blueprint omitted it deliberately, with a paragraph in
`docs/decisions.md` explaining why omitting it was correct. Every AWS example includes it; that was
the signal, and reasoning from the reference table beat reading the examples. It is now
`!Ref 'AWS::AccountId'` and should stay there.

This failed via the hang above, not via a red stack.

## Enabling SharePoint makes an Entra certificate a shared-pipeline dependency

`EnableSharePointSource=true` is the single largest blast-radius change available in this blueprint,
and it is one parameter.

With it on, every merge to `main` — every track's merge, not just this one — depends on things that
live outside this repo and outside AWS: an Entra app registration, an admin-consented
`Sites.Selected` grant on **both** Microsoft Graph and the SharePoint REST API, a per-site
permission grant, a `.p12` in S3, and a certificate that has not expired. When any of those lapses,
the SharePoint ingestion job fails, the verifier fails the stack, and `BlueprintDeploy` is red for
everyone. That is the verifier working correctly, which is exactly what makes it expensive.

**The certificate expiry is the one that will actually bite**, because it is a date rather than a
change: nothing in this repo watches it, and the deploy that breaks will be someone else's merge
weeks later. Rotation is a Terraform apply plus a re-sync — see `sharepoint-source.md`.

Flip the flag in its own PR, after a by-hand `Environment=test` rehearsal. Not in a PR that does
anything else.

## The SharePoint smoke query can pass on S3 content

`SharePointIngestionVerifier` asserts on the SharePoint data source's own ingestion statistics, so
an empty SharePoint source cannot go green. But its fifth assertion is a `bedrock:Retrieve` call,
and retrieval spans the **whole knowledge base** — there is no per-data-source filter in play here.

So a `SharePointSmokeQuery` that the S3 syllabus can also answer makes that assertion prove nothing
about SharePoint. The current default, `What does the syllabus say about attendance?`, is
**exactly that mistake** and is a placeholder: it names a document type that exists on both sides.
Replace it with a question only the SharePoint corpus can answer in the PR that enables the source.

## Narrowing SharePoint scope does not purge, and there is no document-level delete

Turning `crawlPages` off — or dropping a site from `siteUrls` — means the connector no longer
*sees* those documents, so it cannot diff them as deleted. **Observed**: the post-change sync
reported `numberOfDocumentsScanned: 1, numberOfDocumentsDeleted: 0` and the two removed
`SitePages/*.aspx` documents were still returned by `retrieve` afterwards. A narrowed scope reads
as a successful change and leaves the old content answering queries.

The obvious fix is unavailable:

```
ValidationException: Invalid data source type [SHAREPOINTV3] provided.
Only S3 and Custom data source supported for document level request.
```

That rejects `list-knowledge-base-documents` too, so the indexed set cannot be enumerated that way
either. The only purge is deleting and recreating the data source, which is why the SharePoint
source carries `DataDeletionPolicy: DELETE` while the S3 one carries `RETAIN`. **Do not "fix" that
inconsistency** — flipping SharePoint to `RETAIN` makes every stale chunk permanent for the life of
the knowledge base.

Consequence worth planning for: a template change that *replaces* the SharePoint data source
empties the SharePoint half and re-ingests from zero, and its data source id changes.

## Two SharePoint errors are indistinguishable from a wrong secret

Both of these produce `"secret has an invalid format or missing values"`:

- the secret's keys are not exactly `clientId` and `certificatePassword` (camelCase, for
  `ENTRA_ID_APP_ONLY`), and
- the knowledge base is customer-managed rather than `MANAGED`, in which case Bedrock is failing
  partway down a path it cannot service and the secret is irrelevant.

The error names the secret in both cases. Check the knowledge base type first — it is one
`get-knowledge-base` call, and a managed one echoes back
`{"type": "MANAGED", "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"}}` with
no `storageConfiguration` at all. Rewriting a correct secret is the default failure mode here and
it costs hours.

## Turning ACL crawling on triples the consent ask

`aclEnabled: false` in `ConnectorParameters` is not a default worth flipping casually. With ACL and
identity crawling on, Bedrock demands `GroupMember.Read.All` and `User.Read.All` on top of a
`Sites` scope — tenant-wide user and group profile reads, which is a much bigger consent
conversation than one site's documents.

This is not hypothetical: the account's earlier quick-start SharePoint data source failed **every**
ingestion job it ever ran on exactly that, while reporting `status: AVAILABLE` throughout. See
`decisions.md`.

## A scheduled sync fails invisibly, by construction

`EnableScheduledSync=true` starts ingestion jobs on a timer through an EventBridge Scheduler
universal target. It **cannot check the result, ever**, and that is a property of Scheduler rather
than a gap in the template: it refuses API actions whose names begin with a read-only prefix, and
the list includes `get`, `list`, `retrieve` and `invokeModel`. `GetIngestionJob` and the smoke query
are both unreachable from a schedule.

So a knowledge base whose scheduled syncs have failed every week for a month looks exactly like one
whose syncs all succeeded. Nothing goes red. Nothing is written down —
`/aidlc/main/knowledgebase/sync-schedule` records the configuration and the string
`outcomes=not-recorded` for that reason.

**The trap next to it:** `/aidlc/main/knowledgebase/last-ingestion-result` and its SharePoint twin
*are* real ingestion statistics — from the last **deploy**. They will happily show a healthy sync
from three weeks ago while every scheduled run since has failed. Read `commit=` in the value.

What this does *not* do is weaken the deploy: the schedule is not in the deploy path, so it cannot
make a red deploy green. A green deploy remains the only evidence that this knowledge base answers.

If it matters that scheduled syncs work, the shape has to change — Step Functions, which can poll
and assert. See `decisions.md`.

## Scheduled SharePoint syncs are not a certificate-expiry alarm

It is tempting to reason that a weekly SharePoint sync will catch a lapsed certificate early. It
will *encounter* it and then throw the finding away, per the warning above.

The thing that actually catches an expired certificate is the next deploy — which means it surfaces
as a red `BlueprintDeploy` on somebody else's merge, at whatever moment they happen to merge. The
schedule does not change that. Put the expiry date somewhere a human will see it.

## The universal-target ARN is validated by nothing

`arn:aws:scheduler:::aws-sdk:bedrockagent:startIngestionJob` — the `{service}` segment is the **SDK
service identifier**, which AWS documents as sometimes differing from the endpoint prefix
(`bedrockagent`, not `bedrock-agent`). cfn-lint checks the ARN's shape and nothing about whether that
service or action exists.

So a typo there deploys clean, passes `tools/check`, and fails at 07:00 on a Monday with nobody
watching — the same class of unlintable string as `ConnectorParameters`, with a worse observation
story. `RetryPolicy` is pinned to 3 attempts over 900s because Scheduler's default is 185 attempts
across 24 hours, which turns one structural mistake into a day of retries.

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

If that ever fails on template size, see the size warning below — and if you do reach for
`--s3-bucket`, **never point it at the ingestion bucket.** A template staged there becomes a document
the knowledge base indexes, and the next smoke query starts retrieving CloudFormation YAML.

`Environment=test` is four characters, so every name derived from it is distinct from the `main`
ones — stack, both IAM roles, the managed policy, the Lambda, and the `/aidlc/test/knowledgebase/`
SSM path. Nothing collides with a deployed `main` stack. It indexes the same bucket, which is
fine.

**Delete the test stack afterwards.** It bills for storage while it exists.

Without account access, the first real execution is on `main` in the shared account, and only the
verdict is readable — not the failure. Either way, tell the other tracks before merging rather
than after.

## Changing `RetrievalPolicy`'s document rolls the stack back

`AWS::IAM::ManagedPolicy` **replaces** on a `PolicyDocument` change, and this one carries an explicit
`ManagedPolicyName`. So CloudFormation creates the replacement before deleting the original, and the
create fails against the name the original still holds:

```
A policy called aidlc-main-knowledgebase-retrieval already exists.
Duplicate names are not allowed.
```

This happened on `main`: a one-line edit dropping `bedrock:RetrieveAndGenerate` — an action a managed
knowledge base does not support — failed `BlueprintDeploy` and left `UPDATE_ROLLBACK_COMPLETE`. Red
for every track, and the change did not land.

Editing that policy therefore takes a PR that also **renames** it, and the rename has a second
precondition: IAM refuses to delete a managed policy that is attached to anything, so the delete half
of the replacement fails and rolls back again. Check first:

```sh
aws iam list-entities-for-policy \
  --policy-arn arn:aws:iam::<account>:policy/aidlc-main-knowledgebase-retrieval
```

Empty today. Once Track C attaches it, this stops being a two-line change. Consumers read the ARN
from `/aidlc/main/knowledgebase/retrieval-policy-arn`, so a rename does not break anyone who follows
the documented path — only anyone who hardcoded the name.

The general form, worth carrying beyond this blueprint: **an explicit name plus a replacing update is
a self-collision.** It applies to every named IAM resource here.

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

With SharePoint enabled there are two of these couplings, and the SharePoint one is worse: its
corpus is a site somebody else can edit, without a PR.

## The 900-second ceiling bounds corpus size

The verifier polls for up to 240s waiting for the data source and 550s waiting for ingestion,
inside a 900s Lambda timeout. One syllabus is seconds. A few thousand documents would time out
mid-verification and **fail a deploy that was actually fine** — the worst kind of failure, because
it looks like the thing it is monitoring broke.

The ceiling is per invocation, and the two verifier instances are separate invocations sequenced by
`DependsOn`, so enabling SharePoint does not halve either budget. It does roughly double how long
`BlueprintDeploy` takes, on a stage every other track is waiting behind.

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

## This template nearly outgrew the 51,200-byte request-body limit

CloudFormation rejects a template that arrives in a *request body* over 51,200 bytes, which is how
every `aws cloudformation deploy --template-file …` sends it. Adding SharePoint and the schedules took
this template to **55,411 bytes**, and the rehearsal failed before the request even reached AWS:
*"Templates with a size greater than 51,200 bytes must be deployed via an S3 Bucket."*

It is now **50,143 bytes** — comment prose that duplicated these docs was condensed into pointers
rather than deleted, and `tools/check` grew a size gate that fails at 51,200 and warns from 48,000.
So the by-hand command works unchanged, and the next person cannot cross the line without being told.

Two things worth keeping:

- **The pipeline was never at risk**, because it stages templates through S3 where the ceiling is 1 MB.
  But that was reasoning, not observation, and the failure mode would have been `BlueprintDeploy`
  red for every track. Shrinking removed the need to be right about it. Prefer that trade.
- **cfn-lint cannot see this class of failure at all.** The request never leaves the machine. It is
  the same blind spot as `ConnectorParameters`, at a different layer, which is why it is a gate in
  `tools/check` rather than a note in a document.

When the warning fires, move prose to `docs/`. Don't delete reasoning to buy bytes.

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

The literal `0.2.0` appears in both the template default and `pipeline/pipeline.yml`'s
`ParameterOverrides`. Nothing validates that they agree, so bumping one and not the other makes
the `cornell:blueprint-version` tag lie. Bump both in the same PR — the PR that added the
SharePoint source had to touch both, and the pipeline one is the easy half to forget because the
template default is the one you are already editing.

## Two tagging gaps are real, not oversights

`aws resourcegroupstaggingapi get-resources --tag-filters
'Key=cornell:deployment-id,Values=aidlc-main-knowledgebase'` returns the knowledge base, both
roles, the managed policy and the SSM parameters. It does **not** return:

- **the data sources** — `AWS::Bedrock::DataSource` has no `Tags` property at all. Mirrored into
  `/aidlc/main/knowledgebase/data-source-id` and, when SharePoint is enabled,
  `/aidlc/main/knowledgebase/sharepoint-data-source-id`. Delete those parameters and the data
  sources become invisible to inventory.
- **the ingestion bucket** — created outside IaC, untagged. See `assumptions.md`.

A third resource type has the same problem with a different fix: **`AWS::Scheduler::Schedule` has no
`Tags` property either** — cfn-lint rejects a tag block on it with `E3002` — but
`AWS::Scheduler::ScheduleGroup` does take the usual `Key`/`Value` list. So the schedules live in a
tagged group rather than getting an SSM mirror. Prefer that pattern when a taggable container exists;
fall back to the mirror when one doesn't.

## `AWS::Bedrock::KnowledgeBase` takes `Tags` as a map

Not the usual list of `Key`/`Value` pairs. Same trap as `AWS::SSM::Parameter`, and every other
resource in this repo uses the list form, so copying a tag block between resources here will fail
in one direction or the other.

## This is close to the first `Type: MANAGED` CloudFormation anywhere

No AWS example uses it, so the template is assembled from the resource schema and the API docs
rather than from a working sample. cfn-lint clean is a weaker signal than usual here.
