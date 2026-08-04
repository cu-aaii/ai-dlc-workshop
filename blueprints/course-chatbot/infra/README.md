# course-chatbot/infra/

CloudFormation for this blueprint. One template per logical stack; `infra/azure/` holds the
Terraform for the Microsoft side.

**Nothing here yet.** See "Wiring it up" in the [blueprint README](../README.md) for the four
steps, and [`../../hello-world/infra/hello-world.yml`](../../hello-world/infra/hello-world.yml)
for a template that satisfies every convention in about sixty lines.

## What the pipeline needs from a template here

- **All four `cornell:*` tags on every resource** — `cornell:owner`, `cornell:blueprint`,
  `cornell:blueprint-version`, `cornell:deployment-id`. Owner and deployment id arrive as
  parameters; hardcode the blueprint name, and bump the version default in the same PR that
  changes the blueprint. An untagged resource is invisible to track E, which makes it invisible
  in the demo.
- **A stack name of `<application>-<environment>-<name>`.** `BuildPipelineRole` scopes its
  CloudFormation permissions to `stack/${Application}-${Environment}*`, so a stack named outside
  the convention fails with an opaque authorization error rather than a naming complaint.
- **`Environment` capped at `[a-z0-9]{1,4}`.** Four characters, no hyphens, because it lands in
  the stack name and the IAM prefix. Every template in this repo declares that pattern.
- **Every parameter passed explicitly by the pipeline.** Defaults exist so the stack can be
  deployed by hand for debugging; they are not the real values.

Unlike `hello-world`, take a `DeploymentName` parameter. `hello-world` hardcodes its bucket name
and deployment id, which is why its manifest says `singleton: true` — only one can exist per
application/environment. A real blueprint gets deployed more than once.

Deploying a container image means a `Build` stage action that exports `CONTAINER_DIGEST` and a
`ContainerImageUri` parameter here, so the stack always runs exactly the image its commit
produced. `pipeline/codebuild.yml` already handles the ECR login and digest export;
`packages/builder-mcp/infra/builder-mcp.yml` is the worked example.
