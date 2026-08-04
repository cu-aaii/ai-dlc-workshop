# Decisions

Why this blueprint looks the way it does. Each entry is a fork where a reasonable person would
have gone the other way, so the reasoning matters more than the outcome.

## The constraint underneath everything

**No AWS CLI, no console access.** The only way this track causes anything to happen is a merge
kicking off the IaC, and the only signal that comes back is the pipeline going red or green. No
`describe-stacks`, no CloudWatch, no `aws s3 cp`.

Two of the decisions below are direct consequences, and they are the two that matter most.

## Managed knowledge base, not a vector store

`KnowledgeBaseConfiguration.Type: MANAGED` with
`ManagedKnowledgeBaseConfiguration.EmbeddingModelType: MANAGED`.

AWS owns the storage, the index and the embedding model. Consequences worth stating because they
look like omissions in the template:

- **No `StorageConfiguration` at all.** It is create-only and simply absent.
- **No model-access gate.** Nobody has to enable a foundation model in the console first, which
  matters when nobody has a console.
- **No embedding model to name.** `embeddingModelType: MANAGED` forbids `embeddingModelArn` and
  `embeddingModelConfiguration`; supplying either is an error. `CUSTOM` requires both.
- **The embedding model type is immutable.** Switching between `MANAGED` and `CUSTOM` means a new
  knowledge base, not an update.

GA in `us-east-1` since 17 June 2026.

### The service role does still get embedding-model permissions

An earlier version of this document claimed a managed knowledge base needs no
`bedrock:InvokeModel`, on the reasoning that AWS owns the embedding model. The managed
service-role documentation says otherwise: it lists "access to the Amazon Bedrock base models"
among the three required policies, with `bedrock:ListFoundationModels`, `bedrock:ListCustomModels`
and `bedrock:InvokeModel` on the named embedding models — and it does not distinguish `MANAGED`
from `CUSTOM` embedding when it does so.

It may well be that those statements only matter for `CUSTOM`. But the template includes them,
because the two outcomes are not symmetric: being over-permissive by four read-scoped statements
costs nothing, while being wrong costs a failed deploy in a shared account that nobody on this
track can inspect. `InvokeModel` is scoped to four named embedding models. **Do not** generalise
it to `bedrock:*` or `Resource: '*'` to be safe — that trades a small cost for a large one.

### Rejected: S3 Vectors

`AWS::S3Vectors::VectorBucket` and `AWS::S3Vectors::Index` are both CloudFormation-native —
verified against this repo's pinned linter, not assumed. But a managed knowledge base needs
neither, and every resource we don't provision is one we don't have to tag, cost or tear down.

### Rejected: OpenSearch Serverless

Also CloudFormation-native. Also unnecessary here. And its OCU floor bills continuously —
roughly $350/mo on a shared account for a demo blueprint. Only in play if the self-managed path
were forced on us, which is the SharePoint question below.

### Rejected: Aurora + pgvector

More moving parts than the entire rest of this repo combined.

## A verifying custom resource, not a trigger

This is the decision the whole blueprint turns on.

CloudFormation creates a data source but **never ingests through it**. `CreateDataSource` is
asynchronous (`CREATING` → `AVAILABLE`), and Bedrock has no native scheduled sync — "incremental"
describes what gets *reprocessed*, not what *triggers*. So without something running ingestion,
a stack that produced an entirely empty knowledge base reports `CREATE_COMPLETE` and the pipeline
goes green.

The obvious fix is a custom resource that starts an ingestion job and returns. That is not enough:
it makes the deploy *cause* ingestion but still not *prove* it. Given red/green is our only
feedback channel, correctness has to be asserted inside the deploy or it is never asserted at all.

So the verifier fails the stack on any of five conditions: data source never reaches `AVAILABLE`,
ingestion job not `COMPLETE`, zero documents scanned, any document failed, or the retrieval smoke
query returns nothing.

`SourceCommitId` is a custom-resource *property* rather than decoration, so the verifier re-runs
on every merge. Syncs are incremental, so re-running is cheap, and it substitutes for the
scheduler Bedrock doesn't have.

