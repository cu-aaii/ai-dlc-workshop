# knowledgebase

Turns documents sitting in an S3 bucket into a query-ready Amazon Bedrock **managed** knowledge
base, and hands the identifiers to whatever wants to ask it questions.

This is Track B's slice of the workshop: *documents exist somewhere* → *a knowledge base handle
a chatbot can query*. Track A's Builder MCP asks for it; Track C's Teams bot consumes it.

## What deploys

| Resource | Purpose |
|---|---|
| `AWS::Bedrock::KnowledgeBase` | `Type: MANAGED` — AWS owns the storage, index and embedding model. No vector store to provision. |
| `AWS::Bedrock::DataSource` | The managed S3 connector, pointed at `IngestionBucketName`. |
| `AWS::IAM::Role` (×2) | One for Bedrock to read the bucket, one for the verifier below. |
| `AWS::Lambda::Function` + custom resource | Ingests **and verifies** at deploy time. See below — this is the interesting part. |
| `AWS::IAM::ManagedPolicy` | `bedrock:Retrieve` / `bedrock:RetrieveAndGenerate` on this one knowledge base. The handoff seam. |
| `AWS::SSM::Parameter` (×6) | The handoff itself, plus the mirror the untaggable data source needs. |

Stack name: `aidlc-main-knowledgebase`. Region `us-east-1`.

## The bucket is referenced, never created

`IngestionBucketName` defaults to `aidlc-kb-ingestion-890349359349`, which already exists in
`us-east-1` and already holds `Syllabus-SP26-CS1112-LEC001-PRIOR-TERM.pdf`.

The template does not create a bucket. A bucket it created would be empty on the very deploy that
created it, so the verifier's zero-documents assertion would fail every first deploy.

It must be General Purpose and in the **same account and region** as the stack. That is not
boilerplate: the bucket this blueprint originally pointed at, `aidlc-kb-ingestion-bucket`, turned
out to be in **`us-east-2`**, and the managed S3 connector is same-region only. Merging that would
have failed the first create and left `ROLLBACK_COMPLETE`, which blocks every later merge for every
track. See `docs/assumptions.md`.

The bucket carries all four `cornell:*` tags, so Track E's dashboard can see it — but it was created
by hand rather than by IaC. The fix is a CloudFormation *import* in a follow-up PR.

## A green deploy is the acceptance test

CloudFormation creates a data source but never ingests through it. So `CREATE_COMPLETE` on its
own tells you nothing about whether the knowledge base holds a single document — a stack that
produced a completely empty knowledge base reports success.

We have no CLI and no console, so the pipeline's red/green is the only signal that reaches us.
The custom resource is therefore a **verifier, not a trigger**. On every deploy it:

1. polls the data source until `AVAILABLE` (creation is asynchronous),
2. starts an ingestion job and waits for it to finish,
3. **fails** unless the job is `COMPLETE`, at least one document was scanned, and none failed,
4. runs `bedrock-agent-runtime:retrieve` with `SmokeQuery` and **fails on zero results**.

| Pipeline | Meaning |
|---|---|
| `BlueprintDeploy` green | Data source available, ingestion complete, documents indexed with zero failures, and the knowledge base answered the smoke query. |
| `BlueprintDeploy` red | One of those failed. The custom resource's failure reason is the diagnosis and appears on the stack event. |

It takes `SourceCommitId` as a property, so every merge re-ingests and re-verifies. Syncs are
incremental, so that is cheap — and it means "merged" implies "indexed and answerable" without
any scheduler, of which Bedrock has none.

**Do not soften the verifier into fire-and-forget to make a deploy pass.** It is the only thing
standing between a green pipeline and an empty knowledge base.

## Rehearsing before you merge

No feature branch has a pipeline — the Source stage tracks the branch named by `Environment`,
which is capped at four characters. So `tools/check` is the whole pre-merge signal for a builder
with no account access.

