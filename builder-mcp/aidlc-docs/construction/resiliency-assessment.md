# Resiliency Baseline Assessment — builder-mcp

**Date**: 2026-08-03 · **Mode**: opt-in, design-time directional guidance (post-construction
catch-up), **not** production certification. The mob opted in after construction, so this
assesses what exists rather than gating a stage.

**Ruleset**: `aidlc-rules/aws-aidlc-rule-details/extensions/resiliency/baseline/resiliency-baseline.md`
(RESILIENCY-01 … RESILIENCY-15).

**Scope and calibration**: builder-mcp is a stateless MCP server (C4: streamable HTTP,
`BUILDER_MCP_STATELESS=1`) for a university platform MVP serving a two-day workshop and a
small builder population afterward. It is a control-plane convenience, not a data plane: if
it goes down, builders lose the conversational interface, but nothing already deployed is
affected and the PR-and-merge path still works by hand. Recommendations below are sized for
that criticality — roughly "Medium", not Tier-0. Findings are directional, not blocking.

**Evidence base**: `SPEC.md` (C3–C5, C7), `infra/builder-mcp.yml`,
`src/builder_mcp/server.py`, `aws_ops.py`, `github_ops.py`, `catalog.py`,
`aidlc-docs/inception/requirements/versioning-releases-and-recovery-options.md`
(the mob's existing state-class model: stateless / derived / authoritative).

---

## Pillar 1 — Business Goals

### RESILIENCY-01: Critical workload identification — **Partial**

**Posture.** The dependency picture is well documented in practice: SPEC.md C4/C5 name the
runtime (Bedrock AgentCore), inbound auth (Cognito JWT), and both outbound dependencies
(GitHub API server-side token; AWS APIs via the read-mostly runtime role). The recovery
options doc classifies state explicitly. What's missing is a stated criticality tier and
impact-of-unavailability statement.

**Gap.** No document says "builder-mcp is Medium criticality; outage impact = builders fall
back to hand-authored PRs; nothing deployed is affected."

**Recommendation (right-sized).** One paragraph, added to SPEC.md or PROJECT-KNOWLEDGE.md:
criticality tier, blast radius of an outage (none, beyond UX), and the dependency list —
GitHub API (hard for `blueprint_search` off-repo and all writes), CloudFormation /
CodePipeline / Resource Groups Tagging APIs (hard for status/health/restart tools), Cognito
(hard for all inbound calls), Secrets Manager (hard for GitHub writes when deployed). Do not
build a formal BIA.

### RESILIENCY-02: Availability and recovery targets — **Gap (small)**

**Posture.** No SLA/RTO/RPO stated anywhere. The state model implies the answer: the server
is `stateless` class — "redeploy from repo; git is the backup" — so RPO is effectively zero
for everything except the hand-created GitHub-token secret.

**Gap.** The implied targets are undocumented, so nobody has agreed that (say) hours of
downtime is acceptable.

**Recommendation.** Record the answer the architecture already gives: RESILIENCY-02 option
**A/E hybrid** — single-region, redeploy-from-IaC, RTO "one pipeline run" (~tens of
minutes), RPO 0 for code/config, RPO n/a for state (there is none the server owns). Two or
three sentences in the same paragraph as RESILIENCY-01. Note the one exception: the Secrets
Manager secret `aidlc/main/builder-mcp/github-token` is created by hand
(`infra/builder-mcp.yml` GitHubTokenSecretName description) — its recovery is "re-create by
hand", which needs a line in a runbook (see RESILIENCY-13).

---

## Pillar 2 — Change Management & Automation

### RESILIENCY-03: Change management process — **Compliant**

**Posture.** The platform *is* a change management process: PR-only `main`, one human
approval, branch protection, merge as the only deploy trigger (D4, enforced in code — no
tool in `server.py` merges, pushes to a tracked branch, or touches CloudFormation
Create/Update/Delete; the runtime role in `infra/builder-mcp.yml` grants only
`StartPipelineExecution`/`RetryStageExecution` as writes). Change records are the PR history.

**Gap.** None worth acting on. This is option A ("existing org process") with the process
being the repo's own review gate.

### RESILIENCY-04: Automated deployment and rollback — **Compliant with one documentation gap**

**Posture.** Fully automated: merge → Source → PipelineDeploy → BlueprintDeploy; the image
is built by the pipeline's ARM CodeBuild and pinned **by digest**
(`#{BuilderMcpContainer.CONTAINER_DIGEST}`, C4), which is exactly the version-pinned
artifact a rollback needs. IaC is CloudFormation; deployment style is direct/in-place —
appropriate for this criticality.

**Gap.** The rollback mechanism is implicitly "revert the PR and merge" (option A,
version-pinned redeploy) but no doc states it, and nobody has done it once to confirm the
digest-pinned redeploy behaves.

**Recommendation.** Document "rollback = git revert + merge; the pipeline redeploys the
previous digest" in deploy/HANDOFF.md, and exercise it once when convenient. No blue/green,
no canary — over-engineering at this tier.

---

## Pillar 3 — Integrated Observability

This pillar is where the real gaps are.

### RESILIENCY-05: Monitoring and alerting — **Gap**

**Posture.** The runtime role grants CloudWatch Logs permissions
(`/aws/bedrock-agentcore/*` in `infra/builder-mcp.yml`), so logs flow. But: no metrics
beyond AgentCore defaults, no structured logging in the application (no `logging` calls
anywhere in `src/builder_mcp/`), no dashboard, no alarm resources in the template. Tracing
is N/A (single service). The platform's `observability/` track is deliberately not built
yet (repo-level decision) — but that makes builder-mcp itself unwatched.

**Gap.** If the runtime starts failing after a merge, nobody is told; discovery is a builder
reporting "the Builder isn't answering."

**Recommendation (the important one).** Two small additions to `infra/builder-mcp.yml`:
(1) a CloudWatch log metric filter on the AgentCore log group matching error-shaped lines,
plus (2) one CloudWatch alarm on that metric (and/or on AgentCore invocation-error metrics
if the service emits them) notifying an SNS topic the platform team watches. Add minimal
structured logging (one log line per tool call: tool name, outcome, duration) — the `_friendly`
error path in `aws_ops.py` currently swallows errors into the response with no server-side
record at all. Skip dashboards until the Track E observability work lands.

### RESILIENCY-06: Health checks — **Gap**

**Posture.** No health endpoint beyond the MCP protocol itself; no synthetic monitoring.
AgentCore fronts the container, so there is no load balancer to integrate with — the
platform manages liveness restarts internally, which covers the "process is running" case.

**Gap.** Nothing verifies the *deployed* runtime end-to-end (auth → runtime → tool
execution). A bad image that starts but can't serve tools, or a broken Cognito config,
is invisible until a human tries it. Note the irony: builder-mcp offers a `health_check`
tool for the deployments it manages, but has no health check of its own.

**Recommendation.** A synthetic canary at platform scale: a scheduled GitHub Actions
workflow (org policy allows github-owned actions) or EventBridge-scheduled Lambda that
fetches a Cognito client-credentials token and calls one read-only tool
(`blueprint_search`) against the deployed endpoint, failing loudly on error. This one
check covers Cognito, the runtime, the image, and the GitHub catalog path in a single
probe. `deploy/verify.py` reportedly derives the endpoint already — reuse it.

### RESILIENCY-07: Resiliency monitoring — **Gap, mostly N/A**

**Posture.** No resiliency-specific alarms; no capacity monitoring. No auto-scaling
configuration to watch (AgentCore manages capacity).

**Gap / recommendation.** At this tier, RESILIENCY-05/06 above *are* the resiliency
monitoring. One addition worth a line: GitHub API rate limits are the realistic capacity
ceiling (a PAT's 5,000 req/hr is shared across every builder's session, and
`_load_remote` in `catalog.py` makes 1+N GitHub calls per off-repo `blueprint_search`).
Log the `X-RateLimit-Remaining` header in `github_ops.py` and let the RESILIENCY-05 metric
filter catch depletion. Defer formal resiliency-assessment tooling; mark as future.

---

## Pillar 4 — High Availability

### RESILIENCY-08: Multi-zone / multi-region — **Accepted constraint**

**Posture.** Single-region `us-east-1` is a hard platform constraint (CLAUDE.md), not a
choice this component gets to make. AgentCore is serverless and multi-AZ by default, which
satisfies the multi-zone baseline without any configuration. Cognito is regional and
multi-AZ. No data stores exist.

**Gap.** None actionable. **Record as accepted**: single-region topology, RESILIENCY-08
option A, consistent with the RESILIENCY-02 targets above. A region-wide us-east-1 outage
takes down the whole platform, not just builder-mcp; that risk is owned at platform level.

### RESILIENCY-09: Auto-scaling and capacity — **Mostly N/A, one quota note**

**Posture.** Serverless; AgentCore scales the runtime. No concurrency limits configured —
also no knob for one in the current `AWS::BedrockAgentCore::Runtime` properties used.

**Gap / recommendation.** Document the two quotas that could bite: AgentCore runtime
concurrent-session/invocation quotas (workshop = burst of ~30 builders at once — worth a
pre-workshop check against account quotas) and the GitHub API rate limit noted under
RESILIENCY-07. No action beyond documenting and the rate-limit logging.

### RESILIENCY-10: Dependency isolation and circuit breaking — **Partial, with two code-level findings**

**Posture — the good.** Explicit timeouts exist on both httpx clients: `timeout=30` in
`github_ops.py`, `timeout=15` in `catalog.py::_load_remote`. Graceful degradation is a
designed feature, not an afterthought: no GitHub token ⇒ writes return dry-run plans
(`GitHubOps.can_write`, C5); every function in `aws_ops.py` degrades to an `{"error": ...}`
narrative instead of raising (NFR7); `deployment_status` explicitly catches GitHub failure
so it "should not hide AWS state" (`server.py` line 178).

**Posture — the gaps.**

1. **The C3 error contract ("tools return `{"error": ...}`, never raise to the transport")
   is not uniformly implemented.** `blueprint_search` calls `load_catalog` with no
   try/except; off-repo (the deployed case, `repo_root is None`), `_load_remote` calls
   `listing.raise_for_status()` — a GitHub outage or rate-limit 403 raises straight through
   the tool. GitHub is thus an **unmonitored hard dependency of `blueprint_search` when
   deployed**, and the failure mode violates the documented contract. Same pattern in the
   non-dry-run bodies of `create_deployment` and `propose_change`: `GitHubOps` methods
   `raise_for_status()` and nothing in the tool bodies catches.
2. **No compensation for partial failure.** `create_deployment` (non-dry-run) is a
   five-step write sequence (create repo → put shell files → create branch → patch
   pipeline.yml → open PR). A failure mid-sequence leaves an orphan repo or branch with no
   narrative telling the builder what exists and what to do. Related: `propose_change`
   derives its branch name from `abs(hash(title))`, which is process-seeded
   (PYTHONHASHSEED) — a retry after a container restart lands on a *different* branch, so
   retries aren't idempotent.
3. **boto3 clients use default config** — no explicit connect/read timeouts, legacy retry
   mode. Defaults are generous (60s), acceptable but undocumented.

**Recommendation.** (a) Wrap every tool body (or add a decorator) so exceptions become the
contractual `{"error": ...}` narrative — this is the single highest-value code change, small
and mechanical. (b) In `create_deployment`, catch mid-sequence failure and return a
narrative listing what was created and the manual next step. (c) Give boto3 clients an
explicit `botocore.config.Config(connect_timeout=10, read_timeout=30,
retries={"mode": "standard", "max_attempts": 3})` and note the policy in SPEC.md C7 or the
README. Circuit breakers and bulkheads: **not applicable at this tier** — httpx-per-call
plus timeouts is proportionate.

---

## Pillar 5 — Disaster Recovery

### RESILIENCY-11: DR strategy — **Compliant in substance, undocumented in form**

**Posture.** The mob already did the thinking: the recovery-options doc's three-class model
puts builder-mcp squarely in `stateless` — "Redeploy from repo (merge or
restart_deployment). Free — git is the backup." That *is* the Backup & Restore strategy,
and it is the right one.