**This is load-bearing.** Softening it to fire-and-forget to make a deploy pass would silently
turn the blueprint back into something that proves nothing.

## Reference the existing bucket, don't create one

Creating a fresh, correctly tagged bucket is the right answer on tagging grounds and impossible
on access grounds: putting an object into it needs write access nobody on this track has, so it
would be empty forever and every deploy would fail the zero-documents assertion.

So `IngestionBucketName` references a pre-existing bucket. An earlier draft made bucket creation
conditional; dropping that removed the repo's first `Condition` block for no benefit.

**Which bucket changed late, and the reason is worth keeping.** The original target,
`aidlc-kb-ingestion-bucket`, is in **`us-east-2`**. The managed S3 connector is same-region only, so
the first create would have failed — and a failed *first* create leaves `ROLLBACK_COMPLETE`, which
blocks every subsequent merge for every track. The template's own docs asserted the bucket was in
`us-east-1`; one `get-bucket-location` call disproved it. That is the argument for rehearsing with
real credentials rather than reasoning from a plan document.

`aidlc-kb-ingestion-890349359349` replaces it: `us-east-1`, same account, all four `cornell:*` tags,
same syllabus. Created by hand, because a bucket the template created would be empty on the deploy
that created it and would fail the zero-documents assertion. So it closes the tagging gap but not
the IaC gap — see `assumptions.md`.

## Zip Lambda with inline code

A documented exception to CLAUDE.md's "Lambda means container images."

`ContainerBuildProject` and `pipeline/codebuild.yml` exist but no pipeline stage invokes them —
wiring one is Track 0's work. And with no CLI there is no way to upload a code bundle to S3
either, so inline `Code.ZipFile` is not merely the easy zip option, it is the only one available.

`Code.ZipFile` is hard-capped at **4096 characters** by CloudFormation. The handler is currently
~2700, terse and uncommented for that reason. There is no S3-bundle fallback if it outgrows the
cap; that would force the container path.

## SSM parameters plus a managed policy for handoff

### Rejected: CloudFormation `Export` / `Fn::ImportValue`

An export cannot be changed or removed while another stack imports it, which would couple Track
C's lifecycle to ours and block ever replacing the knowledge base. SSM parameters are read at
runtime and carry no such lock.

### The managed policy

`RetrievalPolicy` grants `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` scoped to this one
knowledge base ARN. Consumers attach it rather than writing their own statements, so read access
stays one reviewable artifact — and it is a concrete answer to Track D's isolation question
instead of a paragraph about one.

## Mirroring the data source id into SSM

`AWS::Bedrock::DataSource` has **no `Tags` property at all** — verified against the schema, not
inferred. The all-four-`cornell:*`-tags rule is therefore impossible on it.

Rather than quietly skip it, `DataSourceIdParameter` gives tag-based inventory a join key that
tags cannot reach. Deleting that parameter hides the data source from Track E entirely.

## S3 only; SharePoint pinned — but not for the reason first given

**Retraction.** An earlier version of this document called SharePoint an *authentication dead end*:
the managed connector offers `ENTRA_ID_APP_ONLY` (certificate mandatory) or `OAUTH2_APP` (a
resource-owner password grant needing an MFA-exempt account), and the workshop's Entra app uses a
client secret, which fits neither.

There is a managed SharePoint data source in the account — `knowledge-base-quick-start-9as4d` /
`GBHYGKPMYL` — configured with `authType: ENTRA_ID_APP_ONLY`, a `certificateS3Path` pointing at
`public.cer` in `config-bucket-890349359349`, `https://8chzbf.sharepoint.com/sites/kb`, and the very
secret the retracted paragraph called unusable. So `ENTRA_ID_APP_ONLY` is at least *reachable* here:
someone generated a certificate for the Entra app. That much is configuration anyone can read.

**Second retraction, and this one was mine.** An earlier version of this section called that data
source **working** and a "known-good example." It is neither. It has never ingested a document. Its
last five ingestion jobs all `FAILED` with zero documents scanned, every one of them:

