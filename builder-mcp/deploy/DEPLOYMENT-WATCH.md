# DEPLOYMENT-WATCH — builder-mcp first pipeline run (PR #10)

**For:** Jai (console access + merge rights). Tim has no AWS account access yet, so this
run is yours to watch.
**When:** Now. PR #10 merged `builder-mcp` into `main` as commit
`ad289a8b964bf7c164d9420051297775072af516` ("Merge pull request #10 from
cu-aaii/builder-mcp"). The webhook fires within seconds of merge, so pipeline
`aidlc-main` in `us-east-1` is already running.

**One thing to know before you look at anything:** what merged is the repo state at
`daa7d85` — the **Cognito** auth variant of builder-mcp, *without* the later security
remediation. PR #11 (pending) swaps Cognito for Entra ID and carries the security fixes.
So on THIS run, **seeing Cognito resources (a user pool, domain, app client) in the
builder-mcp stack is correct and expected**, and nothing about `/entra/...` SSM
parameters applies yet. Section 10 covers what changes when #11 merges.

All CLI examples assume:

```sh
--profile <profile> --region us-east-1
```

(`<profile>` is whatever your `~/.aws/config` calls this account; the repo docs use
`ai-dlc-workshop`.)

---

## 1. CodePipeline `aidlc-main` — the master view

**Console:** CodePipeline → Pipelines → `aidlc-main`
(`https://us-east-1.console.aws.amazon.com/codesuite/codepipeline/pipelines/aidlc-main/view?region=us-east-1`)

**CLI:**

```sh
aws codepipeline get-pipeline-state --profile <profile> --region us-east-1 \
  --name aidlc-main \
  --query 'stageStates[].[stageName,latestExecution.status]' --output table
```

Stage order after this merge: **Source → PipelineDeploy → Build → BlueprintDeploy**.
Action names you'll see: `GitRepository` (Source), `PipelineCloudFormation`
(PipelineDeploy), `BuilderMcpContainer` (Build), then `HelloWorldCloudFormation` and
`BuilderMcpCloudFormation` in parallel (both `RunOrder: 1`) in BlueprintDeploy.

**The self-update dance — the first run WILL restart once, and that is healthy.**
The pipeline deploys itself before it deploys anything else: `PipelineDeploy` applies
the new `pipeline/pipeline.yml`, which this merge changed substantially (it adds the
ARM CodeBuild project `aidlc-main-container-arm` and the whole `Build` stage). The
pipeline has `RestartExecutionOnUpdate: true`, so the moment that stack update lands,
CodePipeline **abandons the in-flight execution and starts a fresh one from Source**
under the new definition. Timeline you should expect:

1. Execution A starts: Source → PipelineDeploy. At this point the old pipeline
   definition (no Build stage) is running.
2. PipelineDeploy succeeds → pipeline definition updated → Execution A is superseded.
3. Execution B starts from the top: Source → PipelineDeploy (no-op update this time)
   → Build → BlueprintDeploy.

So: **one restart is expected, not a loop.** A second self-update on Execution B is a
no-op (the definition already matches), so it does not restart again. If you see it
restarting over and over, something is genuinely wrong — but with only this merge in
flight, it won't.

**Healthy:** Execution B walks all four stages to `Succeeded`, roughly 10–20 minutes
end to end (the ARM image build dominates).

**Likely failure here:** `Source` fails with a permissions-flavored error. That is the
CodeConnections connection not reading `AVAILABLE` (the handshake gotcha — the error
never mentions the handshake). Check:

```sh
aws codeconnections list-connections --profile <profile> --region us-east-1 \
  --query 'Connections[].[ConnectionName,ConnectionStatus]' --output table
```

If `cu-aaii` is `PENDING`, finish it in CodePipeline → Settings → Connections →
Update pending connection, then **Release change** on the pipeline. (It has worked
before — hello-world deployed through it — so this only bites if something reset.)

---

## 2. CodeBuild `aidlc-main-container-arm` — the arm64 image build

This is the **first-ever run** of this project — it was created by PipelineDeploy
minutes ago. It builds the `builder-mcp` target of the repo-root `Dockerfile` on
aarch64 compute (AgentCore runtimes require linux/arm64 — that is why it is a separate
project from the untouched x86 reference project; see GOTCHA-ARM in
`../aidlc-docs/PROJECT-KNOWLEDGE.md`). Expect **~3–8 minutes**.

**Console:** CodeBuild → Build projects → `aidlc-main-container-arm` → latest build →
Phase details / Build logs. (Logs also land in CloudWatch group
`/aws/codebuild/aidlc-main-container-arm`.)

**CLI:**

```sh
aws codebuild list-builds-for-project --profile <profile> --region us-east-1 \
  --project-name aidlc-main-container-arm --query 'ids[0]' --output text
# then:
aws codebuild batch-get-builds --profile <profile> --region us-east-1 \
  --ids <build-id> \
  --query 'builds[0].[buildStatus,currentPhase]' --output table
```

**Healthy:** phases PRE_BUILD (ECR login) → BUILD (`docker build --target builder-mcp`)
→ POST_BUILD (`docker push`, then exports `CONTAINER_DIGEST`) all green.

**Likely failures:**

- **Dockerfile / build errors** in the BUILD phase — a `uv sync` or `pip` resolution
  failure, or a missing file because `.dockerignore` excluded something. The build log
  shows the failing Docker step directly. Fix is a PR to `main` (Dockerfile or
  `.dockerignore`), which re-runs everything on merge. Note the image built fine
  locally with `docker buildx build --platform linux/arm64 --target builder-mcp .`
  before merge, so this would mean environment drift, not a broken Dockerfile.
- **ECR push denied** in POST_BUILD (`denied: ... not authorized to perform:
  ecr:InitiateLayerUpload` or similar). The build runs as `ContainerBuildRole`
  (`aidlc-main-container-build`), which `pipeline.yml` grants ECR push on `*` — so a
  denial here means an SCP or a manually-edited role. Compare the live role policy
  against `pipeline/pipeline.yml`, fix via PR (or hand-redeploy of the pipeline stack
  only if the pipeline itself can't self-heal).

After a fix that doesn't need a new commit: pipeline page → failed stage → **Retry**.

---

## 3. ECR repo `aidlc-main` — the image lands

**Console:** ECR → Repositories → `aidlc-main`.

**CLI:**

```sh
aws ecr describe-images --profile <profile> --region us-east-1 \
  --repository-name aidlc-main \
  --query 'sort_by(imageDetails,&imagePushedAt)[-1].[imageTags[0],imageDigest,imagePushedAt]' \
  --output table
```

**Healthy:** a new image tagged `builder-mcp-<author-date>` (the commit's author date
with `:` swapped for `-`, e.g. `builder-mcp-2026-08-03T14-22-33Z`). **Write down the
`sha256:` digest** — the BlueprintDeploy stage passes exactly this digest (not the tag)
as `ContainerImageUri`, and matching it against the runtime later proves the runtime is
running this commit's image.

**Likely failure:** repo doesn't exist / no image. The repo is created by the pipeline
stack itself, so no repo means PipelineDeploy never succeeded (go back to step 1); no
image means the Build stage hasn't finished or failed (step 2).

---

## 4. CloudFormation stacks — the deploy itself

**Console:** CloudFormation → Stacks (filter on `aidlc-main`).

**CLI:**

```sh
aws cloudformation describe-stacks --profile <profile> --region us-east-1 \
  --query 'Stacks[?starts_with(StackName,`aidlc-main`)].[StackName,StackStatus]' \
  --output table
```

**Healthy end state:**

| Stack | Expected status | Notes |
|---|---|---|
| `aidlc-main-pipeline` | `UPDATE_COMPLETE` | The self-update from step 1. |
| `aidlc-main-hello-world` | `UPDATE_COMPLETE` (or no new events) | Only its `SourceCommitId` parameter changes, updating the SSM marker. |
| `aidlc-main-builder-mcp` | `CREATE_COMPLETE` | **New.** Contains Cognito user pool + domain + resource server + app client, the runtime IAM role `aidlc-main-builder-mcp-runtime`, and the AgentCore runtime. The Cognito resources are **expected in this deploy** — they go away when PR #11 merges. |

**THE MOST LIKELY FAILURE OF THE WHOLE RUN** is the `BuilderMcpCloudFormation` action
dying with an **AccessDenied** — `cloudformation-deploy-role` predates AgentCore
(GOTCHA-DEPLOY-ROLE). Symptoms: the pipeline action goes red; the stack shows
`CREATE_FAILED` / `ROLLBACK_COMPLETE` with an event like
`User: arn:aws:sts::<account>:assumed-role/cloudformation-deploy-role/... is not
authorized to perform: bedrock-agentcore:CreateAgentRuntime` (or a `cognito-idp:*`
action for the pool resources).

**How to read the Events tab to find the failing resource:** CloudFormation →
`aidlc-main-builder-mcp` → **Events** → sort newest-first and scan for the **first**
`CREATE_FAILED` (everything after it is cascade/rollback noise). The `Logical ID`
column names the resource (`BuilderRuntime`, `BuilderUserPool`, ...) and `Status
reason` carries the actual API error. CLI equivalent:

```sh
aws cloudformation describe-stack-events --profile <profile> --region us-east-1 \
  --stack-name aidlc-main-builder-mcp \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].[LogicalResourceId,ResourceStatusReason]" \
  --output table
```

**The fix lives in `bootstrap/`:** the deploy role is defined in
`bootstrap/account-bootstrap.yml` as `CloudFormationDeployRole`, deployed **by hand**
(it is the one thing the pipeline cannot deploy for itself) as stack
**`aidlc-account-bootstrap`**. Note the template as written attaches
`AdministratorAccess` — so if you get AccessDenied, either the live role has drifted
from the template (someone narrowed it) or an org SCP is blocking
`bedrock-agentcore:*`. Either way: add an explicit allow for
`bedrock-agentcore:*` (and `cognito-idp:*` for this Cognito deploy) to the role in
`bootstrap/account-bootstrap.yml`, then redeploy the bootstrap stack by hand:

```sh
aws cloudformation deploy --profile <profile> --region us-east-1 \
  --stack-name aidlc-account-bootstrap \
  --template-file bootstrap/account-bootstrap.yml \
  --capabilities CAPABILITY_NAMED_IAM
```

(If it's an SCP, the fix is with whoever owns the org policy, not this repo.)

Then on the pipeline page: failed **BlueprintDeploy** stage → **Retry** (retry failed
actions). No new commit needed — the artifact and image digest are still attached to
the execution. If the stack ended in `ROLLBACK_COMPLETE`, delete it first
(`aws cloudformation delete-stack --stack-name aidlc-main-builder-mcp ...`) — a
rolled-back **initial create** cannot be updated, so Retry would fail again until the
husk is gone.

---

## 5. Bedrock AgentCore console — the runtime exists

**Console:** Amazon Bedrock → AgentCore → Runtimes (us-east-1).

**Healthy:** a runtime named **`aidlc_main_builder_mcp`** — **underscores, not
hyphens** (AgentCore runtime names reject hyphens; GOTCHA-RUNTIME-NAME). Don't burn
time searching for `aidlc-main-builder-mcp`; it will never appear under that name.
Status **READY**, protocol MCP, container URI matching the digest you noted in step 3.

**CLI:**

```sh
aws bedrock-agentcore-control list-agent-runtimes --profile <profile> --region us-east-1 \
  --query 'agentRuntimes[?agentRuntimeName==`aidlc_main_builder_mcp`].[agentRuntimeName,status,agentRuntimeArn]' \
  --output table
```

**Likely failure:** stack is green but status is `CREATE_FAILED`/`FAILED` instead of
READY — that usually means the container started and crashed (bad image, wrong
architecture, immediate exception). Go to step 6; the logs say why. An image that
isn't linux/arm64 fails here, but the dedicated ARM build project exists precisely to
prevent that.

---

## 6. CloudWatch Logs — the server actually started

**Console:** CloudWatch → Log groups → filter `/aws/bedrock-agentcore/` → the group
for `aidlc_main_builder_mcp` (AgentCore names it
`/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT` or similar).

**CLI:**

```sh
aws logs describe-log-groups --profile <profile> --region us-east-1 \
  --log-group-name-prefix /aws/bedrock-agentcore \
  --query 'logGroups[].logGroupName' --output table
# then:
aws logs tail <log-group-name> --profile <profile> --region us-east-1 --since 1h
```

**Healthy:** startup lines from the container, ending in uvicorn binding —
`Uvicorn running on http://0.0.0.0:8000` (AgentCore's MCP contract expects the server
listening on port 8000). No tracebacks, no restart churn.

**Likely failure:** a Python traceback at import/startup (missing env var, bad
config), or repeated start/exit cycles meaning the runtime keeps crashing. The
traceback names the module; fix is a code PR. A missing-GitHub-token warning is **not**
a failure — without the secret `aidlc/main/builder-mcp/github-token`, GitHub write
tools intentionally run in dry-run mode.

---

## 7. Inventory check — the tags landed

Everything deployed must carry the four `cornell:*` tags, or it's invisible to the
platform's inventory/cost work. Prove it:

```sh
aws resourcegroupstaggingapi get-resources --profile <profile> --region us-east-1 \
  --tag-filters 'Key=cornell:deployment-id,Values=aidlc-main-builder-mcp' \
  --query 'ResourceTagMappingList[].ResourceARN' --output table
```

**Healthy for THIS (Cognito) deploy:** at minimum the runtime IAM role
(`aidlc-main-builder-mcp-runtime`), the Cognito user pool, and the AgentCore runtime.
(Caveat: the tagging API can lag minutes behind resource creation, and newer services
like AgentCore sometimes index late — if the role and pool show but the runtime
doesn't, re-check in ten minutes before declaring a tagging bug.)

And per `blueprints/hello-world/README.md`, the same check for hello-world should
return its S3 bucket and SSM parameter:

```sh
aws resourcegroupstaggingapi get-resources --profile <profile> --region us-east-1 \
  --tag-filters 'Key=cornell:deployment-id,Values=aidlc-main-hello-world' \
  --query 'ResourceTagMappingList[].ResourceARN' --output table
```

---

## 8. hello-world end-to-end proof — the deployed-commit marker

This is the cheapest proof the entire path works, and it directly answers Tim's
"I couldn't even tell if hello-world worked": a specific commit travelled from a merge,
through CodePipeline, into a deployed resource.

```sh
aws ssm get-parameter --profile <profile> --region us-east-1 \
  --name /aidlc/main/hello-world/deployed-commit \
  --query 'Parameter.Value' --output text
```

**Healthy:** the output equals the merge commit on `main`:

```
ad289a8b964bf7c164d9420051297775072af516
```

(That is `git rev-parse origin/main` right now — PR #10's merge commit. The pipeline
passes `#{GitRepository.CommitId}` into the hello-world stack, so this parameter is
literally "the commit the pipeline last deployed".) If it shows an older sha, the
hello-world action hasn't run yet or failed — check BlueprintDeploy in step 1.

---

## 9. Functional smoke of the MCP runtime

**Under the CURRENT deploy (Cognito, pre-#11):** a bearer token comes from the Cognito
**client-credentials** flow — the stack's `TokenEndpoint` output
(`https://aidlc-main-builder-<account>.auth.us-east-1.amazoncognito.com/oauth2/token`)
with the `ClientId` output and the client secret, scope `cornell-builder/invoke`. You
don't have to do that by hand: the **verify.py on the deployed `main` is the Cognito
version** and does the whole dance — stack outputs → fetch the client secret via
`cognito-idp:DescribeUserPoolClient` → token → MCP handshake → asserts all 8 tools →
live `blueprint_search` call:

```sh
git checkout main && git pull   # be on ad289a8, the Cognito verify.py
cd builder-mcp
uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1
```

(Set `AWS_PROFILE=<profile>` first if that account isn't your default. Being on the
right checkout matters: PR #11's branch carries the **Entra** verify.py, which will
not work against this Cognito deploy.)

**Healthy:** it prints the 8 tool names (`blueprint_search`,
`deployment_create/read/update/restart/health/delete`, `spec_export`) and ends with
`VERIFIED: the Cornell Builder is live on AgentCore`.

**After PR #11 merges, this section changes completely:** the Cognito flow dies with
the pool, and the **Entra pre-flight** (two SSM parameters + the
`aidlc/main/builder-mcp/entra-client-secret` secret, per this directory's
[HANDOFF.md](HANDOFF.md)) is required INSTEAD — the post-#11 verify.py gets its token
from `login.microsoftonline.com`.

---

## 10. After PR #11 merges — what the NEXT run looks like

PR #11 is the Entra ID swap + security remediation. When it merges, the same watch
sequence applies, with these differences:

- **Pre-flight is now mandatory and comes FIRST.** Before merging #11, these must
  exist (see [HANDOFF.md](HANDOFF.md) for the full Azure-side steps):
  ```sh
  aws ssm put-parameter --name /entra/builder-mcp/tenant-id --type String --value '<tenant-id>' --profile <profile> --region us-east-1
  aws ssm put-parameter --name /entra/builder-mcp/client-id --type String --value '<client-id>' --profile <profile> --region us-east-1
  aws secretsmanager create-secret --name aidlc/main/builder-mcp/entra-client-secret --secret-string '<secret>' --profile <profile> --region us-east-1
  ```
  The stack reads the two ids as `AWS::SSM::Parameter::Value<String>` parameters, so if
  they don't exist **the deploy fails immediately at parameter resolution** — before a
  single resource is touched.
- **The deploy role needs `ssm:GetParameters` on `/entra/builder-mcp/*`** to resolve
  those parameters. Same bootstrap-template-plus-hand-redeploy procedure as step 4.
  (`cognito-idp:*` stops being needed at the same moment.)
- **The stack UPDATE deletes the Cognito resources** — user pool, domain, resource
  server, app client all disappear from `aidlc-main-builder-mcp`. Expected; any client
  still holding a Cognito token or the old token endpoint breaks at that instant.
- **The runtime's JWT authorizer flips to Entra** (discovery URL on
  `login.microsoftonline.com`, audience `api://<client-id>`), and smoke-testing follows
  HANDOFF.md's Entra flow instead of section 9's Cognito flow.
- Step 7's inventory expectation loses the Cognito pool.

---

## The 10-minute checklist

Run top to bottom once the pipeline shows all-green (or to find where it isn't):

| # | Check | Where / command | Pass looks like |
|---|---|---|---|
| 1 | Pipeline run | CodePipeline `aidlc-main` | All 4 stages `Succeeded`; exactly one self-update restart |
| 2 | ARM image build | CodeBuild `aidlc-main-container-arm` | Latest build `SUCCEEDED` (~3–8 min) |
| 3 | Image in ECR | `aws ecr describe-images --repository-name aidlc-main ...` | Tag `builder-mcp-<date>`; note the digest |
| 4 | Stacks | CloudFormation, filter `aidlc-main` | `-pipeline` UPDATE_COMPLETE, `-hello-world` UPDATE_COMPLETE, `-builder-mcp` CREATE_COMPLETE (Cognito resources present — expected until #11) |
| 5 | Runtime | Bedrock AgentCore → Runtimes | `aidlc_main_builder_mcp` (underscores) READY |
| 6 | Logs | `aws logs tail /aws/bedrock-agentcore/...` | Uvicorn on :8000, no tracebacks |
| 7 | Tags | `get-resources` on `cornell:deployment-id=aidlc-main-builder-mcp` | Role + user pool + runtime returned |
| 8 | Deploy marker | `aws ssm get-parameter --name /aidlc/main/hello-world/deployed-commit` | `ad289a8b964bf7c164d9420051297775072af516` |
| 9 | MCP smoke | `uv run python deploy/verify.py` (on `main` checkout) | 8 tools + `VERIFIED: the Cornell Builder is live on AgentCore` |

If a step fails: fix per its section above, then pipeline → failed stage → **Retry**.
The one failure worth expecting in advance is step 4's AccessDenied on
`bedrock-agentcore:*` from `cloudformation-deploy-role` — fix in
`bootstrap/account-bootstrap.yml`, redeploy `aidlc-account-bootstrap` by hand, Retry.
