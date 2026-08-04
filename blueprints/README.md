# blueprints/

One directory per blueprint. A blueprint is a self-contained, governed unit that deploys into
an AWS account the builder never touches.

**This directory's path is load-bearing.** `pipeline/pipeline.yml` names templates under it in
`TemplatePath`, and the Cornell Builder's catalog loader globs `blueprints/*/blueprint.yaml` to
build what `blueprint_search` returns. Rename it and both break — one of them silently, by
returning an empty catalog and falling back to the GitHub API.

```
blueprints/<name>/
├── README.md          builder-facing: what this deploys, how to customize it
├── blueprint.yaml     the manifest the Cornell Builder reads — NOT a CloudFormation template
├── infra/             CloudFormation. One template per logical stack.
│   └── azure/         Terraform, for Microsoft 365 / Entra resources only
└── src/               application code, if the blueprint ships any
```

Later blueprints add `src/`, `skills/`, `docs/`, and `tests/` alongside `infra/`. Everything a
blueprint needs stays inside its own directory — including its container image, which is a
`Dockerfile` with a named target here rather than at the repo root; the Build stage action sets
`CONTAINER_CONTEXT` to this directory.

`infra/azure/` holds Terraform, for Azure/Entra resources only — CloudFormation cannot reach an
Entra tenant, and Terraform is not used for anything with an AWS resource type. A blueprint may
have either directory or both. See "Adding a Terraform module" in `pipeline/README.md`.

**A blueprint without a `blueprint.yaml` is invisible to the Builder.** `blueprint_search` loads
the catalog by globbing `blueprints/*/blueprint.yaml`, so a blueprint that deploys perfectly well
but has no manifest is one no builder can ever be offered. That is correct for a scaffold and
wrong for anything finished — the "Manifest" column below is the catalog, not a formality.

| Blueprint | Manifest | State |
|---|---|---|
| `hello-world` | yes | Fully deploys. Proves the pipeline and the tagging convention, and is the reference for every convention below. |
| `notify-topic` | yes | Fully deploys. One SNS topic with an optional email subscription — the simplest "tell me when X happens" channel, with no compute. |
| `knowledgebase` | yes | Bedrock managed knowledge base over an existing S3 document bucket. Verifies its own ingestion at deploy time, so a green deploy is the acceptance test. SharePoint and web sources pinned. |
| `entra-probe` | no | Fully deploys. Proves the Terraform-from-CodeBuild path reaches the Entra tenant. Terraform only — no AWS resources, so there is no CloudFormation template to advertise. |
| `tiny-chatbot` | yes | Registered `deployed_by: manual` and parked. Flipped to `pipeline` in the PR that wires its Build stage action. |
| `course-chatbot` | **no, on purpose** | **Scaffold — deploys nothing.** Lambda handler and READMEs only: no template, no image target, no registry entry, no pipeline action. Withheld from the catalog until its template exists, so the Builder cannot offer a blueprint that can't deploy. Tracks C and D. |

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

**A `blueprint.yaml` whose `template:` is unregistered fails the same check.** The manifest is the
contract `blueprint_search` returns, so one naming a template that isn't registered — or doesn't
exist — offers a builder a blueprint whose deployment PR cannot deploy. Add the manifest in the
same PR as the template. Until then, no manifest: an absent blueprint is better than a broken one.

**Every parameter passed explicitly by the pipeline.** A blueprint should deploy identically
by hand and through the pipeline. Parameter defaults exist to make a manual deploy possible,
not to be the real values.
