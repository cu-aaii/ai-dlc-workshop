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

The template passes `bucketOwnerAccountId: !Ref 'AWS::AccountId'`, so same-account is what makes that
correct — it is a required property either way, not a cross-account one (see `warnings.md`). Pointing
this at a bucket in another account means hardcoding that owner id and revisiting the
`aws:ResourceAccount` condition on `KnowledgeBaseRole`'s S3 statements; pointing it at another region
does not work at all.

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

## The SharePoint source — now live, so these are hard prerequisites

`EnableSharePointSource` is `true`, so every item below is a prerequisite for **every track's
merges**, not a hypothetical. They were all satisfied during the rehearsal that preceded turning it
on; what follows is what has to stay true. Detail and the how in `sharepoint-source.md`.

**The knowledge base is `Type: MANAGED`.** Not a preference in this context: a customer-managed
knowledge base supports S3 and Custom data sources only, and attaching SharePoint to one fails at
*sync* time with an error that blames the secret.

**An Entra app registration exists with a live certificate, and it is not the original one.** The
app registered during workshop prep uses a client secret, which `ENTRA_ID_APP_ONLY` cannot use. The
connector's app has a certificate and should have no client secret at all.

**Both resource applications are consented.** Microsoft Graph
(`00000003-0000-0000-c000-000000000000`) *and* the SharePoint REST API
(`00000003-0000-0ff1-ce00-000000000000`), each with an application-permission grant. Graph alone
yields a token that reads site metadata and fails on content, which surfaces as a scope error rather
than as a partial success.

**The site named by `SharePointSiteUrl` has an explicit per-site grant.** `Sites.Selected` on its
own grants nothing. The grant is a Graph `POST` issued by a principal holding
`Sites.FullControl.All`, and it survives the deletion of the app that issued it — verified. The
parameter holds one site; the template renders `siteUrls` as a one-element list, so more than one
site is a `ConnectorParameters` edit rather than a parameter value.

**The certificate has not expired.** A date, not a configuration, and nothing in this repo watches
it — the Entra side is managed by hand by the platform team, so the date lives with them. This is the
most likely cause of a SharePoint failure appearing without anyone changing anything, and now that
the flag is on it takes every track's merges with it.

**The `.p12` is at `s3://<SharePointCertificateBucket>/<SharePointCertificateKey>`, under a
prefix.** The connector fetches it itself and also probes for a sibling `<key>.metadata.json`, so
the role grants `GetObject` on the prefix rather than the object — a key at the bucket root would
make that probe a denied call.

**The secret holds exactly `clientId` and `certificatePassword`.** camelCase, those two keys, for
`ENTRA_ID_APP_ONLY`. Wrong names fail with the same generic error as a wrong knowledge base type.
`bedrock/sharepoint-cert-connector` is that secret; `dev/workshop/entra/sharepoint` is the old
client-secret credential and is read by nothing here.

**`SharePointSmokeQuery` is answerable from the SharePoint corpus and *not* from the S3 bucket.**
Retrieval spans the whole knowledge base, so a question both corpora answer makes the assertion prove
nothing. `What do the ECE 4960 handouts cover?` was measured at 5/5 SharePoint chunks. If the handouts
change substantially, re-measure it. See `warnings.md`.

## Scheduled re-sync, only when it is enabled

**Nothing watches it.** `EnableScheduledSync` is `false` by default; when it is `true`, the
assumption being made is that an unverified weekly `StartIngestionJob` is worth having. Scheduler
cannot check a result — `get`, `list` and `retrieve` are all blocked prefixes — so the assumption
cannot be validated from inside the stack, only from the console by someone with access.

**`bedrockagent` is the right SDK service identifier for the universal-target ARN.** Nothing
validates that string; a wrong one fails at invocation time, unobserved. It is the one thing in the
schedule worth confirming during the `Environment=test` rehearsal, by reading Bedrock's ingestion-job
history after the first fire rather than by trusting the stack.

**Ingestion jobs conflict, so the two schedules are offset by an hour.** Whether the concurrency
limit is per data source or per knowledge base has not been tested here; the offset makes it moot.

## Out of scope, deliberately

**The Entra half is not pipeline-runnable from this blueprint.**
`infra/azure/sharepoint-entra.tf.sample` records the shape of the app registration, its consent and
its certificate, but it stays a `.tf.sample`: no `Terraform` stage action names this directory, and
`validate_stacks.py` cross-checks that in both directions, so a real `.tf` here would fail PR
checks until the action exists. The certificate generation and the per-site grant are by-hand steps
regardless.

**No teardown automation.** Nothing in this repo has any, because until now everything was S3 and
SSM and effectively free. This blueprint is the first thing that bills while idle. Note that the
two halves do not tear each other down: deleting the stack leaves the Entra app and the
certificate, and `terraform destroy` leaves the knowledge base.