With account access, deploy it by hand as a separate environment first. That is what the parameter
defaults exist for, and every derived name is distinct from the `main` ones:

```sh
aws cloudformation deploy --region us-east-1 \
  --stack-name aidlc-test-knowledgebase \
  --template-file blueprints/knowledgebase/infra/knowledgebase.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=test SourceCommitId=local-rehearsal

aws logs tail /aws/lambda/aidlc-test-knowledgebase-verifier --since 20m
aws cloudformation delete-stack --stack-name aidlc-test-knowledgebase   # it bills while it exists
```

Worth doing before any change to `ConnectorParameters` or the verifier, because neither is covered
by `tools/check`.

## Reading the result without AWS access

You can't, directly — which is why the verifier exists. What you get is the pipeline verdict,
and the failure reason on a red one.

For anyone who *does* have access, the same facts read out of the stack:

```sh
aws cloudformation describe-stacks --stack-name aidlc-main-knowledgebase \
  --query 'Stacks[0].Outputs' --output table
```

`DocumentsIndexed` and `SmokeQueryResult` are the proof. Or out of SSM, which is where consumers
should look:

```sh
aws ssm get-parameters-by-path --path /aidlc/main/knowledgebase --output table
```

## Consuming it

Read `/aidlc/main/knowledgebase/knowledge-base-id`, attach the managed policy at
`/aidlc/main/knowledgebase/retrieval-policy-arn` to your role, then call
`bedrock-agent-runtime`. Don't write your own `bedrock:Retrieve` statement — the managed policy
exists so read access to this knowledge base stays one reviewable artifact.

SSM rather than a CloudFormation `Export` on purpose: an export would couple the consumer's
stack lifecycle to this one and block ever replacing the knowledge base.

## Customizing

| Parameter | Default | Notes |
|---|---|---|
| `IngestionBucketName` | `aidlc-kb-ingestion-890349359349` | Must exist, same account, **same region** (`us-east-1`), General Purpose. |
| `SmokeQuery` | `What is the late homework policy?` | Must be answerable from the bucket's contents or **every deploy fails**. Change it in the same PR that changes the corpus. |
| `ChunkingMaxTokens` | `300` | **Immutable** once the data source exists. |
| `ChunkingOverlapPercentage` | `20` | **Immutable** once the data source exists. |

Changing either chunking value replaces the data source and re-ingests from scratch.

## Not built

**SharePoint is pinned**, not abandoned. `infra/azure/sharepoint-entra.tf.sample` is the shape
it would take, and `infra/azure/README.md` explains what unpinning it costs. The short version:
a managed knowledge base's SharePoint connector offers only certificate-based `ENTRA_ID_APP_ONLY`
or password-grant `OAUTH2_APP`, and the Entra app already provisioned for the workshop uses a
client secret, which fits neither. The self-managed alternative is in preview and forces
OpenSearch Serverless — a continuous ~$350/mo floor on a shared account.

Web crawler is pinned for the same "one data source proves the pattern" reason, and is a much
smaller lift: another `AWS::Bedrock::DataSource` with `type: WEB` in `ConnectorParameters`.

## Before you push

```sh
tools/check
```

## Teardown

Deleting the stack removes the knowledge base and its index. `DataDeletionPolicy: RETAIN` on the
data source means removing *just the data source* leaves the indexed vectors alone, so a template
edit that replaces it does not silently empty the knowledge base.

This is the first thing in this repo that costs money while idle — managed knowledge base
billing is per-GB-stored plus per-retrieve, and it does not stop when the demo ends.
See `docs/warnings.md`.

## Further reading

- `docs/decisions.md` — the forks taken, what was rejected, and the evidence
- `docs/assumptions.md` — what must already be true for this to deploy
- `docs/warnings.md` — cost, silent-failure modes, immutable fields
- `skills/knowledgebase/SKILL.md` — how Claude Code reproduces this to standard
