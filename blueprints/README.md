# blueprints/

One directory per blueprint. A blueprint is a self-contained, governed unit that deploys into
an AWS account the builder never touches.

```
blueprints/<name>/
├── README.md          builder-facing: what this deploys, how to customize it
└── infra/             CloudFormation. One template per logical stack.
```

Later blueprints add `src/`, `skills/`, `docs/`, and `tests/` alongside `infra/`.

`infra/azure/` holds Terraform, for Azure/Entra resources only — CloudFormation cannot reach an
Entra tenant, and Terraform is not used for anything with an AWS resource type. A blueprint may
have either directory or both. See "Adding a Terraform module" in `pipeline/README.md`.

| Blueprint | State |
|---|---|
| `hello-world` | Fully deploys. Proves the pipeline and the tagging convention. |
| `entra-probe` | Fully deploys. Proves the Terraform-from-CodeBuild path reaches the Entra tenant. Terraform only — no AWS resources. |
| `knowledgebase` | Bedrock managed knowledge base over an existing S3 document bucket. Verifies its own ingestion at deploy time, so a green deploy is the acceptance test. SharePoint and web sources pinned. |

## Required of every blueprint

**All four `cornell:*` tags on every resource.** `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. These feed inventory and the cost and
usage dashboard, so a resource without them is invisible to the observability work — which
makes it invisible in the demo.

Owner and deployment id vary per deployment and arrive as stack parameters. Blueprint name
and version are properties of the template itself: hardcode the name, and bump the version
default in the same PR that changes the blueprint.

One forced exception, in Terraform only: Entra directory objects have no key/value tag field.
Graph's `application` type takes `tags` as a flat list of strings, so the same four values are
encoded as `"cornell:owner=..."` entries. Still greppable, still required — just the only shape
the API offers. See `entra-probe/README.md`.

**Registered in `pipeline/stacks.yml`, and wired to an action in `pipeline/pipeline.yml`.**
Unregistered templates are not linted by PR checks and PR checks fail on finding one. A
template registered `deployed_by: pipeline` with no action also fails — without that check it
would deploy nothing while the PR and every pipeline stage still reported success.

**Every parameter passed explicitly by the pipeline.** A blueprint should deploy identically
by hand and through the pipeline. Parameter defaults exist to make a manual deploy possible,
not to be the real values.
