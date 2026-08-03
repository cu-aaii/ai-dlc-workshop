# Azure side of course-chatbot (draft design)

**Status:** Draft. Produced by Track C on Day 1 to unblock Track 0. Not a spec.
Push back on any resource shape, seam, or approval assumption before writing Terraform.

**Why this file exists:** `blueprints/README.md` says future blueprints add `infra/azure/`
alongside `infra/` for the Terraform side, and CLAUDE.md lists `course-chatbot` and the
Terraform stage among the things deliberately not built yet. Track 0 owns the pipeline
stage that runs Terraform; Track C owns what that Terraform is *for*. This is Track C
naming the shape of the first real Azure-side deploy so Track 0 has a concrete example
to wire into a stage, and so the C ↔ 0 seam is agreed on paper before either side
writes production code.

## What this deploys

The Microsoft Teams frontend for the `course-chatbot` blueprint: an Entra app
registration, an Azure Bot Service tied to it, the Teams channel enabled on that bot,
and the Teams app package that end users install. The AWS side of `course-chatbot`
(Lambda that answers, Bedrock Knowledge Base retrieval via Track B) is a peer
CloudFormation stack under `infra/`, not this file.

## Cross-track seams (read this first)

Three seams. Any of them shifting invalidates the resource shape below.

**Seam 1, messaging endpoint URL (C ↔ AWS side of C, resolves inside this track).**
Azure Bot Service needs a public HTTPS `endpoint` at create time. That URL is served
by the AWS-side Lambda, which does not exist until its stack deploys. Two workable
patterns:

- **Two-phase.** First Terraform pass creates the bot with a placeholder endpoint;
  AWS-side stack deploys and exports its URL; second pass updates the bot. Adds an
  ordering constraint to the pipeline and one visible "endpoint is a placeholder"
  state.
- **Output-plumbing.** AWS-side stack deploys first, exports the endpoint URL to a
  known SSM parameter, Terraform reads it. Cleaner, but couples Terraform to
  parameter-store reads and forces a strict "AWS side before Azure side" order in the
  pipeline.

Track 0's call, since it lands in the pipeline shape.

**Seam 2, bot identity (C ↔ AWS side of C).** The Lambda validates incoming Bot
Framework request signatures using the bot's Microsoft App ID and either a client
secret or a federated identity credential. Recommendation: **federated identity
credential**, so no secret exists to leak into the public repo. Client ID becomes a
Lambda env var passed by CloudFormation; the federated credential is configured on
the Entra app registration (this Terraform) with the AWS Lambda's role ARN. If Cornell
governance forbids that, fall back to a client secret in AWS Secrets Manager: per
CLAUDE.md the secret never touches this repo.

**Seam 3, retrieval interface (C ↔ B).** Not this file's concern, but named here so
it stays visible: the Lambda calls into Track B's KB retrieval interface, which is
still unagreed. Track that in the session log, not here.

## Resources

Rationale, not code. Terraform provider `hashicorp/azurerm` (bot service, channels)
plus `hashicorp/azuread` (app registration).

| Resource | Purpose | Notes |
|---|---|---|
| `azuread_application` | The bot's identity in Cornell's Entra tenant. | Client ID becomes the Bot Framework `Microsoft App ID`. |
| `azuread_application_federated_identity_credential` | Lets AWS Lambda auth to Bot Framework without a secret. | Issuer + subject tied to the Lambda's IAM role. Depends on AWS-side ARN existing. |
| `azuread_service_principal` | Materializes the app in the tenant. | Required before Bot Service can reference it. |
| `azurerm_bot_service_azure_bot` | The bot registration in Azure. | `messaging_endpoint` is Seam 1. SKU `F0` for the workshop. |
| `azurerm_bot_channel_ms_teams` | Enables the bot on Teams. | Turn calling/meeting off unless a story needs them, for a smaller consent surface. |

Teams app package (`manifest.json` + icons, zipped) is a build artifact, not a
Terraform resource. Produced from a template that substitutes the Microsoft App ID
after the app registration is created, then either sideloaded for the demo or
submitted to Cornell's Teams app catalog for real use. Publishing path is a Cornell
approval question, not a Terraform question.

## Inputs

Every parameter passed explicitly, following the same convention as the CFN side.
Nothing gets a default that pretends to be a real value.

