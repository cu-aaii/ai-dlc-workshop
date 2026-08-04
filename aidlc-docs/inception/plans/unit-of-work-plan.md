# Unit of Work Plan — `dashboard` Blueprint

**Stage**: INCEPTION → Units Generation, Part 1 (Planning)
**Date**: 2026-08-03
**Inputs**: `inception/application-design/` (all five artifacts, approved 2026-08-03) ·
`inception/user-stories/stories.md` (approved) · `inception/requirements/requirements.md` (approved) ·
`inception/plans/execution-plan.md` (approved)

---

## What this stage decides, and why it matters more here than it looks

A unit of work is a logical grouping of stories for development. The vendored rules frame this in
microservice terms — "each unit becomes an independently deployable service" — and that framing does
**not** fit here. This blueprint is one CloudFormation deployment into a shared account behind one
CloudFront distribution. Independent deployability is not on the table.

So the question is not "how do we split the system." It is **"how many times do the CONSTRUCTION
stages run."** Functional Design, NFR Requirements, NFR Design, Infrastructure Design, Code Generation,
and Build and Test all execute per unit. Four units means four passes. That cost is real, the workshop
is Aug 3–4 (i.e. now), and it is the reason Q1 below leads with the smallest defensible number rather
than the most architecturally satisfying one.

There is exactly one boundary in this design that changes *how work is verified* rather than merely
how it is organised: C-04 and C-05 have empty dependency rows, use no AWS SDK, and can be built and
fully property-tested on a laptop with no pipeline, no account, and no deployed stack. Everything else
needs a deployed stack and a built image. That asymmetry is the strongest argument for any split at
all, and it is why the recommended answer separates the pure core and nothing else.

> **Amended 2026-08-03.** This plan originally said "everything else needs the never-yet-run container
> build." A branch rebase onto `main` landed a working `Build` stage, so that is no longer true — see
> `inception/amendments/repo-baseline-2026-08-03.md`. Three things changed here as a result: **Q6** was
> rewritten because its premise (no self-approval) is now false, **Q3** was corrected because it
> omitted the now-mandatory `blueprint.yaml`, and **Q8** and **Q9** were added for decisions that did
> not exist when the plan was written. Q1, Q2, Q4, Q5 and Q7 are unaffected.

---

## Part A — Questions

A recommended option is marked in each question. **A recommendation is not a default and nothing is
chosen for you.** Fill in each `[Answer]:` tag. Answer `X` and describe if none of the options fit.

---

### Question 1 — How many units, and where are the boundaries?

This is the consequential question; the rest mostly follow from it. Component IDs are from
`inception/application-design/components.md`.

**A) Two units — Domain Core, and Dashboard Platform** ← *recommended*
   - **U-01 Domain Core**: C-04 Inventory Model, C-05 Aggregation Core
   - **U-02 Dashboard Platform**: everything else — C-01, C-02, C-03, C-06, C-07, C-08, C-09, and the
     `pipeline.yml` / `stacks.yml` edits

   *Why*: it splits on the only boundary that changes the *method* of verification. U-01 is pure
   Python with no AWS, so it can be written and its properties exhaustively generated and run locally,
   before any pipeline machinery is trusted. That de-risks PBT-01..10 — 10 blocking rules — ahead of
   the riskiest infrastructure in the plan. Two CONSTRUCTION passes, not four.

   *Cost*: U-02 is large — 7 components and most of the stories. Its Functional Design and
   Infrastructure Design documents will be long, and a single Code Generation pass covers two Lambdas,
   a React app, an edge configuration, and a pipeline edit.

