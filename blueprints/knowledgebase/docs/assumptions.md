# Assumptions

What has to already be true for this blueprint to deploy. Each one is a thing that will fail the
deploy if it isn't, and most of them fail in a way that doesn't name itself.

## The bucket

**`aidlc-kb-ingestion-890349359349` exists, in the same AWS account and in `us-east-1`.**

Verified, not assumed — and the verification mattered. The bucket this blueprint originally pointed
at, `aidlc-kb-ingestion-bucket`, is in **`us-east-2`**. The managed S3 connector is same-region
only, so the first create would have failed, and a failed first create leaves `ROLLBACK_COMPLETE`,
which blocks every subsequent merge for every track. `aidlc-kb-ingestion-890349359349` was created
in `us-east-1` with all four `cornell:*` tags and the syllabus copied into it.

Same-account is what lets the template omit `bucketOwnerAccountId`. Pointing this at a bucket in
another account means adding that property and revisiting the `aws:ResourceAccount` condition on
`KnowledgeBaseRole`'s S3 statements; pointing it at another region does not work at all.

**It is a General Purpose bucket, not a Directory bucket.** The managed connector does not accept
Express One Zone.

**It contains at least one document the smoke query can answer.** Currently
`Syllabus-SP26-CS1112-LEC001-PRIOR-TERM.pdf`, and `SmokeQuery` defaults to a question about a late
homework policy. Empty the bucket and every deploy fails on the zero-documents assertion — which
is intended, but the failure reads as a broken blueprint if you don't know that.

**It carries all four `cornell:*` tags, but it is still not IaC.** It was created by hand, because
a bucket this template created would be empty on the deploy that created it and would fail the
zero-documents assertion. So Track E's inventory can see it, but nothing in the repo describes it
and a `terraform`-style drift check would not notice it disappearing. The honest fix is a
CloudFormation *import* in a follow-up PR.

The `us-east-2` bucket `aidlc-kb-ingestion-bucket` still exists, untagged and now unreferenced.
Someone should delete it; nothing here does.

## The account

**Bedrock managed knowledge bases are available and not blocked by an SCP or a service quota.**
GA in `us-east-1` since 17 June 2026. No foundation-model access needs enabling, because managed
embedding is AWS's model rather than one the account invokes.

**`cloudformation-deploy-role` can create Bedrock resources.** It holds `AdministratorAccess`, so
this holds today. It is worth knowing it is the thing being relied on.

**The stack name stays inside `${Application}-${Environment}*`.** `aidlc-main-knowledgebase` does.
A stack named outside that prefix cannot be deployed by the pipeline at all, and the failure is an
opaque authorization error rather than a naming complaint.

## The runtime

**The `python3.13` bundled `boto3` supports `bedrock-agent`'s `get_data_source`,
`start_ingestion_job` and `get_ingestion_job`, and `bedrock-agent-runtime`'s `retrieve`.**

All four are long-standing APIs, so this is a safe bet — but a bundled-SDK lag is the plausible
cause if the verifier fails with an unknown-method or unknown-parameter error rather than a
Bedrock error. There is no vendored-dependency escape hatch here, because inline `Code.ZipFile`
cannot carry one and we have no CLI to upload a bundle.

**The whole verify cycle fits in 900 seconds.** The polling budget is 240s waiting for the data
source plus 550s waiting for ingestion. One syllabus takes seconds. See `warnings.md` for what
happens at real volume.

## The corpus

**Small enough that ingestion is fast, and stable enough that a fixed smoke query keeps working.**

Both of these are true for one PDF and neither survives contact with a real document set. Growing
the corpus means revisiting the timeout and probably making the smoke query less specific.

## Out of scope, deliberately

**SharePoint is pinned.** `infra/azure/sharepoint-entra.tf.sample` is illustrative and is not
pipeline-runnable — CLAUDE.md lists the Terraform CodeBuild stage as deliberately not built. The
Entra app and secret `dev/workshop/entra/sharepoint` exist, but nothing in this blueprint reads
them, and the reason is an auth-type mismatch documented in `decisions.md`, not an oversight.

**No teardown automation.** Nothing in this repo has any, because until now everything was S3 and
SSM and effectively free. This blueprint is the first thing that bills while idle.
