# Code Quality Assessment

A note on calibration before the findings: this repository is 16 tracked non-vendored files
with no runtime application code. Judging it against the standards of a production service
would produce a long and useless list of "missing" things. The assessment below asks instead
whether it is well built **for what it is** — a governed deploy path plus one reference
blueprint, built to be extended during a workshop by people who have not seen it before. By
that standard it is in good shape, with a small number of gaps that become real as soon as
runtime code arrives.

## Test Coverage

- **Overall**: **None**, in the conventional sense. There is no test framework, no test runner,
  no test directory, and no coverage tooling.
- **Unit Tests**: None. `pipeline/validate_stacks.py` is the only executable logic in the
  repository and has no tests of its own — including for `check_pipeline_actions()`, the
  function whose entire purpose is catching a silent-failure mode.
- **Integration Tests**: None. Nothing verifies that a deployed stack behaves as intended.
- **Static validation, which does exist and is the real gate**: `cfn-lint` across every
  template, plus three-way reconciliation of registry, filesystem and pipeline definition in
  both directions.

**Fair reading**: for a repository whose only logic is a 217-line validator, "no unit tests" is
defensible. What is genuinely worth noting is that the validator is the thing standing between a
reviewer and an undiagnosable deployment failure, and it is itself unverified. That asymmetry
gets worse, not better, as more blueprints are registered.

## Code Quality Indicators

- **Linting**: **Partial.** `cfn-lint` covers CloudFormation thoroughly. Nothing lints anything
  else — no ruff, black, flake8 or mypy for Python; no shellcheck for `tools/check`; no
  yamllint for the GitHub Actions workflow; no pre-commit configuration. For one Python file
  and one shell script this is proportionate today.
- **Code Style**: **Consistent.** The CloudFormation templates share a single convention:
  single-quoted strings, quoted logical resource references, the same parameter ordering, the
  same tag block shape. `validate_stacks.py` is idiomatic modern Python with type hints and
  small single-purpose functions. Someone reading a second template after the first encounters
  no surprises, which is the property that matters most for a repository designed to be
  extended by newcomers.
- **Documentation**: **Good, and unusually so.** Four READMEs (root, `bootstrap/`, `pipeline/`,
  `blueprints/`) plus `CLAUDE.md`. The documentation's distinguishing quality is that it
  records **failure modes and their symptoms**, not just procedures — the `cfn-lint --region`
  silent pass, the `AWS::SSM::Parameter` tags-as-map asymmetry, the CodeConnections handshake
  that fails as an unrelated permissions error, the org allowed-actions policy that fails as
  `startup_failure` with no logs, the stack-naming violation that fails as an opaque
  authorization error. Each of these is a trap that costs hours to diagnose and minutes to
  avoid once written down. `pipeline/README.md` gives the three-step blueprint recipe;
  `CLAUDE.md` separates hard constraints from conventions and says which are load-bearing and
  why. Inline comments are sparse and placed exactly where a reader would otherwise assume
  wrongly — the tags-as-map comment in `hello-world.yml` being the clearest example.

## Technical Debt

Ordered by when it will start costing something.

1. **No HTTPS ingress and no deployed compute** — `pipeline/`, `blueprints/`.
   Every stack to date is storage, IAM or pipeline plumbing. The Teams chatbot needs a public
   HTTPS messaging endpoint and the request-handling compute behind it, so both would be firsts.
   This is the largest gap between the repository's current state and the work in front of it.

2. **The container build path is defined but never exercised** —
   `pipeline/pipeline.yml`, `pipeline/codebuild.yml`.
   `ContainerBuildProject`, `ContainerRepository`, `ContainerBuildRole` and the buildspec are
   all known-good in the sense of being lint-clean and adapted from a working reference, but no
   stage invokes them, so the `CONTAINER_TARGET`/`DATE_TAG` in, `CONTAINER_DIGEST` out contract
   has never actually run. Since Lambda here means container images, the first blueprint needing
   compute pays the cost of discovering whatever is wrong with it.

3. **Tag enforcement is convention, not validation** — all templates.
   All four `cornell:*` tags are mandatory and feed inventory and the cost dashboard, so an
   untagged resource is invisible to the observability work. Nothing checks for them. The
   validator reconciles registry, filesystem and pipeline, but no check would catch a new
   blueprint that forgot `cornell:owner`. Given that the tags exist precisely to make resources
   visible, a missing tag is silent by construction — the same class of failure the
   registry validator was written to eliminate, left unaddressed one layer over.

4. **Nothing is version-pinned** — `tools/check`, `validate_stacks.py` inline metadata.
   `cfn-lint` and `pyyaml` resolve to whatever is current. A new `cfn-lint` release adding a
   rule can turn a previously green `main` red with no repository change — and `main` is what
   deploys to the shared account. Tolerable at two packages; materially different once runtime
   dependencies exist.

5. **The validator's detection rules have blind spots** — `pipeline/validate_stacks.py`.
   Filesystem discovery matches files containing the literal `AWSTemplateFormatVersion`, so a
   template omitting that key is invisible and escapes registration. Pipeline scanning is a
   regex over `GitRepositoryArtifact::(...)`, so a `TemplatePath` assembled with `!Sub` would
   not be seen. Both are reasonable simplifications given current usage; both are worth knowing
   before relying on the check as complete.

6. **The pipeline self-deployment cycle has no documented recovery path** —
   `pipeline/pipeline.yml`.
   A merge that breaks the pipeline template can leave the pipeline unable to deploy the fix,
   requiring an out-of-band manual deployment. This is the structural reason the pipeline's
   mechanics are treated as frozen, and it is understood by whoever wrote that instruction — but
   the recovery procedure itself is not written down anywhere.