**B) Three units — Domain Core, Application, Platform Wiring**
   - **U-01 Domain Core**: C-04, C-05
   - **U-02 Application**: C-01, C-02, C-03, C-06, C-07
   - **U-03 Platform Wiring**: the `pipeline.yml` Build stage action, the Dockerfiles, the
     `stacks.yml` entry, C-08 Deployment Marker, C-09 Observability Set

   *Why*: U-03 isolates the deployment wiring — the Build stage action, the `Dockerfile` targets, the
   `stacks.yml` entry, and the `blueprint.yaml` manifest — which is the work US-15 does not cover. It
   gets its own Infrastructure Design pass instead of being the last third of a large unit's checklist.

   *Cost*: three CONSTRUCTION passes. U-03 cannot be verified without U-02 existing to build, so the
   isolation is organisational rather than genuinely independent. **This option was weakened by the
   2026-08-03 amendment**: its original justification was that U-03 held "the machinery nobody has run
   yet," and that machinery has now run. What remains is the story-coverage gap, which is a smaller
   reason for a whole unit than an unproven pipeline was.

**C) Four units — Domain Core, Collection, Presentation, Platform Wiring**
   - **U-01 Domain Core**: C-04, C-05
   - **U-02 Collection**: C-01, C-02, the EventBridge schedule
   - **U-03 Presentation**: C-03, C-06, C-07, API Gateway
   - **U-04 Platform Wiring**: as in option B

   *Why*: this is the decomposition the design actually supports. `services.md` already establishes
   S-01 and S-02 as separate failure domains touching at exactly one S3 key, and
   `component-dependency.md` shows C-01 and C-03 never referencing each other. So this split is not
   invented for the sake of having units — it traces a seam the design already documents.

   *Cost*: four CONSTRUCTION passes during a live workshop, for a system that deploys as one stack.
   Highest fidelity to the architecture, highest process overhead, and the two most similar units
   (Collection and Presentation) would each get their own NFR Requirements pass covering largely the
   same Lambda concerns.

**D) One unit — the whole blueprint**
   *Why*: it is one stack, one deployment, and the rules explicitly allow "the single unit represents
   the entire application with logical modules." Fastest to the workshop.

   *Cost*: no unit boundary means PBT work has no natural place to be completed and verified before
   the infrastructure work starts, and the single Functional Design document carries all 17 stories.
   The thing option A buys — proving the pure logic without touching AWS — has to be maintained as a
   discipline rather than a structure.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 2 — Where do the cross-cutting enabler stories go?

US-09 through US-15 are enablers, and several span whatever boundary Q1 draws. US-10 (the PBT suite)
tests U-01's logic but also needs generators for the collector's inputs. US-11 through US-14
(logging, alarms, monitoring) touch both Lambdas. US-15 is deployment. US-09 is supply chain across
Python, containers, and now npm.

**A) Assign each enabler to the unit that owns the most of it, and note the spillover** ← *recommended*
   Each story has exactly one owning unit; where it reaches into another, `unit-of-work-story-map.md`
   records that explicitly as a cross-unit obligation. Nothing is duplicated and nothing is orphaned.

   *Cost*: some stories will have an owner that covers, say, 70% of the work, and the remaining 30%
   depends on another unit's existence — a real sequencing constraint rather than a clean assignment.

**B) Split the enablers into per-unit slices** — e.g. US-10 becomes US-10a (Domain Core properties)
   and US-10b (collector/API properties). Cleanest assignment; every slice sits wholly in one unit.

   *Cost*: it edits an **approved** artifact. `stories.md` was approved on 2026-08-03 with US-09..US-15
   as written, and renumbering or splitting them changes the story set and the three coverage tables
   that end "No v1 functional requirement is uncovered."

**C) Put all seven enablers in their own unit** — a cross-cutting concerns unit.

   *Cost*: that unit would depend on every other unit and could not be completed until they all exist,
   which makes it a phase disguised as a unit. It also separates the tests from the code they test,
   which is the arrangement most likely to leave PBT-01..10 half-done.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 3 — Directory layout under `blueprints/dashboard/`

`blueprints/README.md` establishes that a blueprint is self-contained, and the existing convention is
`blueprints/<name>/infra/` for templates. Everything else is unestablished — `hello-world` has no
application code at all, so this blueprint sets the precedent that later blueprints will copy. That
is the reason to ask rather than pick.

