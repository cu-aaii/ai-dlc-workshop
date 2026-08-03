# hello-world

The smallest possible real deployment. Its job is to answer "is the deploy path green?"
without any application in the way, and to be the demo floor if everything more ambitious
has to be cut.

## What it deploys

| Resource | Name | Why it is here |
|---|---|---|
| S3 bucket | `aidlc-main-hello-world-<account>` | A real, taggable, near-free resource, so the deploy path is proven against an actual resource creation and tag-based inventory has something to find. |
| SSM parameter | `/aidlc/main/hello-world/deployed-commit` | Records the commit the pipeline deployed. |

Both carry the full tagging convention: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`.

## Confirming a deploy landed

The deployment marker is the cheapest end-to-end proof — it shows that a specific commit
travelled from a merge, through CodePipeline, into a deployed resource:

```sh
aws ssm get-parameter --profile ai-dlc-workshop \
  --name /aidlc/main/hello-world/deployed-commit \
  --query 'Parameter.Value' --output text
```

Compare it to `git rev-parse origin/main`. They should match after a pipeline run finishes.

And to confirm the tags landed the way inventory expects:

```sh
aws resourcegroupstaggingapi get-resources --profile ai-dlc-workshop \
  --tag-filters 'Key=cornell:deployment-id,Values=aidlc-main-hello-world' \
  --query 'ResourceTagMappingList[].ResourceARN' --output table
```

## Customizing

Don't. This blueprint's value is that it stays boring and always deploys. If you need
somewhere to experiment, copy it to a new blueprint directory and register that one.
