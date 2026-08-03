# bootstrap/

Account baseline. Everything in here is deployed **by hand, once per AWS account**, and
nothing else in the repo is.

That is not an exception to "everything deploys through GitHub" so much as its starting
condition: `account-bootstrap.yml` creates the role CodePipeline passes to CloudFormation,
the bucket CodePipeline stores artifacts in, and the connection CodePipeline clones through.
The pipeline cannot create its own preconditions.

## Deploy it

```sh
aws cloudformation deploy \
  --profile ai-dlc-workshop \
  --region us-east-1 \
  --stack-name aidlc-account-bootstrap \
  --template-file bootstrap/account-bootstrap.yml \
  --capabilities CAPABILITY_NAMED_IAM
```

`CAPABILITY_NAMED_IAM` is required because `cloudformation-deploy-role` has a fixed name —
`pipeline/pipeline.yml` refers to it by name, so it cannot be a generated one.

## Then finish the GitHub handshake

The connection is created `PENDING`. CloudFormation cannot complete the OAuth handshake, so
a human has to:

1. Open **CodePipeline → Settings → Connections** in `us-east-1` (the stack's
   `CompleteTheHandshakeHere` output links straight there).
2. Select the `cu-aaii` connection → **Update pending connection**.
3. Authorize the AWS Connector GitHub app for the organization and install it on the
   `ai-dlc-workshop` repository.

Confirm before deploying the pipeline:

```sh
aws codeconnections list-connections --profile ai-dlc-workshop \
  --query 'Connections[].[ConnectionName,ConnectionStatus]' --output table
```

`ConnectionStatus` must read `AVAILABLE`. A `PENDING` connection makes the pipeline's Source
stage fail with a permissions error that does not mention the handshake.

Connections are per-account and cannot be shared across accounts, so a second workshop
account needs its own connection and its own handshake.

## What it creates

| Resource | Name | Why |
|---|---|---|
| IAM role | `cloudformation-deploy-role` | CodePipeline passes it to CloudFormation for every stack deploy. `AdministratorAccess`, matching the reference account — it has to be able to create whatever a blueprint declares. |
| S3 bucket | `deployment-artifacts-<account>-<region>` | CodePipeline artifact store. Versioning is mandatory for a CodePipeline S3 store; a 30-day expiry keeps it from growing without bound. |
| CodeConnections connection | `cu-aaii` | How CodePipeline clones from GitHub. |
| SSM parameter | `/code-connections/cu-aaii` | Holds the connection ARN so `pipeline/pipeline.yml` carries no account-specific values. |