**Updated 2026-08-03**: all three options originally omitted **`blueprint.yaml`**, which now exists at
`blueprints/hello-world/blueprint.yaml` and is parsed by `builder_mcp/catalog.py`. A blueprint without
one is invisible to the Cornell Builder MCP. It is not optional and it sits at the blueprint root in
every option below. Also note the container **Dockerfile is at the repo root** with one named target
per component — not per-directory — so the layouts below no longer place Dockerfiles inside the
blueprint. See `inception/amendments/repo-baseline-2026-08-03.md` §A1.2 and §A1.4.

**A) Group by kind, with the pure core as its own top-level package** ← *recommended*
```
blueprints/dashboard/
  blueprint.yaml    the manifest the Cornell Builder MCP reads — required
  infra/            dashboard.yml, and the repurposed marker template
  core/             the pure, AWS-free package — no boto3 import anywhere beneath here
  collector/        handler for C-01 (image built from the root Dockerfile target)
  api/              handler for C-03 (image built from the root Dockerfile target)
  ui/               package.json, package-lock.json, vite config, src/
  tests/            property tests and unit tests
```
*Why*: the `core/` boundary is enforceable rather than aspirational — "no `import boto3` under
`core/`" is a one-line check that keeps §4.5 true as the code grows. A reviewer can see the AWS-free
requirement in the tree.

**B) Group by unit**, one directory per unit from Q1, each containing its own infra/code/tests.
   *Why*: unit boundaries are visible in the filesystem, so ownership is unambiguous.
   *Cost*: `infra/` fragments across unit directories, which breaks the one existing convention
   (`blueprints/<name>/infra/`) that `hello-world` establishes and `stacks.yml` paths reflect.

**C) Flat** — `infra/`, `src/`, `ui/`, `tests/`, with the pure core as a subpackage of `src/`.
   *Why*: fewest directories; conventional Python layout.
   *Cost*: the AWS-free boundary becomes a convention inside `src/` rather than a visible structural
   fact, and it is the boundary 10 blocking PBT rules depend on.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 4 — One CloudFormation template, or several?

This has more leverage than it appears, because it may resolve a problem this design left open.
`application-design.md` §6.4 records that `aws s3 sync` in the Build stage targets a site bucket that
the stack has not created yet on a first deployment, and deferred the fix to Infrastructure Design.
Splitting the storage resources into their own template resolves it structurally — the buckets exist
before the Build stage runs, because a separate stack deployed them.

**A) Two templates — storage, then application** ← *recommended*
   - `dashboard-storage.yml`: the site bucket, the snapshot bucket
   - `dashboard.yml`: everything else

   *Why*: it resolves §6.4 by construction rather than by a workaround, and it puts the stateful
   resources in a stack that is never replaced — which matters because deleting a bucket during a
   stack update is exactly the kind of accident a shared workshop account cannot absorb.

   *Cost*: two registry entries, two `pipeline.yml` actions, and the application stack must receive
   the bucket names as parameters. Deploy order between them becomes load-bearing.

**B) One template — `dashboard.yml`**
   *Why*: simplest; matches `hello-world`'s single-template shape; one registry entry, one action.
   *Cost*: §6.4 stays unresolved and needs one of the other two fixes (sync after BlueprintDeploy, or
   resolve the bucket name by convention at sync time). And every update to the application touches
   the stack that owns the data.

**C) Three templates** — storage, application, and edge (CloudFront + WAF) separately.
   *Why*: CloudFront distributions are slow to update and the WAF allowlist is the thing most likely
   to be edited on its own, in a hurry, when someone is locked out.
   *Cost*: three stacks for one blueprint, and cross-stack parameter passing for origins.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 5 — Does CONSTRUCTION run unit-by-unit, or stage-by-stage across all units?

