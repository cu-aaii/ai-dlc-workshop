# Infrastructure Design — the front door unit

**Generated**: 2026-08-04
**Stage**: CONSTRUCTION — Infrastructure Design (per-unit)
**Unit**: front door — the delivered subset of U1 + U2 + U3 + U5 + retrieval
**Depth**: standard

> **This stage runs retrospectively.** The infrastructure it designs was already built and committed
> (`5726794`, `9c77a60`, `0806656`). Its job is therefore to **ratify or overturn** decisions already
> made, and to record the two that were made without one — packaging, and the knowledge base handoff.
> Where it overturns something, that is stated as a change to be made, not as a description of what is.

---

## 1. Service mapping

| Need | Service | Why this one |
| --- | --- | --- |
| Public HTTPS ingress | **Lambda Function URL** | Free AWS-provided address, no DNS and no ACM certificate — the account has neither a Route 53 zone nor a certificate. The cost is no built-in throttling and no access log, which is where SECURITY-11 and SECURITY-02 needed compensating controls |
| Compute | **Lambda, container image, arm64** | Serverless-first, and the repo's rule is that Lambda means container images |
| Inbound trust | in-process, `botframework.py` | Nothing else in the stack can do it — see §3 on why AgentCore's authorizer cannot |
| Model access | **Cornell LiteLLM gateway** over public egress | Hard constraint (FR-23). No Bedrock inference |
| Retrieval | **Bedrock `Retrieve`** against Track B's managed knowledge base | `Retrieve` makes no FM call, so generation stays on the gateway |
| Secrets | **Secrets Manager**, 2 secrets | Repo rule: secrets live only here |
| Config | **SSM Parameter Store**, 2 parameters | The only surface a builder-supplied value can reach, given `deployment_create` drops `inputs` |
| Logs | **CloudWatch Logs**, 90-day retention | SECURITY-14 |
| Alerting | **Metric filter + alarm** | A rejected token is not an invocation error, so Lambda's own metrics stay flat |

**Nine resource types, one stack.** No VPC, no NAT, no load balancer, no queue, no table.

---

## 2. The packaging decision — ratified, with the reasoning it should have had

**This is the decision this stage exists to make**, and it was instead settled by a character count on
demo day. Recorded properly now.

**Decision: container image, one `Dockerfile` at the blueprint root, target `course-chatbot`, arm64,
built by `ArmContainerBuildProject`, deployed by digest.**

| Option | Verdict |
| --- | --- |
| **Container image** ✅ | The repo's convention with three worked examples. Readable, extensible, testable. Costs a Docker build in the pipeline — which already exists and is exercised |
| **Inline `Code.ZipFile`** ❌ | **Measured, not estimated: 4114 characters against CloudFormation's hard 4096 cap.** Getting under it required removing comments *and* RS256 signature verification, because `cryptography` is absent from the Lambda runtime and there is no stdlib RSA verify. That trades a reproducibility gap for an **authentication** gap |
| **Zip in S3** ❌ | Avoids both caps and needs no Docker. Rejected on *repo* grounds, not AWS ones: it needs build-and-upload machinery that does not exist here, replacing machinery that does. The right end state, the wrong afternoon |
| **AgentCore `CodeConfiguration`** — later | Research established `AgentRuntimeArtifact` accepts a zip, so the AgentCore step needs no second container. Relevant to the next unit, not this one |

**Why the inline option was tempting and still wrong**: it was requested as *less prescriptive*. It is
the opposite. A dense uncommented handler golfed into a template string hardcodes one implementation
and cannot be regenerated from the design — which contradicts FR-1, "the blueprint is a template, not a
bot".

**One SECURITY-10 criterion is unmet by this decision and carries a dated exception** — the base image
sits on a mutable tag. See `docs/decisions/0001-course-chatbot-base-image-unpinned-for-demo.md`.

---

## 3. Ingress topology, and the constraint that fixes it

```
Teams client
  └─> Azure Bot Service          (Microsoft, dev tenant registration)
        └─> Lambda Function URL  AuthType: NONE, public
              └─> handler        validates the Bot Framework JWT, incl. serviceurl
                    ├─> Bedrock Retrieve   (in-account, SigV4)
                    ├─> LiteLLM gateway    (public egress, HTTPS)
                    └─> Bot Framework API  (public egress, bearer token)
```

**Text alternative.** A Teams client sends a message. Azure Bot Service receives it and POSTs a Bot
Framework activity to the Lambda Function URL, which is public and performs no authentication of its
own. The handler validates the request's JWT — signature, issuer, audience, expiry, and the `serviceurl`
correlation — and rejects anything that fails. For a valid message it makes three outbound calls: a
`Retrieve` against the knowledge base in the same account using SigV4, a completion request to
Cornell's LiteLLM gateway over public HTTPS, and a reply POST back to the Bot Framework API using a
bearer token. All three replies flow back through the same Lambda invocation.

