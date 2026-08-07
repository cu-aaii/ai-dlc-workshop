# Container image for the dashboard blueprint's two Lambdas, built by the pipeline's ARM CodeBuild
# project (pipeline/codebuild.yml): docker build <this directory> --target <collector|api>. The two
# Build stage actions set CONTAINER_CONTEXT=blueprints/dashboard and CONTAINER_TARGET to the target
# name, so the build context is this directory and COPY paths are relative to it. Keep the named
# targets: CONTAINER_TARGET selects them. Must be built by ArmContainerBuildProject -- the functions
# declare Architectures: [arm64] and the x86 project would produce an image they cannot run.

# Base image pinned by digest (SECURITY-10, like packages/builder-mcp). This is the multi-arch index
# digest of public.ecr.aws/lambda/python:3.13 as of 2026-08-04, obtained via
# `docker buildx imagetools inspect`. Bump deliberately; a mutable tag could change the production
# image between builds with no diff in this repo. The Lambda base image supplies the runtime
# interface client, the code lands in ${LAMBDA_TASK_ROOT}, and CMD names the handler.
FROM public.ecr.aws/lambda/python:3.13@sha256:70e1683986413e2fbdfc8765950d2ef7aaa21a2239726389f92ace0d02fd281c AS base

# Install the dashboard package plus its AWS extra into the Lambda task root. `.[aws]` pulls boto3
# (the extra, not a base dependency -- so U-01's core stays dependency-free); core itself imports
# none of it. Build from a scratch dir so source files don't mingle with the installed package.
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN pip install --no-cache-dir ".[aws]" --target "${LAMBDA_TASK_ROOT}"
WORKDIR ${LAMBDA_TASK_ROOT}

# --- collector: the hourly C-01 job (EventBridge-invoked) --------------------------------
FROM base AS collector
CMD ["dashboard.collector.handler.handler"]

# --- api: the C-03 read API (behind API Gateway / CloudFront) ----------------------------
FROM base AS api
CMD ["dashboard.api.handler.handler"]