**A) Unit-by-unit, depth-first** ← *recommended*
   Take U-01 all the way through Functional Design → NFR → Infrastructure Design → Code Generation →
   Build and Test, then start U-02.

   *Why*: something works end-to-end sooner, and under option A of Q1 the first thing that works is
   the pure core with its property tests passing — the strongest possible foundation for everything
   built on top, verified before the risky infrastructure is touched.

   *Cost*: decisions made for U-01 may need revisiting when U-02's needs surface.

**B) Stage-by-stage, breadth-first** — all units through Functional Design, then all through NFR, etc.
   *Why*: cross-unit consistency at each stage; NFR decisions get made once with all units in view.
   *Cost*: nothing is verifiable until near the end. In a two-day workshop that is a real risk.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 6 — Ownership and team alignment

**This question was rewritten on 2026-08-03.** Its original premise — "nobody can approve their own
PR, so every change needs a second person" — was true when the plan was written and is now false. Per
`CLAUDE.md` and `inception/amendments/repo-baseline-2026-08-03.md` §A1.1: a PR is required and direct
pushes are rejected, but **zero approving reviews** are needed and a team member merges their own PR.
The `validate` check is the only automated gate between a branch and a shared-account deploy.

That inverts what this question is for. It is no longer "how do we satisfy a mandatory second
reviewer" — it is "**do we want a human reviewer at all, given nothing now requires one**," while
every merge to `main` still deploys to the shared account mid-workshop.

**A) One PR per unit, and ask for a human review even though none is required** ← *recommended*
   Units are sequencing devices; the PR boundary is a review boundary by choice, not by rule. One PR
   per unit keeps each review small enough for someone with no prior context.

   *Why*: `validate` lints templates and checks the registry. It cannot see a WAF allowlist that locks
   everyone out, a cache policy inverted so `/api/*` is cached, or an IAM policy scoped to `*` — the
   three failures this design spent the most effort guarding against. None of them fails a lint.

**B) One PR per unit, self-merged on a green `validate`**
   *Why*: fastest, and it is what the branch protection now expects.
   *Cost*: the only gate is a lint. Accepting this means accepting that a deny-by-default lockout or a
   bad cache policy reaches the shared account without a second pair of eyes.

**C) Units owned by different people, working in parallel**
   *Cost*: U-01 must be complete and stable before anyone can meaningfully work on U-02, since both
   other units call into it. Parallelism is bounded by the dependency graph regardless of headcount.

**D) Ownership is not being decided here** — record units as work groupings only and leave both
   assignment and review policy out of the artifacts.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 7 — What happens to the deferred cost stories?

US-D1 and US-D2 are the deferred cost placeholders. FR-8 is deferred with its data source (Cost
Explorer vs. CUR) deliberately undecided. All 17 stories must be assigned to units, so these two need
a home even though no one is building them now.

**A) Assign them to the unit that will eventually own them, marked deferred** ← *recommended*
   They land in whichever unit holds the collector under Q1's answer, tagged `DEFERRED — not in v1`.
   Coverage stays complete and the future home is on record.

**B) A separate deferred unit** (`U-DEFERRED`) holding US-D1, US-D2, and later the telemetry
   amendment's stories.
   *Why*: keeps v1 units free of anything nobody is building, and gives the queued telemetry amendment
   a place to land.
   *Cost*: a unit that never gets a CONSTRUCTION pass is arguably not a unit.

**C) Leave them unassigned** and note the exception.
   *Cost*: contradicts this stage's own completion criterion that all stories are assigned to units.

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 8 — arm64 or x86 for the two Lambdas? *(added 2026-08-03)*

**This question did not exist when the plan was written.** The approved Application Design says only
"container images," because at that time there was one container path and it had never been invoked.
The rebase changed that: there are now two paths with asymmetric evidence. See
`inception/amendments/repo-baseline-2026-08-03.md` §A1.2 and §A1.3.

- **arm64** — `ArmContainerBuildProject`, invoked by the `Build` stage for `builder-mcp`. Build →
  digest → deploy-by-digest is **proven end to end**.
- **x86** — `ContainerBuildProject`, known-good by inspection, **still never invoked**. It was added
  alongside the ARM project deliberately so its definition stays untouched "for future x86 Lambda
  images" — meaning the repo anticipates exactly this decision.