```
SharePoint app is missing required scopes: Missing required permissions:
[GroupMember.Read.All, User.Read.All,
 one of [Sites.FullControl.All, Sites.Selected, Sites.Read.All]]
```

I concluded "working" from `status: AVAILABLE` plus a complete-looking `connectorParameters`, and
never listed its ingestion jobs. **`AVAILABLE` describes the connector's validity, not whether it
ever ingested anything** — the same mistake as reading a stack status instead of an outcome, which
is the lesson at the top of `warnings.md`. Nothing in this repo had evidence for the claim when it
was written.

What is *not* established: whether `siteUrls` is correct. Bedrock validates the app's granted Graph
permissions before it reaches the site, so a wrong site URL would fail at scopes first regardless.
The scope error is the current blocker; it is not proof that anything behind it is right.

Two things follow for anyone unpinning SharePoint. The consent is an Entra admin task, not a code
task — `Sites.*` plus, because this config sets `aclEnabled: true` and `crawlIdentities: true`,
`GroupMember.Read.All` and `User.Read.All` for identity crawling. Turning ACL and identity crawling
off should drop the requirement to a Sites scope alone, which is a much smaller consent ask. And
`GBHYGKPMYL` is a **shape** reference only — copy its structure if you like, but do not treat it as
proof the shape ingests.

Independently of all that, SharePoint stays pinned on **scope**: adding a second data source means
extending the verifier, which asserts on a single ingestion job and would otherwise let an empty
second source pass green. `infra/azure/sharepoint-entra.tf.sample` records the shape.

The self-managed connector remains rejected: preview, and its docs state only OpenSearch Serverless
is available with it — the continuous OCU floor, on a shared account, for a demo.

The secret `dev/workshop/entra/sharepoint` stays where it is; nothing in this blueprint's deployed
template references its values.

Web crawler is pinned only because one data source proves the pattern. It is a much smaller lift:
another `AWS::Bedrock::DataSource` with `type: WEB`.

## `BlueprintVersion` duplicated in the pipeline action

CLAUDE.md says two things that conflict here: "pass every parameter explicitly from the pipeline"
and "bump the version default in the PR that changes the blueprint." `hello-world` resolves the
conflict by omitting `BlueprintVersion` from its `ParameterOverrides`.

This blueprint passes it explicitly, which means the literal `0.1.0` appears in both
`pipeline/pipeline.yml` and the template default, and nothing checks that they agree. Both places
carry a comment saying so.

Worth revisiting repo-wide: a per-blueprint version passed from the pipeline wants a single source
of truth, and right now there isn't one either way.

## What a by-hand rehearsal proved, and what skipping it would have cost

Before merging, this template was deployed by hand as `aidlc-test-knowledgebase` with
`Environment=test`. It found one defect that `tools/check`, three documentation passes and a full
review had all missed, and it converted two assumptions into facts:

| Outcome | Detail |
|---|---|
| **Found** | `ChunkingConfiguration` alongside a managed embedding model fails at CREATE. It lints clean. On a first create this leaves `ROLLBACK_COMPLETE`, which blocks every track's merges until someone with account access deletes the stack. |
| **Confirmed** | `AWS::Bedrock::KnowledgeBase` with `Type: MANAGED` reached `CREATE_COMPLETE`. The managed path does work from CloudFormation, which no AWS example demonstrates. |
| **Confirmed** | `ConnectorParameters` written as a YAML mapping marshals correctly — the data source request reached server-side validation and failed on chunking rather than on a malformed connector body. |

The general lesson, worth keeping because this repo's deploy model invites the mistake: here
**cfn-lint clean is a statement about syntax, not about whether the service will accept the
request.** Two of the three facts above are invisible to every check that runs in CI.

## Verified against the pinned linter, not recalled

Everything below was read out of `cfn-lint>=1.53,<2`'s bundled `us-east-1` schemas:

