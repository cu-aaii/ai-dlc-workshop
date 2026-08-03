---
name: knowledgebase
description: Deploy or modify the Cornell AI-DLC knowledge base blueprint - a Bedrock managed knowledge base over an S3 document bucket that verifies its own ingestion at deploy time. Use when a builder asks for document search, RAG, "make these documents searchable/queryable", a knowledge base for a chatbot, or when changing what a knowledge base indexes.
---

# knowledgebase blueprint

Produces a query-ready Amazon Bedrock **managed** knowledge base and returns the identifiers a
chatbot needs to query it. Template lives at `blueprints/knowledgebase/infra/knowledgebase.yml`.

## Read these first

- `blueprints/knowledgebase/docs/warnings.md` — before any edit
- `blueprints/knowledgebase/docs/decisions.md` — before proposing an alternative that was rejected
- `blueprints/knowledgebase/README.md` — what deploys and how to consume it

## The two constraints that break naive changes

**Nobody on this track has AWS CLI or console access.** The only way to cause anything is a merge
kicking off the IaC; the only signal back is the pipeline going red or green. Never suggest an
`aws` command as a verification step, a fix, or a prerequisite. If a change would need one, the
change is wrong.

**Every merge to `main` deploys to a shared AWS account, and no feature branch rehearses it.** The
Source stage tracks `BranchName: !Ref Environment` and `Environment` is `[a-z0-9]{1,4}`, so a
feature branch has no pipeline — pushing to one deploys nothing, and a red deploy on `main` is red
for every other track.

For a builder with no account access, `tools/check` is the entire pre-merge signal. Say that
plainly rather than implying a change was tested. For anyone who *does* have account access, a
by-hand `Environment=test` deploy is the rehearsal and is worth doing before any change to the
data source configuration or the verifier — see `docs/warnings.md` for the command.

## Do not do these

| Don't | Why |
|---|---|
| Turn the verifier into a fire-and-forget trigger | It is the only thing distinguishing a green pipeline from an empty knowledge base. See the section below. |
| Add a vector store — S3 Vectors, OpenSearch Serverless, Aurora | `Type: MANAGED` needs none. OpenSearch Serverless bills ~$350/mo continuously. |
| Add `StorageConfiguration` | Absent on purpose for a managed knowledge base, and create-only. |
| Broaden `KnowledgeBaseRole`'s Bedrock statements to `bedrock:*` or `Resource: '*'` | The four embedding-model statements are deliberate and deliberately narrow — the managed service-role docs require them and don't say whether `MANAGED` embedding actually uses them. Keep them scoped. |
| Create the ingestion bucket | Seeding objects needs write access nobody here has, so it would be empty forever and every deploy would fail. |
| Add a `Tags` block to `AWS::Bedrock::DataSource` | The resource has no `Tags` property. cfn-lint will reject it. Use the SSM mirror. |
| Copy a `Key`/`Value` tag list onto `AWS::Bedrock::KnowledgeBase` | Its `Tags` is a **map**, like `AWS::SSM::Parameter`. |
| Wire SharePoint with the existing client secret | Auth-type mismatch, not an oversight. `infra/azure/README.md`. |
| Edit anything under `aidlc-rules/` | Vendored verbatim from upstream. |

## Changing what gets indexed

Point at a different bucket → change `IngestionBucketName` **in two places**: the template default
and the `ParameterOverrides` in `pipeline/pipeline.yml`. The bucket must already exist, be General
Purpose, and be in the same account and `us-east-1`.

Then change `SmokeQuery` to something the new corpus can answer, in the same two places. If you
don't, **every** deploy fails — the verifier asserts the query returns results, and a red
`BlueprintDeploy` stage blocks other blueprints too.

Add a second source (web crawler is the cheap one) → another `AWS::Bedrock::DataSource` with
`type: WEB` in `ConnectorParameters`, **and extend the verifier**. The handler asserts on one
ingestion job, so a second data source can be completely empty while the stack goes green. This
is the step that gets forgotten.