**A) arm64 for both Lambdas** ← *recommended*
   *Why*: it is the only container path with evidence behind it, and Lambda on arm64 (Graviton) is
   cheaper per GB-second — which matters for a blueprint whose own purpose is cost visibility. Reuses
   the proven `ArmContainerBuildProject` and the root `Dockerfile` target pattern.
   *Cost*: any Python wheel without an aarch64 build must compile from source in the image. For this
   design's dependencies (boto3 and the standard library — the pure core has none) that is unlikely to
   bite, but it is the real risk.

**B) x86 for both Lambdas**
   *Why*: the widest wheel compatibility, and `ContainerBuildProject` was the original reference
   project.
   *Cost*: this blueprint becomes the first thing ever to invoke it, which is the exact risk the
   amendment just retired. It reintroduces a resolved unknown for no stated benefit.

**C) You choose** — I pick and record the reasoning. (That would land on A.)

X) Other (describe after the `[Answer]:` tag)

[Answer]:

---

### Question 9 — The `blueprint.yaml` manifest values *(added 2026-08-03)*

`blueprint.yaml` is a real parsed contract now (§A1.4), and four of its fields need deliberate values
rather than copied ones. Answer whichever you have opinions on; where you skip, I will use the
recommendation and record that I did.

**9a — `data_classification`.** hello-world declares `[public]`. This dashboard exposes account
inventory: resource ARNs, owner NetIDs, deployment ids, and eventually cost figures.
   A) `[internal]` ← *recommended* — Cornell-internal; consistent with a WAF allowlist restricted to
      Cornell IP ranges, which is already the only access control
   B) `[public]` — matches hello-world; hard to justify given ARNs and NetIDs
   C) Something stricter (`[confidential]`, or a Cornell-specific term you use)

   [Answer]:

**9b — `singleton`.** hello-world sets `singleton: true` and its own comment says "**Real blueprints
should take a `DeploymentName` parameter instead**." The approved design has **no `DeploymentName`
parameter** — resources are named per app/environment, so exactly one dashboard can exist per
environment.
   A) Take a `DeploymentName` parameter, `singleton: false` ← *recommended* — follows the repo's own
      stated guidance for real blueprints. *Cost*: changes resource naming across every dashboard
      template, and the stack name must still fit `aidlc-<env>-*` for `BuildPipelineRole`
   B) `singleton: true`, keep the design as approved — one dashboard per environment is arguably
      correct for a dashboard *of* that environment. *Cost*: knowingly diverges from the guidance
   C) You choose

   [Answer]:

**9c — `state`.** Vocabulary is `stateless | derived | authoritative`.
   A) `derived` for the snapshot, nothing authoritative ← *recommended* — the snapshot is fully
      rebuildable by re-running the collector, which is already the stated basis for RESILIENCY-02's
      RTO/RPO N/A. Declaring it `derived` makes that consistent rather than merely compatible
   B) Something else (describe)

   [Answer]:

**9d — `cost`.** `baseline_monthly_usd` and `scales_with`.
   A) Estimate now from the resource set, and record it as an estimate ← *recommended*
   B) Leave `0` like hello-world until FR-8 lands. *Cost*: a cost dashboard misreporting its own cost
      is a bad look, and `0` is definitely wrong — CloudFront, WAF, and two Lambdas are not free
   C) You choose

   [Answer]:

---

## Part A1 — Categories evaluated and deliberately not asked about

Recorded so their absence reads as a decision rather than an omission.

- **Business domain / bounded contexts** — evaluated and **not asked**. There is one domain: the
  account's tagged resource inventory. There is one aggregate (the snapshot), one upstream source (the
  Tagging API), and no second business capability. A bounded-context question would be manufacturing a
  distinction the requirements do not contain. FR-8's cost data would introduce a second source, which
  is precisely why it is deferred with its data source undecided.
