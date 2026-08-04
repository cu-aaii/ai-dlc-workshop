# Build instructions — teams-bot

What gets built, by what, and how to build the same thing locally before a PR merges.

## What gets built

One container image, from `blueprints/teams-bot/Dockerfile`, target `teams-bot`. The pipeline's
`ArmContainerBuildProject` builds it with `CONTAINER_TARGET=teams-bot` and
`CONTAINER_CONTEXT=blueprints/teams-bot` (see the Build stage action in `pipeline/pipeline.yml`
and the buildspec in `pipeline/codebuild.yml`). Those two values have to agree with where this
component actually lives — a stale `CONTAINER_CONTEXT` fails the build with a missing-path error
that says nothing about the move that caused it.

The image is built for **linux/arm64**, because `blueprints/teams-bot/infra/teams-bot.yml`
declares the Lambda function with `Architectures: ['arm64']` and the two must agree. On the
pipeline this falls out for free: `ArmContainerBuildProject` runs on CodeBuild's native
`ARM_CONTAINER` environment (`aws/codebuild/amazonlinux2-aarch64-standard:3.0`), so the plain
`docker build` in `pipeline/codebuild.yml` already produces an arm64 image without a `--platform`
flag. A local build on an x86_64 laptop has no such native host and needs `buildx` with an
explicit `--platform` to cross-build (below).

The image installs from `blueprints/teams-bot/src/requirements.lock`, not
`blueprints/teams-bot/src/requirements.txt`. The `.txt` file declares intent as version ranges;
the `.lock` file is what actually gets installed, and it is the exact resolved set for the whole
transitive dependency tree — so two builds of the same commit install byte-identical packages
(SECURITY-10). Editing `requirements.txt` without regenerating the lock changes nothing about
what ships.

The base image, `public.ecr.aws/lambda/python:3.13`, is on a **mutable tag** — not pinned by
digest. This is a dated exception to SECURITY-10, expiring **2026-08-05**; see
`docs/decisions/0001-course-chatbot-base-image-unpinned-for-demo.md` for why, and don't treat it
as closed. Everything else about the image is reproducible: dependencies are pinned in
`requirements.lock`, and the deployed artifact is pinned by digest (see below) — the base layer
is the one floating input.

## Building it locally before merging

Nothing about this component builds on a PR branch — `pipeline/pipeline.yml`'s Source stage
tracks `BranchName: !Ref Environment`, and `Environment` is the literal branch name being
deployed (`main` on the shared pipeline). A branch other than `main` never reaches
`ArmContainerBuildProject` at all, pipeline or no pipeline. So a Dockerfile mistake — a bad
`COPY` path, a lockfile that doesn't resolve, a target that no longer matches
`CONTAINER_TARGET` — is invisible to CI on the PR and only surfaces after merge, in the shared
account. Building the image locally before opening the PR is the only pre-merge check for any
of that.

The command below is written for reference but has **not been run in this environment** — Docker
is not available here. Treat it as untested; confirm it locally before relying on it.

```sh
docker buildx build \
  --platform linux/arm64 \
  --target teams-bot \
  --tag teams-bot:local \
  blueprints/teams-bot
```

The context is `blueprints/teams-bot` (matching `CONTAINER_CONTEXT`), the target is `teams-bot`
(matching `CONTAINER_TARGET`), and `--platform linux/arm64` is required because a typical dev
laptop is not itself arm64 the way `ArmContainerBuildProject`'s CodeBuild host is — without it,
`buildx` builds for the host architecture and the mismatch with the function's
`Architectures: ['arm64']` won't show up until deploy.

This only builds the image; it does not push anywhere; and it does not run the unit tests (see
`unit-test-instructions.md` for those — they run directly against `src/`, with no image build).

## The lock-file regeneration loop

`requirements.lock` carries its own regeneration command in its header:

```sh
uv pip compile blueprints/teams-bot/src/requirements.txt \
    --python-version 3.13 -o blueprints/teams-bot/src/requirements.lock
```

Run this whenever `requirements.txt` changes — a new dependency, a bumped floor or ceiling.
`boto3` stays absent from both files deliberately: the `public.ecr.aws/lambda/python:3.13` base
image already ships it, and adding it here would shadow the runtime's own copy with a second,
unpinned-against-the-runtime version.

`tools/check` does not run a vulnerability scan against the lock file — it's a shared script, not
specific to this blueprint. Run that separately before a release:

```sh
uvx pip-audit -r blueprints/teams-bot/src/requirements.lock
```

## How the image reaches a deploy

Never by tag. `pipeline/codebuild.yml`'s `post_build` phase pushes the image, then resolves and
exports its digest:

```sh
export CONTAINER_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' \
    $CONTAINER_REPOSITORY_URI:$CONTAINER_TARGET-$DATE_TAG)
```

The `TeamsBotDeploy` action in `pipeline/pipeline.yml` then passes
`"ContainerImageUri": "#{TeamsBotContainer.CONTAINER_DIGEST}"` as a CloudFormation parameter, and
`infra/teams-bot.yml`'s Lambda function is declared with `ImageUri: !Ref ContainerImageUri`. So
what actually deploys is a `sha256:...`-addressed image, not a mutable tag — the tag built during
the Build stage (`$CONTAINER_TARGET-$DATE_TAG`) exists only to give `docker push` something to
push; CloudFormation never sees it. That's what "the deployed artifact IS pinned" in the base-image
decision record means in practice: whatever floats in the base layer between builds, the one
CloudFormation actually runs is addressed by content, not by name.

## Not covered here

Deploying the stack, injecting the two Secrets Manager values, wiring the Azure Bot Service
endpoint, and anything else that needs AWS or Entra credentials is out of scope for this
document — see `./integration-test-instructions.md` for that path. This document stops at "the
image builds and the digest reaches CloudFormation."
