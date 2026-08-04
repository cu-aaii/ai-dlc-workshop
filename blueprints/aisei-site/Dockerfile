# Container image for the aisei-site blueprint, built by the pipeline's ARM CodeBuild
# project (pipeline/codebuild.yml) once its Build stage action is wired with
# CONTAINER_TARGET=aisei-site and CONTAINER_CONTEXT=blueprints/aisei-site -- see
# "Adding a container image build" in pipeline/README.md. The build context is this
# directory, so COPY paths below are relative to it. Keep the named target:
# CONTAINER_TARGET selects it.

# --- aisei-site: Angular + Hono app, run in Lambda via the AWS Lambda Web Adapter -------
# app/ is a vendored copy of aisei-site (../../../aisei-site), unmodified except for
# leaving out .env. Rather than porting the Hono server to hono/aws-lambda, the AWS Lambda
# Web Adapter (github.com/awslabs/aws-lambda-web-adapter) runs as an extension that starts
# the server's own `node dist/server/index.js` and forwards each invocation to it over
# HTTP on $PORT -- so app/server needs no Lambda-specific code. Built by the ARM CodeBuild
# project (linux/arm64). Both base images are pinned by digest (SECURITY-10, like
# builder-mcp's Dockerfile); resolved with `crane digest --platform=linux/arm64 <image>`.

FROM node:24-alpine@sha256:0e6f1567e269207c28295276928277a030139cbc5a0fb7d5bd2674f0401a9082 AS build

WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ .
RUN npm run build
RUN npm prune --omit=dev

FROM node:24-alpine@sha256:0e6f1567e269207c28295276928277a030139cbc5a0fb7d5bd2674f0401a9082 AS aisei-site

WORKDIR /var/task
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1@sha256:cd0ad9539cbf223feb1cabd8f4deb7064b6270f185614274b940a36590cdc8f9 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./

# aisei-site's own server (app/server/app.config.ts) reads PORT, defaulting to 4300;
# the adapter needs it to know where to forward invocations. AWS_LWA_READINESS_CHECK_PATH
# points it at aisei-site's existing GET /health route so the adapter waits for the Hono
# server to be up before serving traffic.
ENV PORT=4300
ENV AWS_LWA_READINESS_CHECK_PATH=/health

CMD ["node", "dist/server/index.js"]