- **Inter-unit communication patterns** — evaluated and **not asked**. Already settled by the approved
  design: the two runtime services communicate through exactly one S3 object and never call each
  other, and the pure core is called in-process as a library. There is no messaging, queue, or
  synchronous inter-unit call to choose a pattern for. Reopening it here would relitigate an approved
  decision.
- **Scalability differing across units** — evaluated and **partly folded into Q4**. The only real
  difference is that stateful storage should outlive stateless compute, which is a template-boundary
  question, so it is asked there rather than twice. Throughput differences are immaterial at §4.4's
  stated volume (tens to low hundreds of resources).
- **RESILIENCY-04, -14, -15** — not asked. Already deferred to NFR Design by the extension's own
  scoping and recorded in `aidlc-state.md`. Asking now would move a gate that was already placed.
- **Q12/Q13** (`application-design-plan-clarification-2.md`) — not repeated here. They remain open,
  non-blocking, and independent of decomposition.

---

## Part B — Execution checklist (runs after you approve)

### B1. Preconditions
- [ ] Confirm every `[Answer]:` tag in Part A is filled — **Q1-Q9, including the four Q9 sub-tags**
- [ ] Run the mandatory Step 7 analysis over all answers — vagueness, undefined terms, contradiction,
      missing detail, option-merging — and raise follow-ups rather than proceeding if any is found
- [ ] Record resolved decisions and any interactions between answers in a `Part A2` section

### B2. `unit-of-work.md` (mandatory artifact)
- [ ] Define each unit: identity, purpose, components owned, and what it explicitly does **not** own
- [ ] State the responsibility boundary for each unit in terms a reviewer can check
- [ ] Record the verification method per unit — specifically, which units can be tested with no AWS
      account and which cannot, since that is the asymmetry the decomposition turns on
- [ ] Document the code organization strategy per Q3, including the enforceable no-`boto3` boundary if
      option A is chosen
- [ ] Record which units carry the known story-coverage gap (Build stage action, Dockerfiles) — now
      cheaper to close, since the `Build` stage exists and the root `Dockerfile` target pattern is
      established (amendment §A1.2)
- [ ] Record the chosen Lambda architecture (Q8) and, if x86, that it reintroduces an uninvoked path
- [ ] Include `blueprint.yaml` in the code-organization strategy with the Q9 values recorded
- [ ] Carry forward `application-design.md` §6.4 and note whether Q4's answer resolves it

### B3. `unit-of-work-dependency.md` (mandatory artifact)
- [ ] Dependency matrix, rows depending on columns, with the nature of each dependency
- [ ] Verify acyclicity and state it, rather than implying it
- [ ] Distinguish **runtime** dependencies from **build/deploy-order** dependencies — they differ here,
      and conflating them is what produces the CloudFormation-error-that-looks-like-a-template-bug
- [ ] Mermaid diagram with the mandated Material styling
- [ ] Record the critical path and what blocks what

### B4. `unit-of-work-story-map.md` (mandatory artifact)
- [ ] Map all 17 stories — US-01..US-15, US-D1, US-D2 — to units per Q2 and Q7
- [ ] Record cross-unit obligations where a story's work spills past its owning unit
- [ ] Coverage table proving every story is assigned, in both directions
- [ ] Preserve the requirement traceability from `stories.md` so FR→story→unit is followable end to end

### B5. Validation and honest reporting
- [ ] Validate unit boundaries against the approved component and dependency graphs — no unit owning
      half a component, no component owned twice
- [ ] Confirm all 17 stories are assigned to exactly one owning unit
- [ ] Confirm no unit depends on a unit that depends on it
- [ ] Report anything that cannot be settled here, naming the later stage that carries it, rather than
      inventing a decision to look complete

### B6. Completion
- [ ] Mark every step above `[x]`
- [ ] Update `aidlc-docs/aidlc-state.md`
- [ ] Append to `aidlc-docs/audit.md` with an ISO-8601 timestamp
- [ ] Present the `# 🔧 Units Generation Complete` message and wait for explicit approval