7. **`cloudformation-deploy-role` holds `AdministratorAccess`** —
   `bootstrap/account-bootstrap.yml`.
   Deliberate and reasonable for a workshop account where arbitrary blueprints must be
   deployable. `BuildPipelineRole` narrows what the *pipeline* can target, but the role it
   assumes is unbounded. Worth an explicit decision rather than an implicit one before anything
   long-lived is deployed.

8. **No secret has ever been consumed** — repository-wide.
   The policy is Secrets Manager only, and it is stated clearly, but no stack reads a secret. A
   Teams bot needs its client secret at runtime, and there is no worked example to copy — so
   the first implementation sets the pattern for everything after it.

9. **Live credentials in the working tree** — `docs/teams-chatbot-docs/Research into in-tenant
   setup.md`, `.mcp.json`.
   A real Entra client secret, a test-user password, an n8n bearer token, and a GitHub personal
   access token, in a public repository with secret scanning disabled by enforced org policy.
   Both paths are untracked but **neither is gitignored**, so a `git add .` commits them.
   Reported to the user at the start of this workflow; remediation is rotate, then gitignore
   `.mcp.json` and scrub the research document.

## Patterns and Anti-patterns

### Good Patterns

- **Self-deploying pipeline** (`pipeline/pipeline.yml`, `PipelineDeploy` before
  `BlueprintDeploy`) — a pipeline change ships through the pipeline it changes, so no privileged
  side channel exists and the committed definition cannot drift from the running one.

- **Branch-as-environment** — `Environment` is simultaneously the tracked branch name, part of
  every stack name, and part of the IAM prefix the deploy role is scoped to. One template, one
  parameter, a whole parallel environment. The tight `[a-z0-9]{1,4}` constraint is documented as
  a consequence of the IAM interpolation rather than left as an unexplained limit.

- **Three-way registry reconciliation, in both directions** (`validate_stacks.py`) — the
  standout piece of engineering judgement here. It targets a specific, nasty failure mode: a
  blueprint registered without a pipeline action produces a green pull request, every stage
  `Succeeded`, and no stack. That is close to undiagnosable from the console. The fix converts
  it into a review-time error while deliberately keeping the `stacks.yml` ↔ `pipeline.yml`
  mirroring hand-written, so the human still sees both halves.

- **Explicit parameter passing** — the pipeline passes every parameter; template defaults exist
  only so a stack can be hand-deployed for debugging. This makes hand-deployment a faithful
  reproduction rather than an approximation, which is what makes debugging trustworthy.

- **Identical local and CI gate** — `tools/check` is what CI runs. `uv` is the only
  prerequisite, so a clean machine needs no setup and a green check means the same thing
  everywhere.

- **Loose coupling by name, not export** — the pipeline references
  `cloudformation-deploy-role` by constructed name rather than importing a CloudFormation
  export, so bootstrap can be redeployed or replaced without a cross-stack lock.

- **Blueprints as leaves** — no blueprint imports from another or reads an export, so each is
  independently deployable and independently reasoned about.

- **Documentation that records symptoms** — the most valuable single quality here. Each
  documented gotcha names what you will actually see when you hit it, which is what makes it
  findable in the moment.

- **Vendored-content discipline** — `aidlc-rules/` is byte-identical to upstream, with the
  reason stated (the re-sync is a delete-and-replace that would silently discard edits) and the
  prohibition extended even to fixing typos. Provenance and re-sync instructions live in
  `README.md`.

### Anti-patterns

- **Unvalidated validator** (`pipeline/validate_stacks.py`) — the one piece of logic
  guarding against a silent-failure mode is itself untested.

- **Convention-only tag enforcement** (all templates) — mandatory tags with no automated
  check, where the consequence of omission is invisibility. Structurally the same silent
  failure the registry validator exists to prevent.

- **Unpinned build dependencies** (`tools/check`, inline metadata) — upstream releases can
  turn `main` red without a repository change.

- **Latent, unexercised infrastructure** (`ContainerBuildProject`, `ContainerRepository`,
  `codebuild.yml`) — reasonable as deliberate staging, and documented as such, but code that
  has never run should be assumed broken until it does.

- **Regex-parsed CloudFormation** (`pipeline_deployed_templates()`) — pragmatic and adequate
  for literal paths, brittle against any dynamic construction. Worth knowing rather than worth
  fixing now.

## Readiness For The Teams Chatbot Work

Not a template section; recorded because it is the actionable output of this assessment.

**What the repository gives the work for free**: a governed, reviewed deploy path that
demonstrably reaches AWS; a clear blueprint recipe; a working reference template to copy;
consistent conventions; and unusually good documentation of the traps.

**What the work must build from nothing** — each of these is a first for this repository:

| Gap | Consequence |
| --- | --- |
| Public HTTPS ingress | The bot cannot receive Bot Framework activities without one. Largest gap. |
| Deployed compute | No Lambda, container or service has ever run here. |
| Live container build path | Lambda means container images; the dormant path must be activated and debugged. |
| A stack that reads a secret | The bot needs its client secret; the first implementation sets the pattern. |
| Any non-AWS provisioning | Entra app registration, Azure Bot Service resource and Teams manifest all sit outside AWS. Terraform-from-CodeBuild is the designated mechanism and is explicitly not built. |
| A runtime dependency policy | Inbound JWT validation needs a library. Unpinned resolution is a different proposition for runtime code than for a linter. |
| Tag validation | More blueprints raise the odds of a silently untagged, and therefore invisible, resource. |

**One architectural question this assessment cannot answer**, flagged for Requirements Analysis
rather than assumed: the research prototype runs on self-hosted n8n with credentials in n8n's
own store, which conflicts with the hard constraints on AWS-native IaC, serverless compute and
Secrets Manager. Whether the target is AWS-native, an n8n bridge, or a staged migration is a
requirements decision.
