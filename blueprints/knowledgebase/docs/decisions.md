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

### The service role keeps embedding-model permissions it almost certainly does not need

An earlier version of this document claimed a managed knowledge base needs no
`bedrock:InvokeModel`, on the reasoning that AWS owns the embedding model. The managed
service-role documentation says otherwise: it lists "access to the Amazon Bedrock base models"
among the three required policies, with `bedrock:ListFoundationModels`, `bedrock:ListCustomModels`
and `bedrock:InvokeModel` on the named embedding models — and it does not distinguish `MANAGED`
from `CUSTOM` embedding when it does so. So the template included them.

**The original reasoning turned out to be right, and the statements are staying anyway.** A managed
knowledge base in this account — `sharepoint-kb` / `KANPIZQSGD`, the one behind the SharePoint
defaults — has been observed ingesting and answering with a service role holding **no `bedrock:*`
permission at all**. Managed embedding does not use them.

They stay because the asymmetry that put them there has not changed: four read-scoped statements
cost nothing, and deleting them to be tidy risks a failed deploy in a shared account for no gain.
`InvokeModel` is scoped to four named embedding models. **Do not** generalise it to `bedrock:*` or
`Resource: '*'` — that trades a small cost for a large one.

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

## Scheduled re-sync, and the one place this blueprint accepts an unverified action

Every other decision here bends towards "assert it or don't ship it." This one doesn't, so it needs
the most explanation.

**The problem.** Bedrock has no scheduled sync — confirmed against the current sync documentation,
not recalled: *"each time you add, modify, or remove files from your data source, you must sync,"*
and `StartIngestionJob` is the only trigger. Between merges the index goes stale, silently. For S3
that is a slow drift; for SharePoint, where the corpus is a site anyone can edit without a PR, it is
the normal case.

**What ships.** `EnableScheduledSync` (default `false`) creates an `AWS::Scheduler::ScheduleGroup`,
a role with exactly `bedrock:StartIngestionJob` on this one knowledge base, and one
`AWS::Scheduler::Schedule` per enabled data source, using the universal target
`arn:aws:scheduler:::aws-sdk:bedrockagent:startIngestionJob`. No Lambda, no code, no new inline-code
pressure, weekly by default and offset an hour apart.

**What it cannot do, and this is structural rather than an omission.** EventBridge Scheduler refuses
any API action whose name begins with a read-only prefix, and the published list includes `get`,
`list`, **`retrieve`** and **`invokeModel`**. So from a schedule:

| Wanted | Reachable? |
|---|---|
| `StartIngestionJob` | Yes |
| `GetIngestionJob` / `ListIngestionJobs` — did it work? | **No** (`get`, `list`) |
| `Retrieve` — does it still answer? | **No** (`retrieve`) |

A schedule can therefore start a sync and can never find out what happened. All five assertions
still exist, and they only ever run on a deploy. **A scheduled sync keeps the index fresh and proves
nothing**, which is precisely the fire-and-forget shape `warnings.md` tells you not to build — the
difference being that here it is additive: it cannot make a deploy pass that would otherwise fail,
because it is not in the deploy path at all. That is the whole argument for accepting it.

### Rejected for now: Scheduler → Step Functions

The verified version. `startExecution` is not a blocked prefix, and Step Functions' SDK integrations
*can* call `GetIngestionJob` and `Retrieve`, so a state machine can start the job, poll it, assert
the statistics, run the smoke query and write the result somewhere — the deploy-time verifier's five
assertions, on a timer, with a real outcome to record.

It also retires a warning this blueprint already carries: the verifier's 900-second Lambda ceiling
bounds corpus size, and `warnings.md` says the shape has to change to Step Functions or
fire-and-forget-plus-alarm before this takes real volume. Same work, two problems.

Deferred because it is a second implementation of the assertions, which either duplicates them or
means rewriting the one artifact in this blueprint that is known to work, days before a workshop.
The right sequence is: ship the schedule, then replace *both* the schedule target and the custom
resource's Lambda with one state machine, rather than adding a third thing.

### Rejected: event-driven on change

For S3 this needs `NotificationConfiguration.EventBridgeConfiguration` on the bucket, which requires
CloudFormation to **own** the bucket — the import `assumptions.md` already calls the honest fix.
There is also a debounce problem: fifty uploaded files are fifty events, and ingestion jobs conflict,
so most of them would fail. Worth doing after the import, with a queue in front.

For SharePoint there is no AWS-visible change event at all. Microsoft Graph change notifications
would mean a public HTTPS endpoint, a validation handshake and subscription renewal every few days —
a new inbound surface for a blueprint that indexes a syllabus. Polling is the answer there.

### Rejected: reusing the verifier Lambda on a schedule

It speaks only the custom-resource protocol — it reads `ResponseURL` and `StackId` and `PUT`s a
response — so a scheduled invocation would fail on the event shape. Adapting it means editing the
one load-bearing artifact, which has ~280 characters of inline headroom, to do double duty. The
tempting version of this idea costs more than the state machine and leaves less.

