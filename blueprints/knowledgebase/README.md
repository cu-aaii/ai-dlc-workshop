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
| `AWS::Bedrock::DataSource` | The managed SharePoint connector — **only when `EnableSharePointSource` is `true`, and it defaults to `false`.** |
| `AWS::IAM::Role` (×2) | One for Bedrock to read the bucket (and, when enabled, the certificate and secret), one for the verifier below. |
| `AWS::Lambda::Function` + custom resource | Ingests **and verifies** at deploy time. See below — this is the interesting part. A second custom resource, same function, verifies SharePoint. |
| `AWS::IAM::ManagedPolicy` | `bedrock:Retrieve` / `bedrock:RetrieveAndGenerate` on this one knowledge base. The handoff seam. |
| `AWS::Scheduler::Schedule` + `ScheduleGroup` | Re-syncs between deploys — **only when `EnableScheduledSync` is `true`, and it defaults to `false`.** Fire-and-forget; see below. |
| `AWS::SSM::Parameter` (×6, ×8 with SharePoint, ×9 with schedules) | The handoff itself, plus the mirrors the untaggable data sources need. |

Stack name: `aidlc-main-knowledgebase`. Region `us-east-1`.

The deployed `main` stack is S3-only. With the flag off, nothing SharePoint-shaped exists in the
stack at all — every SharePoint resource, role statement, verifier, SSM mirror and output hangs off
one `Condition`.

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

With SharePoint enabled, a second instance of the same function does the same four things against
the SharePoint source, sequenced after the S3 one. The ingestion statistics are per-data-source, so
an empty SharePoint source cannot pass — but step 4 queries the whole knowledge base, so the
SharePoint smoke query has to be one only SharePoint can answer.

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

That command sends the template in the request body, which CloudFormation caps at 51,200 bytes. This
template got to 55,411 once and the command broke; it is back to 50,143 and `tools/check` now gates
it. If the gate ever fires, either move prose into `docs/` or add `--s3-bucket` plus `--s3-prefix`
— but never point that at the ingestion bucket, which would index your template as a document.

**Mandatory** before enabling SharePoint. Add `EnableSharePointSource=true` to the overrides, and
read the data source's status from Bedrock rather than from the stack — a malformed connector body
hangs the deploy instead of failing it:

```sh
aws bedrock-agent list-data-sources --knowledge-base-id <id>   # status, per source
```

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
| `EnableSharePointSource` | `false` | Adds the SharePoint source. Read `docs/sharepoint-source.md` first; flip it in its own PR. |
| `SharePointSiteUrl` | `https://8chzbf.sharepoint.com/sites/kb` | One site — the site needs its own per-site Graph grant. Indexing a *second* site is a `ConnectorParameters` edit, not a parameter change. Ignored while the flag is off. |
| `SharePointTenantId` | Entra directory id | Not a secret. |
| `SharePointConnectorSecretArn` | `bedrock/sharepoint-cert-connector` | Must hold exactly `clientId` and `certificatePassword`. Referenced by ARN; the template never reads its value. |
| `SharePointCertificateBucket` / `SharePointCertificateKey` | `bedrock-sharepoint-certs-890349359349` / `certs/certificate.p12` | The `.p12`, under a prefix — the role grants `GetObject` on the prefix because the connector probes for a sibling `.metadata.json`. |
| `SharePointSmokeQuery` | `What does the syllabus say about attendance?` | **Placeholder.** Retrieval spans the whole knowledge base, so this one would pass on the S3 syllabus. Replace it with a SharePoint-only question. |

| `EnableScheduledSync` | `false` | Adds the re-sync schedules. Fire-and-forget — read the section above. |
| `SyncScheduleExpression` / `SharePointSyncScheduleExpression` | `cron(0 7 ? * MON *)` / `cron(0 8 ? * MON *)` | **UTC**, so 07:00 here is 03:00 in Ithaca in summer. Offset by an hour because ingestion jobs conflict. |

Every one of these is also passed explicitly from `pipeline/pipeline.yml`, so changing a default
means editing two files.

**Chunking is not tunable here, and that is the service's rule, not ours.** A managed embedding
model owns chunking outright — supplying a `ChunkingConfiguration` alongside it fails at CREATE with
*"A chunking strategy cannot be specified with a managed embedding model."* Tuning chunk size means
`EmbeddingModelType: CUSTOM`, which means naming an embedding model and provisioning a vector store,
which is the whole cost this blueprint exists to avoid.

## SharePoint: wired, verified, off by default

`EnableSharePointSource=true` adds a second data source over a SharePoint site's document library,
and a second verifier instance that holds it to the same five assertions. The configuration in the
template is one that was observed ingesting and answering in this account — not a sketch.

It is off by default because turning it on makes **every track's merge to `main`** depend on things
outside this repo and outside AWS: an Entra app registration, admin-consented `Sites.Selected`
grants on both Microsoft Graph and the SharePoint REST API, a per-site permission grant, a `.p12` in
S3, and a certificate that has not expired. When one of those lapses the verifier correctly fails
the stack, and `BlueprintDeploy` is red for everyone.

Read `docs/sharepoint-source.md` before flipping it — in particular the order of operations, and the
fact that the default `SharePointSmokeQuery` is a placeholder that would pass on S3 content.

What is still by hand, and why: the certificate (CloudFormation cannot generate a `.p12`), the
secret's value (never in a public repo), and the per-site Graph grant. The Entra app registration
itself is Terraform-shaped — `infra/azure/sharepoint-entra.tf.sample` — but stays a sample until a
`Terraform` stage action names that directory.

## Re-syncing between deploys

A merge re-ingests and re-verifies. Nothing else does, because **Bedrock has no scheduled sync** —
`StartIngestionJob` is the only trigger there is. So between merges the index goes stale, which
matters most for SharePoint, where the corpus is a site anyone can edit without a PR.

`EnableScheduledSync=true` adds one EventBridge Scheduler schedule per data source (weekly by
default, offset an hour apart, expressions in **UTC**) calling `StartIngestionJob` through a universal
target. No Lambda, no code.

**It verifies nothing, and it can't.** Scheduler refuses API actions whose names start with a
read-only prefix — `get`, `list`, `retrieve` — so `GetIngestionJob` and the smoke query are both
unreachable from a schedule. A month of failed syncs looks exactly like a month of successful ones.
`/aidlc/main/knowledgebase/sync-schedule` records the configuration and the literal
`outcomes=not-recorded` so that is hard to forget.

It cannot make a bad deploy pass, though — it is not in the deploy path. Freshness improves; the
acceptance test is still a green merge. The verified version is Scheduler → Step Functions, which can
poll and assert, and is written up in `docs/decisions.md` as evaluated and deferred.

## Not built

Web crawler, for the same "nothing asks for it yet" reason SharePoint used to be pinned for. It is a
much smaller lift than SharePoint was: another `AWS::Bedrock::DataSource` with `type: WEB` in
`ConnectorParameters`, plus a third verifier instance.

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
- `docs/sharepoint-source.md` — the SharePoint half: Entra, the certificate, the grants, the order
- `docs/assumptions.md` — what must already be true for this to deploy
- `docs/warnings.md` — cost, silent-failure modes, immutable fields
- `skills/knowledgebase/SKILL.md` — how Claude Code reproduces this to standard