**`AuthType: NONE` is forced, not chosen.** Azure Bot Service cannot sign SigV4 and its source
addresses are not fixed, so there is no IAM caller to authorise. This is SECURITY-07's own
public-facing-443 exception, and authorisation moves to the application layer.

**Why the Lambda cannot be removed from the path**, which is the load-bearing constraint of the whole
design: AgentCore Runtime *could* be exposed directly, but its `CUSTOM_JWT` authorizer validates a
token against an issuer and audience and stops there. **It cannot compare the `serviceurl` claim to the
request body**, and that comparison is the control preventing an attacker with a valid Bot Framework
token from redirecting replies to a server they own. So the front door stays, and AgentCore is reached
by SigV4 from inside the account (FR-21).

---

## 4. IAM — least privilege, and where it came from

Four policies on one role, **no wildcard action and no wildcard resource anywhere**:

| Policy | Grant | Scoped to |
| --- | --- | --- |
| `logs` | `CreateLogStream`, `PutLogEvents` | This function's log group. **`Delete*` deliberately absent** so it cannot destroy its own audit trail |
| `secrets` | `GetSecretValue` | The two secret ARNs, by `!Ref` |
| `config` | `GetParameter` | This deployment's SSM prefix |
| `knowledge-base` | `bedrock:Retrieve` | **One** knowledge base ARN |

**The last row is why the knowledge base id resolves at deploy time.** Reading it at runtime would
leave the role needing `knowledge-base/*` — a wildcard resource SECURITY-06 forbids. Resolving it via
`AWS::SSM::Parameter::Value<String>` makes the exact ARN available to the template.

**Ratified with its cost stated**: that creates a **hard cross-blueprint deploy dependency**. This
stack cannot deploy where `knowledgebase` has not, which is why its action runs at `RunOrder: 2`. A
missing parameter fails the deploy with a resolution error — the right failure, since the alternative is
a chatbot about a real Cornell course with nothing behind it.

The prompt-bucket grant is a **conditional** `AWS::IAM::RolePolicy` rather than an always-present
statement, so there is no wildcard resource when no bucket is configured.

---

## 5. Deployment mechanics

| | |
| --- | --- |
| Stack name | `aidlc-main-course-chatbot` — `<app>-<env>-<name>`, or `BuildPipelineRole` refuses it |
| Build action | `CourseChatbotContainer` → `ArmContainerBuildProject`, exports `CONTAINER_DIGEST` |
| Deploy action | `CourseChatbotCloudFormation`, **`RunOrder: 2`**, 18 parameters passed explicitly |
| Image reference | Digest, never a tag (FR-28) |
| Tags | All four `cornell:*` on every taggable resource; SSM takes the map form |
| Registry | `pipeline/stacks.yml` as `deployed_by: pipeline`, plus the `MANIFEST_EXEMPT` removal |

**Two operational facts that are not in the template and will bite whoever deploys it first:**

1. **The first merge will not deploy this stack.** A CodePipeline execution uses the structure in place
   when it *started*, so the merge adding a Build action updates the pipeline and reports every stage
   green without running the new one. Start a second execution.
2. **Both secrets are created empty.** `GenerateSecretString` puts a random 32-character placeholder in
   each; the bot authenticates with that and gets `401` until someone injects the real values. Green
   deploy, silent failure.

---

## 6. What this stage would change if time allowed

Recorded as design output rather than as a wish list — these are consequences of decisions above.

| # | Change | Why |
| --- | --- | --- |
| 1 | **Restore the worker Lambda and async invoke** | Closes FR-9 (VIOLATED), FR-11, FR-16 and FR-17 in one change. Highest-value work remaining, ahead of AgentCore: AgentCore adds capability, this fixes correctness |
| 2 | Pin the base image by digest | Closes the exception in §2 |
| 3 | Wire `AlarmTopicArn` to the `notify-topic` blueprint | The alarm currently notifies nobody |
| 4 | Dependency vulnerability scanning in CI | `pip-audit` is documented in `requirements.lock` but not run anywhere |
| 5 | Reconsider `ReservedConcurrency: 10` | Chosen as a round number, not from a load model. Workshop scale is tens of users, so 10 concurrent is plausibly right and definitely unmeasured |

**Item 1 is the one to argue about.** Everything else on this list is a small addition; that one is a
structural change that the synchronous design deliberately deferred, and it is the difference between a
demo and a blueprint someone else can safely instantiate.
