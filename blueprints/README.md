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

`skills/`, `docs/` and `tests/` join them as blueprints get real. Everything a blueprint needs
stays inside its own directory, with one exception: container images live as named targets in the
repo-root `Dockerfile`, because `pipeline/codebuild.yml` builds with the repo root as context.

| Blueprint | State |
|---|---|
| `hello-world` | Fully deploys. Proves the pipeline and the tagging convention, and is the reference for every convention below. |
| `course-chatbot` | **Scaffold — deploys nothing.** Lambda handler and READMEs only: no template, no image target, no registry entry, no pipeline action, and no manifest. Tracks B, C and D. |

## Required of every blueprint

**All four `cornell:*` tags on every resource.** `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`. These feed inventory and the cost and
usage dashboard, so a resource without them is invisible to the observability work — which
makes it invisible in the demo.

Owner and deployment id vary per deployment and arrive as stack parameters. Blueprint name
and version are properties of the template itself: hardcode the name, and bump the version
default in the same PR that changes the blueprint.

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