### Where the outcome is recorded: nowhere, and the SSM parameter says so

`/aidlc/main/knowledgebase/sync-schedule` records the *configuration* — the expressions, the group,
and the literal string `outcomes=not-recorded`. It is deliberately not a result record, because
there is no result to record: nothing in the stack ever learns what a scheduled sync did.

The two `last-ingestion-result` parameters sit next to it and *are* real results — of the last
**deploy**. Reading them as evidence that scheduled syncs are healthy is the specific mistake this
wording exists to make harder. An alarm on Scheduler's `TargetErrorCount` would at least catch "the
API call itself failed"; it still would not catch a failed ingestion job, and nothing subscribes to
anything today.

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

`RetrievalPolicy` grants `bedrock:Retrieve` — and, since `sharepoint-runbook.md` §11, **not**
`bedrock:RetrieveAndGenerate`, which a managed knowledge base does not support at any IAM level.
Granting it would hand a consumer an affordance the service rejects, which costs them an hour of
debugging their own role. A bot that wants generation calls `Retrieve` then `Converse`. Scoped to
this one knowledge base ARN. Consumers attach it rather than writing their own statements, so read access
stays one reviewable artifact — and it is a concrete answer to Track D's isolation question
instead of a paragraph about one.

## Mirroring the data source id into SSM

`AWS::Bedrock::DataSource` has **no `Tags` property at all** — verified against the schema, not
inferred. The all-four-`cornell:*`-tags rule is therefore impossible on it.

Rather than quietly skip it, `DataSourceIdParameter` gives tag-based inventory a join key that
tags cannot reach. Deleting that parameter hides the data source from Track E entirely.

## SharePoint: wired, verified, and off by default

The operational detail lives in `sharepoint-source.md`. This section is the decisions and the
retractions, because this is the part of the blueprint that has been wrong in public twice.

**Retraction 1.** An earlier version called SharePoint an *authentication dead end*: the managed
connector offers `ENTRA_ID_APP_ONLY` (certificate mandatory) or `OAUTH2_APP` (a resource-owner
password grant needing an MFA-exempt account), and the workshop's original Entra app used a client
secret, which fits neither. The conclusion drawn from that — SharePoint is unreachable here — was
wrong. A new app registration with a certificate is a modest amount of work, not a blocker, and
that is what now exists.

**Retraction 2, the worse one.** A later version called the account's existing quick-start data
source `knowledge-base-quick-start-9as4d` / `GBHYGKPMYL` **working** and a "known-good example." It
was neither. It never ingested a document; its last five ingestion jobs all `FAILED` with zero
documents scanned:

```
SharePoint app is missing required scopes: Missing required permissions:
[GroupMember.Read.All, User.Read.All,
 one of [Sites.FullControl.All, Sites.Selected, Sites.Read.All]]
```

"Working" was concluded from `status: AVAILABLE` plus a complete-looking `connectorParameters`,
without ever listing the ingestion jobs. **`AVAILABLE` describes the connector's validity, not
whether it ever ingested anything** — the same class of mistake as reading a stack status instead
of an outcome, which is the lesson at the top of `warnings.md`.

Worth keeping because that failure is also the design input for what shipped: the missing scopes
were `GroupMember.Read.All` and `User.Read.All`, which Bedrock demands *only* because that
configuration sets `aclEnabled: true` and `crawlIdentities: true`. Turning ACL crawling off drops
the requirement to a `Sites` scope alone, which is a far smaller consent ask. Hence
`aclEnabled: false` in this template.

**What is now true, and verified rather than reasoned.** A managed knowledge base with a SharePoint
data source has been observed ingesting and answering in this account — `sharepoint-kb` /
`KANPIZQSGD`, one job `COMPLETE`, one document scanned, one indexed, none failed. The template's
`ConnectorParameters` body and its parameter defaults are that configuration, field for field.

**Independently confirmed, on a different tenant.** `sharepoint-runbook.md` documents this path
built end to end on a separate tenant and AWS account, and it settles the consent question this
document used to leave open: that build ingested holding `Sites.Selected` and nothing else on both
Microsoft Graph and the SharePoint REST API. No `GroupMember.Read.All`, no `User.Read.All`, no scope
error. `aclEnabled: false` is sufficient on its own — `crawlIdentities` then defaults to `false`
without being set, which the service confirms in its echo of `connectorParameters`.

So the consent ask is two `Sites.Selected` grants plus one per-site grant, not the five tenant-wide
permissions the quick-start failure implies. Two builds, two accounts, same answer — which is why
`aclEnabled: false` is in the template rather than under discussion.

That runbook also carries three findings this blueprint acts on: `aclEnabled` is **immutable after
creation** (so getting it wrong is a data-source replacement, not an update), the SharePoint
`connectorParameters` body is larger and therefore more exposed to the unlintable-Json hazard than
the S3 one, and `RetrieveAndGenerate` is not supported on a managed knowledge base at all — see
below.

### Off by default