Change chunking → **you can't, and adding a `ChunkingConfiguration` back will fail the deploy.** A
managed embedding model owns chunking; the API rejects any chunking strategy specified alongside it.
This is a tempting edit because the CloudFormation schema accepts the block and cfn-lint passes it
clean. It fails at CREATE. Tuning chunking requires `EmbeddingModelType: CUSTOM` plus a vector
store — a different blueprint, not a parameter.

## Editing the verifier

`IngestionVerifierFunction` uses inline `Code.ZipFile`, hard-capped at **4096 characters** by
CloudFormation. It is at **3814** — roughly 280 to spare, so two or three added lines break it.
There is no S3-bundle fallback without CLI access, so outgrowing the cap forces the unbuilt
container-image path. Keep the handler terse and uncommented; the reasoning lives in the
surrounding template comments, not in the Python. Measure before adding — see `docs/warnings.md`.

**Four properties exist to prevent a hung stack. Preserve all of them.** A custom resource that
never responds leaves CloudFormation waiting, and nobody here can cancel a stuck stack.

1. `import boto3` and both `boto3.client(...)` calls live **inside** `verify()`, inside the `try`.
   Hoisting them to module scope is the easy, tempting mistake: a module-level failure means the
   handler never runs and CloudFormation never hears anything.
2. Every poll loop is bounded by `c.get_remaining_time_in_millis()`, not a fixed iteration count.
   Running long must produce a clean `FAILED`, not a killed invocation.
3. botocore is configured with short connect/read timeouts so one hung call cannot eat the budget.
4. `send()` retries, because a dropped response looks exactly like a hang.

Growing the corpus past a few hundred documents means changing the shape, not the timeout — see
`docs/warnings.md`.

Statistics field names: there is **no `numberOfDocumentsIndexed`**. Use
`numberOfNewDocumentsIndexed` + `numberOfModifiedDocumentsIndexed`. `numberOfDocumentsScanned`
includes unchanged documents, which is what makes the zero-scanned assertion safe on a re-deploy.

The five assertions are the contract. Removing any one of them removes a failure mode from the
only test this blueprint has:

1. data source reaches `AVAILABLE`
2. ingestion job is `COMPLETE`
3. at least one document scanned
4. zero documents failed
5. the smoke query returns at least one result

## Repo rules this blueprint has to satisfy

**All four `cornell:*` tags on every taggable resource**: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. Hardcode the blueprint name; bump the
version default when the blueprint changes — and remember it is also duplicated in
`pipeline/pipeline.yml`, with nothing checking that they agree.

**Stack name `aidlc-<environment>-knowledgebase`.** `BuildPipelineRole` scopes CloudFormation to
`stack/${Application}-${Environment}*`, so a name outside the convention fails with an opaque
authorization error rather than a naming complaint. Note the Bedrock KB `Name` pattern
`^([0-9a-zA-Z][_-]?){1,100}$` allows no doubled separators.

**`Environment` stays `[a-z0-9]{1,4}`.** Don't widen it in this template alone; it is part of the
stack name and the role's resource scope.

**Registered in `pipeline/stacks.yml` AND wired to an action in `pipeline/pipeline.yml`.** Both,
in the same PR as the template. A registered template with no action deploys nothing while every
check reports success — `validate_stacks.py` catches this, but only if the registry entry exists.

**Every parameter passed explicitly from the pipeline.** Template defaults exist so the stack can
be deployed by hand for debugging; they are not the real values.

**No secrets in the repo, ever.** This repo is public and has **no secret scanning** — an enforced
org security configuration disables it. Reference Secrets Manager by name or ARN only. The Entra
credentials at `dev/workshop/entra/sharepoint` are referenced nowhere in the deployed template.

## Verifying a change

```sh
tools/check
```

That is the whole self-serve loop: `validate_stacks.py` for the registry and the pipeline
mirroring, then cfn-lint. `uv` is its only prerequisite.

**cfn-lint clean is a weaker signal here than usual.** `ConnectorParameters` is free-form Json and
the linter validates nothing inside it, so a misspelled key passes clean and fails at deploy in
the shared account. Treat edits inside that block as untested.

After that: push the branch, watch the pipeline, read the verdict. A green `BlueprintDeploy` means
the acceptance test passed — that is the design, because it is the only design that works without
CLI access.