| Fact | Consequence |
|---|---|
| `KnowledgeBaseType` enum includes `MANAGED`; `EmbeddingModelType` is `CUSTOM \| MANAGED` | The managed path lints clean with the pinned linter. |
| KB required properties are only `Name`, `RoleArn`, `KnowledgeBaseConfiguration` | Minimal template. |
| KB `Name` pattern is `^([0-9a-zA-Z][_-]?){1,100}$` | `aidlc-main-knowledgebase` is valid; a doubled separator would not be. |
| KB `Tags` is a **map**, not a `Key`/`Value` list | Same trap as `AWS::SSM::Parameter`. Every other resource in this repo uses the list. |
| `AWS::Bedrock::DataSource` has no `Tags` property | Hence the SSM mirror above. |
| `DataSourceType` includes `MANAGED_KNOWLEDGE_BASE_CONNECTOR` | The managed connector is reachable from CloudFormation. |
| `ConnectorParameters` is free-form `Json` | **cfn-lint validates nothing inside it.** A typo passes `tools/check` and fails at deploy. The single biggest risk in this template, and the other reason the verifier exists. |

One thing the live data source shows that no document states: the Bedrock API returns
`connectorParameters` as a **JSON-encoded string**, not an object. This template writes it as a YAML
mapping and relies on CloudFormation to marshal it, which is what the `Json` schema type implies.
That is the last untested assumption in the template, and the reason to rehearse a deploy by hand
before merging rather than after.
| `KnowledgeBaseConfiguration` sub-objects and `VectorIngestionConfiguration/ChunkingConfiguration` are create-only | Changing type or embedding model replaces the resource. |
| The schema **accepts** `ChunkingConfiguration` next to a managed embedding model | And the API **rejects** it. See below — the sharpest example of cfn-lint clean meaning less than usual here. |

Confirmed from AWS documentation rather than memory:

- The service role does **not** need the `AmazonBedrockExecutionRoleForKnowledgeBase_` name prefix.
  That is only what the console generates, so the role follows this repo's naming convention.
- Managed S3 connector body is `type: S3`, `version: "1"`, and a `connectionConfiguration` holding
  **both** `bucketName` and `bucketOwnerAccountId`. The bucket must be **General Purpose** and in
  the **same region** as the knowledge base.

  **Retraction.** An earlier version of this document said `bucketOwnerAccountId` could be omitted
  for a same-account bucket, because the connector reference marks it *Conditional — "Required for
  cross-account access"* — and it noted, without acting on it, that every AWS example includes it
  anyway. The reference is wrong and the examples were right: omitting it fails validation with
  *"Value at 'connectionConfiguration.bucketOwnerAccountId' failed to satisfy constraint: Member
  must not be null."*

  The lesson worth generalising: when a doc table and every worked example disagree, the examples
  are evidence and the table is prose. This one cost a hung stack, because the failure mode is the
  one described at the top of `warnings.md` — Bedrock fails the data source, CloudFormation does not
  notice, and the deploy hangs instead of going red.
- `deletionProtectionConfiguration` is a **sibling of** `connectorParameters`, not a member of it.
  The two AWS pages disagree on this; the CloudFormation schema agrees with the connector
  reference. Omitted here either way, which sidesteps the question.
- Managed KB parsing is `SMART_PARSING` only. It is the default, but the template states it
  explicitly because the AWS CLI example does and an unstated default is one more assumption.
- `IngestionJobStatistics` has **no `numberOfDocumentsIndexed` field.** An earlier version of the
  verifier read that key and silently fell back to the scanned count, so it would have reported a
  plausible-looking number that was not measuring indexing at all. The real fields are
  `numberOfNewDocumentsIndexed` + `numberOfModifiedDocumentsIndexed`.
- `numberOfDocumentsScanned` "includes new, updated, and unchanged documents," which is what makes
  the zero-scanned assertion safe on re-deploys. If it counted only *changed* documents, every
  no-op merge would fail the stack.
- Retrieval actions are `bedrock:Retrieve` / `bedrock:RetrieveAndGenerate` on
  `arn:aws:bedrock:us-east-1:<account>:knowledge-base/<id>`.