`EnableSharePointSource` defaults to `false` and `pipeline/pipeline.yml` passes `false`, so the
deployed `main` stack is S3-only. This is the decision most likely to read as timidity, so the
reason is worth being explicit about: enabling it makes **every merge to `main`, by every track,**
depend on an Entra app registration, an admin consent, a per-site grant and an unexpired
certificate. None of those is in this repo, none is visible to `tools/check`, and the verifier
correctly fails the stack when any of them lapses — so a lapsed certificate is a red
`BlueprintDeploy` for everyone during a workshop.

An S3-only deploy is byte-for-byte what it was before SharePoint existed: everything
SharePoint-shaped hangs off one `Condition`.

### Rejected: making the certificate or the secret value IaC

CloudFormation cannot generate a `.p12`, and a certificate password in a template is a secret in a
public repo with no secret scanning. Terraform *can* generate one, but its state then holds the
password, and the `.p12` has to exist on disk for the S3 upload. So the certificate, the secret's
value and the per-site Graph grant are by-hand steps, documented rather than automated. The
template references them and never contains them, which is this repo's standing pattern for
credentials.

### `DataDeletionPolicy: DELETE` on SharePoint, `RETAIN` on S3

A deliberate divergence between two otherwise identical resources.

SharePoint has **no document-level deletion** — Bedrock rejects it with *"Invalid data source type
[SHAREPOINTV3] provided. Only S3 and Custom data source supported for document level request."* And
narrowing scope does not purge: **verified**, turning `crawlPages` off left the already-indexed
`SitePages/*.aspx` documents retrievable, because the connector can no longer see them to diff
them as deleted. Deleting the data source is therefore the only purge that exists, and it only
purges if the policy says `DELETE`.

`RETAIN` would make every stale SharePoint chunk permanent for the life of the knowledge base. The
price of `DELETE` is that replacing the resource empties the SharePoint half and re-ingests from
zero — which the verifier asserts, so it is loud rather than silent. For S3, document-level
deletion *is* available, so `RETAIN` keeps its original protective meaning there.

### A second verifier instance, not a second verifier

The previous version of this blueprint listed "extend the verifier" as the step that gets
forgotten, because the handler asserted on one ingestion job and a second data source could sit
empty behind a green stack.

The fix cost zero lines of Python. The handler already takes `KnowledgeBaseId`, `DataSourceId` and
`SmokeQuery` as custom-resource properties, so a second `AWS::CloudFormation::CustomResource`
pointed at the same Lambda verifies the second source. That mattered concretely: inline
`Code.ZipFile` is capped at 4096 characters with ~280 to spare, and a code-touching approach would
probably not have fit.

`DependsOn` sequences the two, because Bedrock rejects concurrent ingestion jobs with a conflict
and two instances racing would spend their 900-second budgets waiting on each other.

The residual gap is stated in the template and in `sharepoint-source.md`: the ingestion statistics
are per-data-source, so an empty SharePoint source cannot pass, but `bedrock:Retrieve` spans the
whole knowledge base, so a smoke query the S3 corpus can also answer weakens assertion five to
nothing. The default `SharePointSmokeQuery` is currently exactly that mistake and is labelled a
placeholder.

### Still rejected: the self-managed SharePoint connector

Preview, and its documentation states only OpenSearch Serverless is available as the vector store
with it — a continuous OCU floor of roughly $350/month, on a shared account, for a blueprint that
indexes a syllabus. It accepts a client secret, which is its only advantage, and that advantage
evaporated the moment a certificate existed.

### The old secret

`dev/workshop/entra/sharepoint` (keys `entraAppID`, `entraAppDirectoryID`, `entraAppSecretID`,
`entraAppSecretValue`) is the client-secret credential from the original app. Nothing in this
blueprint reads it. The connector reads
`bedrock/sharepoint-cert-connector`, which holds exactly `clientId` and `certificatePassword`.

Web crawler remains unbuilt, now purely because nothing asks for it: another
`AWS::Bedrock::DataSource` with `type: WEB` plus a third verifier instance.

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

| `KnowledgeBaseConfiguration` sub-objects and `VectorIngestionConfiguration/ChunkingConfiguration` are create-only | Changing type or embedding model replaces the resource. |
| The schema **accepts** `ChunkingConfiguration` next to a managed embedding model | And the API **rejects** it. See below — the sharpest example of cfn-lint clean meaning less than usual here. |

The Bedrock API returns `connectorParameters` as a **JSON-encoded string**, not an object, which no
document states and which makes the round trip look asymmetric. This template writes it as a YAML
mapping and relies on CloudFormation to marshal it, as the `Json` schema type implies. That was the
last untested assumption in the template until the by-hand rehearsal below; it is now confirmed for
the S3 body, and the SharePoint body is the same mechanism with different keys.

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
- The retrieval action is `bedrock:Retrieve` on
  `arn:aws:bedrock:us-east-1:<account>:knowledge-base/<id>`. `bedrock:RetrieveAndGenerate` exists as
  an IAM action but the API behind it does not serve a managed knowledge base, so it is not granted.
