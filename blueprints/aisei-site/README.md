# aisei-site

A standalone Angular + Hono web app, packaged as a single Lambda container behind a
public Function URL. `app/` is a vendored, unmodified copy of `aisei-site`
(the AII base-template scaffold) — the app itself has no idea it's running in Lambda; the
[AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) bridges the
gap by running `node dist/server/index.js` and forwarding each invocation to it over HTTP.

It exists as a minimal demo of the other direction from tiny-chatbot: instead of writing a
handler for this repo's deploy path, it takes an app that already exists elsewhere and
deploys it unchanged. No auth, no state, no LLM.

**Status: parked.** Registered `deployed_by: manual` in `pipeline/stacks.yml` and not
wired to a pipeline action, on purpose, until the hello-world deploy path is verified
end to end.

## What it deploys

All resources are behind a `HasImage` condition (mirroring builder-mcp's and
tiny-chatbot's bootstrap pattern): with `ContainerImageUri` empty the stack validates and
deploys nothing, which is all a parked blueprint needs.

| Resource | Name | Why it is here |
|---|---|---|
| Lambda function | `aidlc-main-aisei-site` | Container image (arm64); the app's own Hono server, run behind the Lambda Web Adapter. |
| Function URL | output `FunctionUrl` | `AuthType: NONE` — a public demo site, `data_classification: public`, nothing stored. |
| IAM role | `aidlc-main-aisei-site-exec` | Basic logging only, scoped to the function's own log group. |
| Log group | `/aws/lambda/aidlc-main-aisei-site` | Tagged, 30-day retention, cleaned up with the stack. |

Every taggable resource carries the full convention: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`.

Like tiny-chatbot, this blueprint takes a `DeploymentName` parameter, so several sites
can coexist per environment.

## Why the Lambda Web Adapter, not `hono/aws-lambda`

Hono ships a Lambda adapter (`hono/aws-lambda`) that would mean rewriting
`app/server/index.ts` to export a handler instead of calling `serve()`. The Lambda Web
Adapter avoids that: it runs as a Lambda extension that starts the app's own
`npm start` equivalent (`node dist/server/index.js`) and proxies invocations to it over
HTTP on `$PORT`. That keeps `app/` a byte-for-byte copy of the source app, so the same
image works unchanged if the app is ever run somewhere that isn't Lambda.

`app/server/app.config.ts` already reads `PORT` (default 4300), and `app/server/app.ts`
already exposes `GET /health`, which is why this app needed zero code changes to fit the
adapter's contract — `AWS_LWA_READINESS_CHECK_PATH=/health` in the Dockerfile just points
the adapter at the route that was already there.

## Flipping it live

Three steps, one PR, once hello-world has deployed green:

1. Add a `Build` stage action in `pipeline/pipeline.yml` running
   **`ArmContainerBuildProject`** — not the x86 `ContainerBuildProject`; the Lambda below
   declares `Architectures: [arm64]`, and an x86 image would crash at invoke — with
   `CONTAINER_TARGET=aisei-site`, `CONTAINER_CONTEXT=blueprints/aisei-site` (the
   directory holding this blueprint's `Dockerfile`) and `DATE_TAG`, per "Adding a
   container image build" in `pipeline/README.md` and the `BuilderMcpContainer` action
   as the working example.
2. Add a `BlueprintDeploy` CloudFormation action modelled on `HelloWorldCloudFormation`,
   passing every parameter explicitly — including
   `ContainerImageUri: #{AiseiSiteContainer.CONTAINER_DIGEST}` (deploy by digest, not
   tag) and `DeploymentName`.
3. Change this blueprint's entry in `pipeline/stacks.yml` to `deployed_by: 'pipeline'` —
   `validate_stacks.py` fails a `pipeline` entry with no action and a `manual` entry with
   one, so steps 2 and 3 must land together.

Also pin both base images in `Dockerfile` by digest (SECURITY-10, like builder-mcp's
Dockerfile) in that same PR.

## Testing locally

Unlike tiny-chatbot, `CMD` here is just the app's own server — the Lambda Web Adapter is
a Lambda extension with no effect outside Lambda, so a plain container run serves the app
directly on `$PORT`:

```sh
# From the repo root:
docker build -t aisei-site blueprints/aisei-site
docker run -p 4300:4300 aisei-site
# then open http://localhost:4300 in a browser, or curl http://localhost:4300/health
```