**Gap.** It's stated as a general platform policy, not applied to builder-mcp by name, and
the two exceptions aren't listed.

**Recommendation.** Don't duplicate the recovery-options doc — reference it. Add to it (or
to HANDOFF.md) the builder-mcp-specific footnote: the two things *not* recovered by
redeploy are (1) the hand-created GitHub token secret (re-create per its runbook line), and
(2) the Cognito app client id/secret, which change on stack re-create — every builder's
configured client credential must be reissued. That second one is the only genuinely
surprising recovery consequence in this component.

### RESILIENCY-12: Data backup and replication — **N/A**

No persistent state owned by builder-mcp. Catalog and code live in git; deployment repos
live in GitHub; the secret is hand-managed. Mark N/A with that one-line justification.
(The `state:` manifest contract this component *enforces* for other blueprints is the
platform's answer to this rule — a strength worth noting, not a gap.)

### RESILIENCY-13: Failover and recovery procedures — **Gap (small)**

**Posture.** deploy/HANDOFF.md covers forward deployment. No recovery runbook.

**Gap.** "Redeploy from IaC" has never been written down as steps, and the secret + Cognito
client-credential consequences (RESILIENCY-11) live only in people's heads.

**Recommendation.** A ten-line "recovery" section in deploy/HANDOFF.md: re-run pipeline (or
`restart_deployment`); if the stack is gone, merge redeploys it; re-create the secret; note
that clients need new Cognito credentials after a pool re-create. Communication plan =
workshop Slack/Teams channel, one line. Nothing more.

---

## Pillar 6 — Continuous Improvement

### RESILIENCY-14: Chaos engineering and DR testing — **Deferred (option C), acceptable**

**Posture.** None. The recovery-options doc already proposes the right platform-level
practice ("a backup nobody has restored is a hypothesis" — restore drills as a P1 maturity
gate for blueprints).

**Recommendation.** Record option C: defer to operations, with two named test scenarios
captured now — (1) delete the `aidlc-main-builder-mcp` stack in a test environment and
redeploy from IaC end-to-end (validates RESILIENCY-11/13 including the Cognito credential
consequence); (2) run the tool surface with GitHub unreachable and confirm every tool
returns a narrative, not a hang or a transport error (validates RESILIENCY-10 fix). No
chaos tooling.

### RESILIENCY-15: Incident response — **Gap (small)**

**Posture.** No defined process; no alerting exists to route anywhere (see RESILIENCY-05).
During the workshop the de facto process is "the platform team is in the room."

**Recommendation.** Option B, lightweight: the RESILIENCY-05 alarm notifies an SNS topic
subscribed by the platform team; incidents and their corrections go where the platform
already writes things down (`aidlc-docs/audit.md` or BACKLOG.md). Do not adopt paging
tooling for an MVP.

---

## Compliance summary

| Rule | Posture | Blocking? (advisory mode) |
|---|---|---|
| R-01 Workload identification | Partial — dependencies documented, criticality tier not stated | No — one paragraph fixes it |
| R-02 Availability/recovery targets | Gap — implied by architecture, undocumented | No |
| R-03 Change management | **Compliant** (PR gate is the process) | — |
| R-04 Deployment & rollback | Compliant; rollback undocumented/untested | No |
| R-05 Monitoring & alerting | **Gap** — logs only, no metrics/alarms/structured logging | Top priority |
| R-06 Health checks | **Gap** — no end-to-end probe of deployed runtime | Top priority |
| R-07 Resiliency monitoring | Gap, mostly N/A — GitHub rate limit is the one real ceiling | No |
| R-08 Multi-zone/region | **Accepted** — single-region us-east-1 platform constraint; AgentCore multi-AZ | — |
| R-09 Auto-scaling/capacity | Mostly N/A — document AgentCore + GitHub quotas | No |
| R-10 Dependency isolation | Partial — timeouts + degradation good; error contract leaks, no retry policy | Priority |
| R-11 DR strategy | Compliant in substance (stateless class); apply by name | No |
| R-12 Backup/replication | **N/A** — no owned persistent state | — |
| R-13 Recovery procedures | Gap — no recovery runbook | No |
| R-14 DR testing | Deferred (option C) with scenarios captured | No |
| R-15 Incident response | Gap — propose lightweight (SNS → platform team) | No |

---

## Prioritized shortlist — before P1

1. **Make the error contract true everywhere (R-10).** Wrap all seven tool bodies so every
   exception — especially `blueprint_search`'s uncaught off-repo GitHub path and the
   non-dry-run GitHub write sequences — returns the contractual `{"error": ...}` narrative;
   give `create_deployment` a partial-failure narrative listing what was created.
   **Effort: S.** Highest value per line changed; it converts the worst failure mode
   (transport exception, GitHub as silent hard dependency) into the designed one.

2. **One alarm and structured logs (R-05, R-15).** Log metric filter on the AgentCore log
   group + one CloudWatch alarm → SNS topic the platform team subscribes to; add one
   structured log line per tool call (tool, outcome, duration, GitHub rate-limit
   remaining). **Effort: M** (template resources + light code).

3. **Synthetic canary against the deployed endpoint (R-06).** Scheduled probe
   (github-owned Action or EventBridge + Lambda): Cognito token → `blueprint_search` →
   assert success. One probe exercises auth, runtime, image, and the GitHub catalog path.
   **Effort: M.**

4. **Explicit outbound-call policy (R-10).** boto3 `Config` with standard retry mode and
   explicit timeouts; document the timeout/retry policy for both boto3 and httpx in
   SPEC.md/README so it survives the P1 GitHub App migration. **Effort: S.**

5. **Recovery runbook + targets paragraph (R-02, R-11, R-13).** Criticality tier, RTO/RPO
   ("one pipeline run" / zero), redeploy-from-IaC steps, secret re-creation, and the
   Cognito client-credential reissue consequence of a stack re-create. **Effort: S.**

Items 1 and 4 are code/PR-sized today; 2 and 3 are natural first tickets of the P1
observability work; 5 is documentation the P1 Entra ID and GitHub App migrations will
want anyway.