| Name | Source | Notes |
|---|---|---|
| `tenant_id` | Track 0 / Cornell M365 admin | Cornell's Entra tenant ID. |
| `subscription_id` | Track 0 | The Azure subscription that hosts the Bot Service resource. Open question: does Cornell have a shared subscription for this? |
| `resource_group_name` | Track 0 | Where Bot Service lives. Assumed pre-existing. |
| `bot_display_name` | Blueprint parameter | `course-chatbot` for the demo. |
| `owner` | Deployment-time input | Mirrors `cornell:owner` on the AWS side. |
| `blueprint_version` | Blueprint | Mirrors `cornell:blueprint-version` on the AWS side. |
| `messaging_endpoint` | Seam 1 | Placeholder or SSM-sourced depending on which pattern Track 0 picks. |
| `aws_lambda_role_arn` | AWS-side output | For the federated identity credential's subject. Required only if seam 2 uses federated identity. |

## Outputs

| Name | Consumer | Notes |
|---|---|---|
| `microsoft_app_id` | AWS-side Lambda | Env var. Not secret; safe as a CloudFormation parameter. |
| `bot_id` | Observability / Track E | Uniquely identifies the bot in Azure for audit. |
| `teams_app_id` | Teams app manifest build | Used to fill the manifest. |

## Tagging

Azure tags are a flat `map(string)`, unlike the list-of-Key/Value shape used on the
AWS side. Every resource that supports tags carries the same four keys with the same
values as the AWS side of this blueprint, so a single `cornell:deployment-id` value
identifies the resources of one deployment across both clouds:

- `cornell:owner`
- `cornell:blueprint` (`course-chatbot`)
- `cornell:blueprint-version`
- `cornell:deployment-id`

`azuread_application` and its federated credential do not support Azure resource tags
(they live in Entra, not ARM). That's an unavoidable gap for Track E's inventory.
Name it and move on.

## Cornell approvals required

Not blockers Track 0 can fix by writing better Terraform. Naming them here so nobody
rediscovers them Monday night.

- **Tenant admin consent for the Entra app registration.** Someone with Cornell M365
  Application Admin or Global Admin role has to consent to the app's permissions.
  Track 0 should confirm who owns this at Cornell and how long it takes.
- **Azure subscription with rights to create Bot Service resources.** Not a
  guaranteed thing at Cornell. If none exists, this is the single biggest blocker for
  the demo and needs a Day 1 answer, not a Day 2 discovery.
- **Teams admin approval to publish or sideload the bot.** Sideloading for the
  demo is the fast path; org-wide publish is post-workshop.
- **Federated identity credential** (if seam 2 uses it): the tenant must permit
  cross-cloud federated credentials from an AWS OIDC issuer. Some tenants block this
  by policy.

## Verify

Track C's standing rule is that anything built here checks its own work before it
reports success. For the Terraform side:

- **CI-time (in the pipeline stage Track 0 builds):** `terraform fmt -check`,
  `terraform validate`, `terraform plan -detailed-exitcode` against the previous
  applied state. Non-zero drift fails the check.
- **Post-apply:** query the deployed bot and assert (a) `messaging_endpoint` matches
  the value in the AWS-side stack's output, (b) Teams channel is `enabled`, (c) the
  Microsoft App ID on the bot matches the Entra app registration. Any mismatch fails
  the deploy, does not just warn.
- **End-to-end (the demo itself):** send a Teams message, receive a grounded
  response. This is beat 6 of the demo, so the demo IS the verify. Track 0's stage
  should still gate on the post-apply checks above so the room does not find out
  during the demo.

## Open questions

- **Does Cornell have an Azure subscription for hosting Bot Service resources?**
  If not, everything above is moot. Ask Track 0 today.
- **Federated identity or client secret?** Recommendation is federated. Depends on
  Cornell tenant policy.
- **Sideload or full publish?** Sideload for the demo unless anyone objects.
- **State backend for Terraform.** S3 in the shared AWS account is the natural fit
  and reuses infrastructure Track 0 already touches. Track 0's call.
- **Two-phase deploy or SSM plumbing** for the messaging endpoint (seam 1). Track
  0's call.
- **How does the Teams app manifest get built?** Terraform can render it from a
  template, or a small CodeBuild step can. Either is fine; the seam is where the
  Microsoft App ID gets substituted.
