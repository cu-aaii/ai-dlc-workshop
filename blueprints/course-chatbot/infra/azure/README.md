# course-chatbot/infra/azure/

Terraform for the Microsoft side of the Teams chatbot (track C). Everything behind the bot runs
on AWS; this is the Azure Bot Framework registration, the Entra app, and the Teams app manifest.

**Nothing here yet, and no pipeline stage runs Terraform.** Both are track C's work.

## Why Terraform here and CloudFormation everywhere else

The split is by cloud, not by preference: AWS resources are CloudFormation deployed via
CodePipeline → CodeBuild; **non-AWS resources (Azure/M365 only) are Terraform executed from
CodeBuild.** Same trigger, same governance gate, same "no click-ops" rule. A Terraform stage is
a CodeBuild action with a buildspec — `pipeline/codebuild.yml` is the pattern to copy, and the
org allowed-actions policy permits `hashicorp/setup-terraform@*` if a PR check ever needs a
`terraform validate`.

## Two things that will bite

- **State.** Terraform needs a backend, and there isn't one. An S3 backend with a DynamoDB lock
  table belongs in `bootstrap/account-bootstrap.yml` — it is account baseline, not per-blueprint
  infrastructure, and it has to exist before the first `terraform apply` rather than being
  created by it.
- **Credentials.** A service principal that can register a bot is a secret, so it lives in AWS
  Secrets Manager and is read at deploy time. Never in a `.tfvars`, never in this repo — this
  repository is public and has no secret scanning, so nothing will stop a committed credential.

Add `*.tfstate*` and `.terraform/` to `.gitignore` before the first apply, not after.

## Governance still applies

The four `cornell:*` tags are an AWS-inventory convention, but the deployment they belong to
spans both clouds. Tag the Azure resources with the same owner and deployment id — track E has
to be able to answer "what is this and whose is it" about the Teams app too, and the answer
cannot live only in someone's memory of which bot belongs to which course.
