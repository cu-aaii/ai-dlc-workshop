# blueprints/

One directory per blueprint. A blueprint is a self-contained, governed unit that deploys into
an AWS account the builder never touches.

```
blueprints/<name>/
├── blueprint.yaml     the builder-facing contract the Cornell Builder MCP reads
├── README.md          builder-facing: what this deploys, how to customize it
└── infra/             CloudFormation. One template per logical stack.
```

Later blueprints add `src/`, `skills/`, `docs/`, and `tests/` alongside `infra/`.

`infra/azure/` holds Terraform, for Azure/Entra resources only — CloudFormation cannot reach an
Entra tenant, and Terraform is not used for anything with an AWS resource type. A blueprint may
have either directory or both. See "Adding a Terraform module" in `pipeline/README.md`.

| Blueprint | State | In the builder catalog |
|---|---|---|
| `hello-world` | Fully deploys. Proves the pipeline and the tagging convention. | yes |
| `entra-probe` | Fully deploys. Proves the Terraform-from-CodeBuild path reaches the Entra tenant. Terraform only — no AWS resources. | no — exempt, see below |
| `knowledgebase` | Bedrock managed knowledge base over an existing S3 document bucket. Verifies its own ingestion at deploy time, so a green deploy is the acceptance test. SharePoint and web sources pinned. | yes |
| `tiny-chatbot` | Experimental. Canned-response chat page behind a public Lambda Function URL; parked at `deployed_by: manual` until its Build action is wired. | yes |

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

**A `blueprint.yaml` manifest, or a `MANIFEST_EXEMPT` entry saying why not.** The Cornell
Builder MCP builds its catalog by globbing `blueprints/*/blueprint.yaml`. A blueprint with no
manifest deploys perfectly and **no builder can find it** — `blueprint_search` skips the
directory with no error, so the failure shows up as a plausible wrong answer rather than an
empty one. `knowledgebase` was invisible this way: asking for a knowledge base returned
`tiny-chatbot` as the top hit.

The field contract is C1 in `builder-mcp/SPEC.md`. Two rules in it are load-bearing and easy to
miss: a manifest must never contain the CloudFormation template-format-version key, even in a
comment (`validate_stacks.py` finds templates by text scan and would hand the manifest to
cfn-lint), and `metadata.version` stays in lockstep with the template's `BlueprintVersion`
default — out of lockstep, the version the catalog shows is not the version the
`cornell:blueprint-version` tag records. `tools/check` enforces the manifest's presence, its
name, its template being registered, and that lockstep.

`entra-probe` is the one exemption, and it is a real limitation rather than outstanding work: a
manifest's `template` is a CloudFormation path and `deployment_create` renders a CloudFormation
action from it, so a Terraform-only blueprint cannot be a catalog entry yet.
