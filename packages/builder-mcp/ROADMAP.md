# builder-mcp — Roadmap

Ordered next actions to finish the feature. Complements [BACKLOG.md](BACKLOG.md): the backlog is
*what the mob agreed to build*, this is *what to do next and in what order*, with the no-AWS
constraint applied. Contract references are to [SPEC.md](SPEC.md).

## Where we are

Verified by running `tools/check` on `trust-me-bruh` (2026-08-03):

- 41 tests pass, cfn-lint clean, 4 templates registered and present
- 8 tools registered (C3), all `dry_run` paths run with no credentials
- The chatbot loads its catalog, ranks it, and can plan a deployment PR

So the code isn't broken. What's missing is a catalog with more than one thing in it, and tests
at the two edges where it talks to the outside world.

## The constraint

No AWS access on this branch. That rules out four things, and only four:

| Can't do | Why |
|---|---|
| Deploy the AgentCore runtime | needs the account and the pipeline |
| `deploy/verify.py` against a live endpoint | needs a running runtime |
| End-to-end reliability test (BACKLOG) | needs a real merge → pipeline → stack |
| Speed measurement (BACKLOG) | needs the above to time |

Everything else below is local work. The two AWS-facing modules (`aws_ops.py`, `github_ops.py`)
are testable without an account — you stub the client, not the service.

---

## P0 — Unblock the branch

Do this first. Every task after it touches a file that `main` has changed.

### 0.1 Rebase `trust-me-bruh` onto `main`

This branch is 1 ahead / 4 behind. Merged as-is it deletes Track B's and Track C's pipeline
wiring: our `pipeline/pipeline.yml` has 3 `TemplatePath` entries and no `Terraform` stage, and
`tools/check` will not catch that because our `stacks.yml` and `pipeline.yml` agree with each
other.

Expect conflicts in `pipeline/pipeline.yml`, `pipeline/stacks.yml`, `CLAUDE.md`. The restructure
moved `builder-mcp/` → `packages/builder-mcp/` and `aidlc-docs/` → `docs/aidlc/`; `main` has since
added `blueprints/knowledgebase/`, `blueprints/entra-probe/`, and `pipeline/terraform.yml` at the
old layout's paths.

**Done when:** `tools/check` passes, `pipeline.yml` still has all five stages (Source,
PipelineDeploy, Build, BlueprintDeploy, Terraform), and `stacks.yml` still lists knowledgebase.

### 0.2 Open a PR for the restructure

There is no PR for this branch. `main` still has `builder-mcp/` at the root, so two layouts are
diverging and every other team is planning against the old one. The restructure is only worth
having if it lands.

**Done when:** PR open against `main`, one approval, merged.

---

## P1 — Make the catalog real

The chatbot's job is search → create. Right now `blueprints/hello-world/blueprint.yaml` is the
only manifest in the repo, so there is exactly one thing to find.

### 1.1 Write `blueprints/knowledgebase/blueprint.yaml`

Track B's stack is merged and deploying on every merge to `main`, and its README says "Track A's
Builder MCP asks for it" — but `catalog.py:79` finds blueprints by globbing
`blueprints/*/blueprint.yaml` and Track B never wrote one. The chatbot cannot offer it.

Pure YAML, no AWS. Copy the shape from `blueprints/hello-world/blueprint.yaml`, then read
`blueprints/knowledgebase/infra/knowledgebase.yml` for the real parameters. Decisions to make
while writing it:

- `inputs` — mirror the template's parameters, mark which are required
- `singleton` — true if the template hardcodes its own identity, false if it takes a
  `DeploymentName`. Read the template; don't guess.
- `matches` — the phrases a builder would actually type ("chatbot over my course documents")
- `cost` — the `baseline_monthly_usd` gap is real; a rough figure beats `0`
- `data_classification` — course documents are not `public`
- `state` — a knowledge base is `derived`, the bucket behind it is `authoritative`

The `add-blueprint` skill covers the three-file mirror if you touch registration.

**Done when:** `tools/check` passes (`check_blueprint_manifests` enforces the template link), and
`blueprint_search("course documents")` ranks it first.

### 1.2 Decide what a Terraform blueprint looks like in the catalog — C1 change

C1 says `template` is a "repo-relative CFN template path (registered in `pipeline/stacks.yml`)",
and `validate_stacks.py:188` enforces that. Track C shipped `blueprints/entra-probe/`, which is
Terraform, has no CloudFormation template, and correctly has no `stacks.yml` entry.

**A Terraform blueprint is currently unrepresentable in the catalog.** That's a C1 contract
change, which per SPEC.md is a cross-team event — needs a PR naming C1 and agreement from Track C
and Track E.

Options to put in that PR: add a `deploys:` discriminator (`cloudformation` | `terraform`), or
make `template` a list of typed entries. Don't build either until it's agreed.

**Done when:** a decision exists in `docs/decisions/`, or the item is explicitly deferred.

### 1.3 Validate manifests instead of defaulting them

`Blueprint.from_manifest()` (`catalog.py:37-53`) reads every field with `.get()` and a fallback. A
manifest missing `metadata.name` loads as `"unnamed"` with `version="0.0.0"` and `template=""`.
Nothing errors. C1 is marked FROZEN and says "code and tests implement these" — nothing does.

`validate_stacks.py:check_blueprint_manifests()` only checks that `template` is present and
registered. It never looks at `apiVersion`, `kind`, `metadata`, `summary`, `matches`, the shape of
`inputs`, `cost`, `data_classification`, or `state`.

