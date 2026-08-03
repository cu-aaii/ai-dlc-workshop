# infra/azure — SharePoint, pinned

`sharepoint-entra.tf.sample` is a **sample**, not a deployable. The `.tf.sample` extension is
deliberate: nothing runs it, and nothing should until the two blockers below are cleared.

## Why it isn't a `.tf`

**There is no Terraform stage.** CLAUDE.md lists "the Terraform stage for Azure/Entra resources"
under *deliberately not built*. There is nowhere for a `.tf` file to execute, so committing one
would imply a pipeline that doesn't exist.

**And the AWS side wouldn't work anyway.** A Bedrock **managed** knowledge base's SharePoint
connector accepts two authentication types:

| Auth type | What it needs | Why it's blocked |
|---|---|---|
| `ENTRA_ID_APP_ONLY` | A **certificate** in Secrets Manager | The workshop's Entra app was provisioned with a client secret. Adding a cert means a new app registration and a Graph admin consent round. |
| `OAUTH2_APP` | An M365 **user's username and password** (resource-owner password grant) | Requires an MFA-exempt account, and puts a human's password in Secrets Manager. Not something to do for a demo. |

The self-managed connector *does* accept a client secret. But it is in preview, and its
documentation states only OpenSearch Serverless is available as the vector store with it — a
continuous OCU floor of roughly $350/month, on a shared account, for a blueprint that indexes one
syllabus. Rejected on cost, not on capability. See `../../docs/decisions.md`.

So the S3 path in `../knowledgebase.yml` is the whole blueprint today, and this directory records
what SharePoint would take rather than pretending it's wired.

## What already exists

The Entra app and SharePoint site were set up by hand during workshop prep. Their credentials live
in **AWS Secrets Manager** at `dev/workshop/entra/sharepoint`, with keys `entraAppID`,
`entraAppDirectoryID`, `entraAppSecretID`, `entraAppSecretValue`.

Nothing in this repo reads those values, and nothing should ever write them into a file here.
This repo is public and **has no secret scanning** — an enforced org security configuration
disables it — so nothing mechanical would stop a committed credential.

The sample references the secret by name only. That is the pattern: blueprints are configured to
*use* credentials without ever containing them.

## Unpinning it

In order, because each step is blocked by the previous one:

1. **Decide the auth story.** Realistically: a new Entra app registration with a certificate,
   certificate in Secrets Manager, `ENTRA_ID_APP_ONLY`. The existing client secret is a dead end
   for the managed connector.
2. **Wire the Terraform stage** — a CodeBuild action that runs `terraform apply` with state
   somewhere durable. Note the org allowed-actions policy permits `hashicorp/setup-terraform@*`
   in GitHub Actions, which is a hint the platform team anticipated this, but the *pipeline* stage
   is still absent.
3. **Add a second `AWS::Bedrock::DataSource`** to `../knowledgebase.yml` with
   `ConnectorParameters` for SharePoint. Remember that block is free-form Json and cfn-lint
   validates nothing inside it.
4. **Extend the verifier**, or accept that it only proves the S3 half. Right now it asserts on
   one ingestion job; two data sources means two jobs, and the current handler would happily go
   green with SharePoint completely empty.

Step 4 is the one that gets forgotten.

## The much smaller win first

The web crawler needs none of this — no Entra, no Terraform, no certificate. It is another
`AWS::Bedrock::DataSource` with `type: WEB` in `ConnectorParameters`, plus step 4 above. If the
goal is "prove the blueprint handles more than one source," that is the cheap version.
