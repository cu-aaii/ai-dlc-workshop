# tiny-chatbot

The world's tiniest chatbot: a canned-response Lambda behind a public Function URL. No
LLM, no state, no dependencies — every reply is a hardcoded string in `src/app.py`, chosen
by a handful of pattern-matching rules. It opens with "Hey! I'm a chatbot. Chitty chitty
chop chop."

It exists because hello-world proves the deploy path but deploys nothing you can *see* —
a bucket and an SSM parameter make a poor demo. This is the first blueprint whose deploy
ends with a URL you can open in a browser, and the first to exercise the container image
path (Lambda means container images).

**Status: parked.** Registered `deployed_by: manual` in `pipeline/stacks.yml` and not
wired to a pipeline action, on purpose, until the hello-world deploy path is verified
end to end.

## What it deploys

All resources are behind a `HasImage` condition (mirroring builder-mcp's bootstrap
pattern): with `ContainerImageUri` empty the stack validates and deploys nothing, which is
all a parked blueprint needs.

| Resource | Name | Why it is here |
|---|---|---|
| Lambda function | `aidlc-main-tiny-chatbot` | Container image (arm64), serves the chat page on GET and canned replies on POST. |
| Function URL | output `FunctionUrl` | `AuthType: NONE` — a public demo page, `data_classification: public`, nothing stored. |
| IAM role | `aidlc-main-tiny-chatbot-exec` | Basic logging only, scoped to the function's own log group. |
| Log group | `/aws/lambda/aidlc-main-tiny-chatbot` | Tagged, 30-day retention, cleaned up with the stack. |

Every taggable resource carries the full convention: `cornell:owner`, `cornell:blueprint`,
`cornell:blueprint-version`, `cornell:deployment-id`.

Unlike hello-world, this blueprint takes a `DeploymentName` parameter, so several chatbots
can coexist per environment.

## Flipping it live

Three steps, one PR, once hello-world has deployed green:

1. Add a `Build` stage action in `pipeline/pipeline.yml` running
   **`ArmContainerBuildProject`** — not the x86 `ContainerBuildProject`; the Lambda below
   declares `Architectures: [arm64]`, and an x86 image would crash at invoke — with
   `CONTAINER_TARGET=tiny-chatbot` (and `DATE_TAG`), per "Adding a container image build"
   in `pipeline/README.md` and the `BuilderMcpContainer` action as the working example.
2. Add a `BlueprintDeploy` CloudFormation action modelled on `HelloWorldCloudFormation`,
   passing every parameter explicitly — including
   `ContainerImageUri: #{TinyChatbotContainer.CONTAINER_DIGEST}` (deploy by digest, not
   tag) and `DeploymentName`.
3. Change this blueprint's entry in `pipeline/stacks.yml` to `deployed_by: 'pipeline'` —
   `validate_stacks.py` fails a `pipeline` entry with no action and a `manual` entry with
   one, so steps 2 and 3 must land together.

## Testing locally

The handler is stdlib-only, so no image or venv is needed:

```sh
# A canned reply (run from the repo root):
python -c "
import sys; sys.path.insert(0, 'blueprints/tiny-chatbot/src')
import json, app
event = {'requestContext': {'http': {'method': 'POST'}}, 'body': json.dumps({'message': 'hello'})}
print(app.handler(event, None)['body'])
"

# The page itself:
python -c "
import sys; sys.path.insert(0, 'blueprints/tiny-chatbot/src')
import app
open('tiny-chatbot.html', 'w').write(app.handler({}, None)['body'])
"  # then open tiny-chatbot.html in a browser (POSTs will fail locally; replies need the Lambda)
```
