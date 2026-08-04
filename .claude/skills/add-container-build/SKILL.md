---
name: add-container-build
description: Wire a container image build into the pipeline for a blueprint that needs one (Lambda container image, Bedrock AgentCore runtime, any ECR-hosted image). Use when adding a Dockerfile target, adding a Build stage action, or passing an image digest into a CloudFormation deploy. Covers the digest-not-tag rule and the arm64 AgentCore contract.
---

# Wiring a container image build

Lambda here means container images, so a blueprint that runs code needs an image built and
pushed before its stack deploys. The mechanics (ECR login, digest export) already exist in
`pipeline/codebuild.yml` — wiring a new one is **a Dockerfile target plus a Build stage
action**, not a rediscovery.

`builder-mcp` is the worked example: Dockerfile target → `BuilderMcpContainer` Build action →
digest passed into `BuilderMcpCloudFormation`.

## Step 1 — add a Dockerfile target

One named target per component in the **root** `Dockerfile` — that file holds *every* image in
the repo. **Never add a per-package Dockerfile.** Build context is the repo root, so `COPY`
paths start from there. Keep targets self-contained.

```dockerfile
# --- <name>: <one line on what it is> ------------------------------------------------------
FROM <base> AS <name>

WORKDIR /app

# Dependency layer first so code edits don't re-resolve the environment.
COPY packages/<name>/pyproject.toml packages/<name>/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY packages/<name>/src ./src
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-sync", "<entrypoint>"]
```

Paths depend on where the component lives: `packages/<name>/` for a component that isn't a
blueprint and isn't the deploy path, `blueprints/<name>/src/` for a blueprint's own code.

The target name is what `CONTAINER_TARGET` refers to in step 2 — they must match exactly.

### If it is a Bedrock AgentCore runtime

The AgentCore Runtime contract is **linux/arm64**, MCP over streamable HTTP on
`0.0.0.0:8000/mcp`, stateless. Build it with the **ARM** CodeBuild project
(`ArmContainerBuildProject`), not the x86 one. Bind all interfaces and set stateless mode via
`ENV` in the image, as `builder-mcp` does:

```dockerfile
ENV BUILDER_MCP_HOST=0.0.0.0 \
    BUILDER_MCP_STATELESS=1 \
    BUILDER_MCP_PORT=8000
EXPOSE 8000
```

## Step 2 — add a Build stage action

The `Build` stage runs **before** `BlueprintDeploy`, so the image exists by the time the stack
deploys. Add an action alongside `BuilderMcpContainer`:

```yaml
            - Name: '<Name>Container'
              Namespace: '<Name>Container'
              InputArtifacts:
                - Name: 'GitRepositoryArtifact'
              ActionTypeId:
                Category: 'Build'
                Owner: 'AWS'
                Provider: 'CodeBuild'
                Version: '1'
              Configuration:
                ProjectName: !Ref 'ArmContainerBuildProject'
                EnvironmentVariables: >-
                  [
                  {"name": "CONTAINER_TARGET", "value": "<name>", "type": "PLAINTEXT"},
                  {"name": "DATE_TAG", "value": "#{GitRepository.AuthorDate}", "type": "PLAINTEXT"}
                  ]
```

- **`Namespace` is mandatory** — it is how the digest is referenced downstream. Without it
  `#{<Name>Container.CONTAINER_DIGEST}` resolves to nothing.
- `CONTAINER_TARGET` must equal the Dockerfile target name.
- `DATE_TAG` is normally `#{GitRepository.AuthorDate}`. The buildspec rewrites `:` to `-`
  itself, so pass it raw.
- Pick `ArmContainerBuildProject` for arm64 (AgentCore) targets.

## Step 3 — deploy by digest, not by tag

Pass the exported digest into the blueprint's CloudFormation action:

```yaml
                ParameterOverrides: !Sub >-
                  {
                  "Application": "${Application}",
                  "Environment": "${Environment}",
                  "Owner": "${Owner}",
                  "ContainerImageUri": "#{<Name>Container.CONTAINER_DIGEST}"
                  }
```

`CONTAINER_DIGEST` is declared in `codebuild.yml` under `env.exported-variables`, and holds a
full `repo@sha256:...` reference from `docker inspect`. **Deploy by digest, never by tag** —
a tag is mutable, so a tag-pinned stack can silently drift onto a different image than the
commit produced. The digest guarantees the runtime runs exactly this commit's image.

The receiving template needs a matching parameter:

```yaml
  ContainerImageUri:
    Description: 'Image to run, passed as a digest by the pipeline Build stage'
    Type: 'String'
```

Give it no useful default, or a default that fails loudly — an image reference is not
something to guess at.

## Don't change the buildspec

`pipeline/codebuild.yml` was preserved verbatim from the AI Innovation Lab reference pipeline.
Change the *shape* of the pipeline when a blueprint needs something; don't "improve" the ECR
login, the tagging, or the digest export. If a build needs different behaviour, pass it in as
an environment variable from the Build action.

## Verify

```bash
tools/check
```

`tools/check` lints templates and the registry — it does **not** build the image. A Dockerfile
mistake surfaces in the CodeBuild logs after merge, so read the target carefully before
pushing: it is a shared account and `main` deploys on merge.

Order to confirm in `pipeline.yml`: `Source` → `PipelineDeploy` → `Build` → `BlueprintDeploy`.
A Build action added *after* the deploy stage produces an unresolved digest, not an error.