Two places, two jobs — do both:

1. **`validate_stacks.py`** — the PR gate for manifests authored in this repo. Extend
   `check_blueprint_manifests()` to check the full C1 key set and types.
2. **`Blueprint.from_manifest()`** — the runtime guard. On AgentCore the catalog loads over the
   GitHub API (`_load_remote`), where no PR check ever ran. Raise on a malformed manifest rather
   than serving `"unnamed"` to a builder.

**Done when:** a manifest with a missing `metadata.name` fails `tools/check`, and
`from_manifest({})` raises instead of returning a `Blueprint`.

---

## P2 — Test the edges

All 41 tests cover pure logic. `github_ops.py` and `aws_ops.py` are exercised only through
`dry_run` paths, which return before touching either. Both are testable with no account.

### 2.1 Golden test: patching the real `pipeline.yml`

Highest value item here. `patching.py` inserts a CloudFormation action into
`pipeline/pipeline.yml` by text insertion. The existing tests (`test_patching.py`) insert into a
fixture.

Nothing asserts that inserting into the **actual current** `pipeline.yml` produces a file that
still passes `validate_stacks.py` and `cfn-lint`. That is exactly the failure mode CLAUDE.md warns
about: a registration PR that looks fine, merges green, and deploys nothing.

Write a test that reads the repo's real `pipeline.yml`, inserts an action, and asserts the result
parses as YAML, has the action inside `BlueprintDeploy`, and round-trips byte-identically on
remove.

**Done when:** the test exists and fails if someone reshapes `pipeline.yml`.

### 2.2 GitHub edge tests with a fake transport

`github_ops.py` builds an `httpx.Client` (`:34`). `httpx.MockTransport` lets you assert the real
write path — branch created, files committed, PR opened, **no push to a tracked branch, no merge**
— with no network and no token.

The governance invariants in C3 ("no merge, no push to a tracked branch") are currently asserted
by code review only. Make them tests.

**Done when:** the non-dry-run path has coverage, including a test that fails if anything ever
calls the merge endpoint.

### 2.3 AWS edge tests with a stubbed client

`aws_ops.py` has five functions (`stack_status`, `pipeline_state`, `tagged_resources`, `restart`,
`_friendly`) and zero tests. `botocore.stub.Stubber` needs no credentials and no account.

Cover the paths that matter: a `ROLLBACK_COMPLETE` stack, a stack that doesn't exist, an
`AccessDenied`, and the C3 invariant that `restart` only ever calls
`StartPipelineExecution` / `RetryStageExecution` and never a CloudFormation write.

**Done when:** `aws_ops.py` has coverage, and `_friendly()` is asserted to turn each error into a
narrative rather than raising (NFR7).

---

## P3 — Guardrails and contract debt

### 3.1 Cap `deployment_restart` (BACKLOG: Operations & guardrails)

Agreed by the mob, not built. The refuse path and the message are pure logic. The open design
question is where the restart count lives, because the server is stateless (C4) — that part needs
a decision before code.

**Done when:** the cap is specced in SPEC.md C3 with the state mechanism named; implementation can
follow.

### 3.2 Reconcile the AI-DLC record with the code

`docs/aidlc/builder-mcp/aidlc-state.md` says gates 1 and 2 are "OPEN — awaiting answers". Both are
answered in the question files, and commit `592782d` is titled "Close Gates 1-2". It also says "22
tests green"; the real number is 41. `STAGE-GATES.md:108` says "Nothing is deployed", which stopped
being true when PR #10 merged.

`docs/aidlc/README.md` already explains the file is a stale snapshot. Either update the gate table
and the counts, or move both files under a dated archive path so nobody reads them as current.
Pick one — the current state is a document that contradicts itself next to a README apologising
for it.

**Done when:** no file in `docs/aidlc/builder-mcp/` states a fact the code contradicts.

### 3.3 Fix the two stale claims in `main`'s CLAUDE.md

After P0 lands, `CLAUDE.md` on `main` still says `builder-mcp/` is deliberately not built, and
that no stage invokes the container build. Both were true a few merges ago. Track E read the second
one and recorded it as a finding in their own state file, so this is actively misleading other
teams.

**Done when:** both statements match `pipeline/pipeline.yml`.

---

## Parked until someone has AWS

Not blocked on us. When an account is available, in this order:

1. **Deploy the AgentCore runtime** — `deploy/HANDOFF.md` is the runbook. Note PR #11 replaces
   Cognito with Entra ID client-credentials (C5), which adds hand-created pre-flight: an Azure app
   registration, two SSM parameters, and a Secrets Manager secret. Confirm which auth is landing
   before deploying.
2. **`deploy/verify.py`** against the live endpoint.
3. **End-to-end reliability run** (BACKLOG) — `deployment_create` → merge → pipeline → stack, more
   than once, so the answer is a rate and not an anecdote.
4. **Speed check** (BACKLOG) — needs an agreed start/stop boundary first. No performance targets
   exist anywhere; the NFR Requirements stage was skipped. This produces the first number.
5. **Cost spec** (BACKLOG) — estimate now without AWS, confirm against real bills later.

## Suggested order

P0.1 → P0.2 → P1.1 → P1.3 → P2.1 → P2.2 → P2.3 → P1.2 → P3.

P1.1 before P1.3 so the validator has a second real manifest to validate. P1.2 sits late because
it needs two other teams in the room. P2.1 is the one to do first if you only do one thing.
