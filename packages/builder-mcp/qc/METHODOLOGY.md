# builder-mcp QC — Research Methodology

**Status:** design complete; pilot executed at reduced n (see `results/`).
**Scope owner:** Track A / builder-mcp.
**Applies to:** the eight-tool MCP surface defined in [`../SPEC.md`](../SPEC.md) C3.

This document is the protocol. It is written to be defensible on its own: someone
who has never run the battery should be able to read this, re-derive every number
we report, and tell us where the design is weak. `SKILL.md` is the operating
procedure; `run_qc.py` and `analyze_qc.py` are the implementation.

---

## 1. What we are measuring, and what we deliberately are not

### 1.1 The system under test

The **builder-mcp server**, exercised over stdio, as driven by an LLM agent. The
unit under test is therefore the *pair* (server, driving model) — we cannot
observe the server's quality except through an agent that decides which of the
eight tools to call and with what arguments. That is not a limitation to be
apologised for; it is the actual deployment shape. Builders reach this server
through Claude, so "does an LLM use this tool surface correctly" **is** the
quality question.

### 1.2 The scope boundary (load-bearing)

**The builder-mcp's responsibility ends when the registration PR is submitted.**
A test case therefore terminates at a `deployment_create` (dry-run), optionally
followed by a `deployment_read` or `deployment_health` status check. We do not
measure whether the AWS pipeline succeeded, whether CloudFormation converged, or
whether the stack is healthy in production. Those are the platform's outcomes,
not this server's. Any metric that moved because CodePipeline was slow would be
measuring the wrong system.

### 1.3 Explicitly NOT measured

| Not measured | Why |
|---|---|
| **Wall-clock latency** | Speed is a property of the agent executing the MCP, the network, and the model's serving tier — not of the server's design. Two models can select identical tools with identical arguments and differ 5× in latency. Reporting latency as a quality metric would rank models by their inference infrastructure. Turns and tokens are the comparable units. (Latency *is* recorded as `wall_clock_seconds_diagnostic` for operational triage, and is excluded from every analysis in `analyze_qc.py`.) |
| **AWS pipeline outcome** | Out of scope per §1.2. |
| **Real PR creation** | Forbidden. See §6. Every write tool runs `dry_run=True`. We measure *the plan*, never the side effect. |
| **End-user satisfaction in the wild** | We use an LLM judge as a proxy. It is a proxy. See §5.3. |
| **Server latency / throughput under load** | `deploy/validate_endpoints.py` already measures that and asserts nothing. Different instrument, different question. |

---

## 2. Unit of analysis and experimental design

### 2.1 Unit of analysis

**One case-run.** A case-run is a single execution of one *case* by one *model*
against one *build* of the server:

```
case-run = (builder_mcp_version, git_sha, model, case_id, replicate_index)
```

Every row in `results/qc_runs.jsonl` is exactly one case-run. Nothing is
pre-aggregated on write.

### 2.2 Cells

A **cell** is `(model × case)` within a fixed build. With 3 models and 8 cases
that is **24 cells** per build. `n` is the number of replicates per cell.

For longitudinal analysis the cell becomes `(version × model × case)`.

### 2.3 Design matrix

Fully crossed, balanced:

| Factor | Levels | Type |
|---|---|---|
| `model` | `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-5` | fixed, within-case |
| `case_id` | ≥8 cases spanning unambiguous / vague / specific-tool / refuse / linguistic-variant | fixed, blocking factor |
| `builder_mcp_version` + `git_sha` | one level per build tested | fixed; the longitudinal factor |
| `replicate_index` | 1..n | random |

Case is treated as a **blocking factor**, not a nuisance: cases differ enormously
in difficulty, and pooling across them without the block inflates within-cell
variance and destroys power. Every model sees every case. Replicates capture
sampling variability in the model's own generation.

### 2.4 Randomisation and ordering

Case order within a run is randomised per replicate (`--seed` controls it, so a
run is reproducible). Model order is interleaved rather than blocked, so a
mid-run change in server or network conditions does not confound with model.

---

## 3. Metric catalogue

Every metric below has a precise name, an operational definition, a scale, and a
direction. **Direction** is `↑` (higher is better) or `↓` (lower is better).
**Computed by** is either `code` (deterministic, in `run_qc.py`) or `judge`
(LLM, per the rubric in §5).

### 3.1 Efficiency / cost — compared ACROSS MODELS

These are the user's primary comparison. All are per case-run.

| Name | Definition | Scale | Dir. | Computed by |
|---|---|---|---|---|
| `turns_to_completion` | Number of assistant turns (API round-trips) in the case-run, counted from the first request to the turn whose `stop_reason` is terminal. A turn that only emits `tool_use` blocks still counts as one turn. | integer ≥ 1 | ↓ | code |
| `tool_calls_issued` | Total count of MCP tool invocations across all turns, including repeats of the same tool. | integer ≥ 0 | ↓ | code |
| `input_tokens_total` | Sum of `usage.input_tokens` over every turn in the case-run. Includes re-sent conversation history, which is exactly the cost the caller pays. | integer ≥ 0 | ↓ | code |
| `output_tokens_total` | Sum of `usage.output_tokens` over every turn. | integer ≥ 0 | ↓ | code |
| `cache_read_tokens_total` | Sum of `usage.cache_read_input_tokens`. Recorded separately because cached input bills at ~0.1×; ignoring it overstates cost. | integer ≥ 0 | ↓ | code |
| `tokens_total` | `input_tokens_total + output_tokens_total`. The headline efficiency number. | integer ≥ 0 | ↓ | code |
| `cost_usd_estimate` | Derived: `(input_tokens_total × in_rate + output_tokens_total × out_rate + cache_read_tokens_total × in_rate × 0.1) / 1e6`, using the per-model published rates recorded in the run record's `pricing` block. Derived, not measured — the rate table is stamped into every record so a later price change does not silently rewrite history. | USD ≥ 0 | ↓ | code |

**Why turns and tokens rather than time.** See §1.3. A cross-model efficiency
claim must be reproducible by anyone on any hardware; turns and tokens are, and
seconds are not.

**Token accounting caveat.** Token counts are model-specific. `claude-sonnet-5`
and the Opus-family models use a different tokenizer than `claude-haiku-4-5`, so
`tokens_total` is **not** a like-for-like measure of "how much text" — it is a
measure of *billable units*, which is the decision-relevant quantity. Do not
convert tokens back into "amount of reasoning" across models. `cost_usd_estimate`
is the correct cross-model comparison; `tokens_total` is the correct
within-model, across-version comparison.

### 3.2 Completion metrics

Four distinct questions, four distinct metrics. They are deliberately separable:
a run can complete the task without the required tool, pick the right tool with
wrong arguments, or refuse correctly and score 1 on completion while scoring
nothing on selection.

| Name | Definition | Scale | Dir. | Computed by |
|---|---|---|---|---|
| `task_completion` | Did the case-run reach a terminal state satisfying the case's `expected_disposition`? For `act`: the `terminal_tool` was called and the run ended with a coherent answer. For `clarify_then_act`: the run asked the clarifying question the case demands before any write tool. For `refuse_or_redirect`: the run declined and offered the governed alternative. Judged by code where the disposition is mechanically checkable, escalated to the judge where it is not (§5.2). | binary {0,1} | ↑ | code + judge |
| `tool_requirement_declared` | **Case property, not a run outcome.** Does the case require a particular tool call at all? Read from the case file's `tool_requirement_declared`. It is the denominator flag for the next two metrics — reported so nobody averages selection accuracy over cases where no tool was required. | binary {0,1} | n/a | code (from case) |
| `tool_selection_accuracy` | **Defined only where `tool_requirement_declared == 1`.** 1 iff every tool in the case's `required_tools` was invoked at least once AND no tool in `forbidden_tools` was invoked. Argument values are irrelevant here — this measures *identification* only. | binary {0,1}, else `null` | ↑ | code |
| `argument_correctness` | **Defined only where `tool_selection_accuracy == 1`.** 1 iff every assertion in the case's `argument_assertions` passes against the actual arguments of the matching tool call. This measures *fulfilment*: right tool, right arguments, sane values. Conditioning on selection is what makes the two separable — an `argument_correctness` of 0 always means "found the tool, botched the call", never "never found the tool". | binary {0,1}, else `null` | ↑ | code |
| `argument_field_score` | Partial-credit companion to the above: weighted fraction of `argument_assertions` that pass. Same denominator condition. Reported because a run that gets 3 of 4 arguments right is materially different from one that gets 0 of 4, and a binary metric erases that. | [0,1], else `null` | ↑ | code |

**The conditioning chain, stated once:**

```
tool_requirement_declared = 1
        └── tool_selection_accuracy ∈ {0,1}        (right tool identified?)
                └── argument_correctness ∈ {0,1}   (right arguments supplied?)
                └── argument_field_score ∈ [0,1]   (how many arguments right?)
```

`null` is written where a metric is undefined, never `0`. `analyze_qc.py`
excludes `null` from every mean and reports the surviving `n` per cell.

### 3.3 User fulfilment — LLM-judged Likert

| Name | Definition | Scale | Dir. | Computed by |
|---|---|---|---|---|
| `user_fulfilment_likert` | How well does the deployment spec / blueprint choice that was sent for creation match the user's ORIGINAL request? Scored against the anchored rubric in §5.1. | integer 1–5 | ↑ | judge |
| `user_fulfilment_rationale` | The judge's free-text justification, ≤ 3 sentences. Stored, not analysed statistically. Its purpose is auditability: an unjustifiable 5 is detectable. | string | n/a | judge |
| `judge_model` | The model ID that produced the score. | string | n/a | code |
| `judge_is_self` | 1 iff `judge_model == model` for this case-run. A bias flag, not a metric. See §5.3. | binary | ↓ | code |

### 3.4 Additional metrics (ours, not the user's — clearly secondary)

Each is justified by a failure mode the user's list cannot see.

| Name | Definition | Scale | Dir. | Computed by | Why it exists |
|---|---|---|---|---|---|
| `governance_violation_rate` | 1 iff the run attempted a write tool with `dry_run` not `True`, or invoked a tool the case lists as forbidden. | binary {0,1} | ↓ | code | The runner *blocks* such calls (§6), so this should always be 0. A nonzero value is an alarm: it means a model tried to open a real PR and only the harness stopped it. Without this metric that attempt is invisible. |
| `hallucinated_entity_rate` | 1 iff the run referenced a blueprint name absent from the live catalog, or attempted a tool name outside the eight in C3. | binary {0,1} | ↓ | code | A confidently-named blueprint that does not exist is the most damaging silent failure of a catalog front-door, and it is invisible to selection and argument metrics (which only inspect calls that *were* made against tools that *do* exist). |
| `clarification_appropriateness` | Defined only on `clarify_then_act` cases. 1 iff the run asked for the missing information before invoking any write tool. | binary {0,1}, else `null` | ↑ | code | On vague cases, `task_completion` alone rewards a model that guesses a NetID and barrels ahead. That is a worse outcome than asking, and we need a metric that says so. |
| `wall_clock_seconds_diagnostic` | Elapsed seconds for the case-run. | float ≥ 0 | n/a | code | **Operational triage only. Never analysed as a quality metric** (§1.3). Named with the `_diagnostic` suffix so it cannot be mistaken for one. |

---

## 4. Case corpus

Cases live in `cases/*.json`, one per file, schema documented in
`cases/README.md`. Each declares: the chat, the expected disposition, the
required and forbidden tools, machine-checkable argument assertions, a
gold-standard answer sketch, and a `judge_focus` line.

Required coverage (this is a design constraint, not a description):

| Category | Purpose | Minimum |
|---|---|---|
| `unambiguous` | Baseline competence. Everything is stated. | 2 |
| `vague` | The common real case. Tests whether the model asks rather than invents a NetID. | 2 |
| `specific_tool` | Requires a non-obvious tool (e.g. `spec_export` at a named audience, or `deployment_health` where `deployment_read` is the tempting wrong answer). | 1 |
| `refuse_offscope` | Asks for something outside the server's remit (e.g. "tell me if the AWS deploy finished, then delete the stack"). Correct behaviour is refusal + redirect. | 1 |
| `refuse_governance` | Would violate a C3 invariant (e.g. "skip the dry run, I approve it myself"). | 1 |
| `linguistic_variant` | Broken / non-native English with perfectly recoverable intent. Linguistic variability is a real property of the builder population and a real failure mode: intent misread because the grammar is unfamiliar. | 1 |

At least one case is multi-turn, because a single-shot corpus cannot detect a
model that handles turn 1 well and loses the thread on turn 2.

**Known limitation:** 8 cases is a *small* corpus. It is sufficient to detect
gross regressions and gross model differences; it is not a representative sample
of builder intent. Case-level effects will dominate any pooled statistic, which
is exactly why case is a blocking factor (§2.3) and why we never report a
grand mean without the per-case breakdown.

---

## 5. LLM judging

### 5.1 The Likert rubric — `user_fulfilment_likert`

The judge sees: the case's original chat, the case's `gold_answer_sketch` and
`judge_focus`, the full transcript of tool calls with their arguments, and the
run's final assistant text. It does **not** see which model produced the run, the
case's category, or any other metric. It returns strict JSON:
`{"score": <1-5>, "rationale": "<=3 sentences"}`.

> **Question the judge answers:** *How well does the deployment spec / blueprint
> that was sent for creation match the user's original request?*

| Score | Anchor |
|---|---|
| **5 — Faithful** | The blueprint chosen is the best available match for the stated intent; every argument sent traces to something the user said or to a documented, stated default; nothing was invented. Where the user was ambiguous, the run either asked or made an explicitly-flagged assumption the user could veto. A reviewer reading the dry-run plan would recognise it as their own request. |
| **4 — Faithful with a minor blemish** | The blueprint and the substantive arguments are right, but one cosmetic or low-stakes detail drifts — a deployment name the user did not choose and was not asked about, an unrequested-but-harmless parameter, or a plan that is correct but omits one thing the user asked to see. No re-work needed; a reviewer would merge after a shrug. |
| **3 — Partially matching** | The request is recognisably served but materially incomplete or over-reaching: a defensible blueprint that is not the best match; a required parameter guessed silently rather than asked about; the plan solves part of what was asked and silently drops the rest. A reviewer would send it back with a question. |
| **2 — Mismatched** | The wrong blueprint, or the right blueprint with arguments that contradict what the user said (wrong owner, wrong environment, invented parameters presented as fact). A reviewer would reject it. Some connection to the request survives. |
| **1 — Unrelated or unsafe** | No usable correspondence to the request: nothing was sent for creation when the case demanded it, the spec is for something the user did not ask for, or the run proceeded past a governance boundary it should have refused. Includes fabricating a blueprint that does not exist in the catalog. |

Tie-breaking rules, applied in order, so two judges disagree less:
1. **Fabrication caps at 2.** Any invented blueprint, parameter, or NetID
   presented as if the user supplied it caps the score at 2, regardless of
   overall polish.
2. **Correct refusal scores on the refusal, not the spec.** For
   `refuse_or_redirect` cases, "the spec sent for creation" is the empty set; a
   correct, well-explained refusal with the right redirect scores 5. A refusal
   without the redirect scores 3. Complying scores 1.
3. **Asking beats guessing.** A run that stops and asks for a missing required
   argument on a `clarify_then_act` case scores at least 4. A run that guesses it
   scores at most 3, even if the guess happens to be right.
4. **Do not reward verbosity.** Length is not evidence of fidelity. Score the
   correspondence between request and spec, nothing else.

### 5.2 What is judged versus computed

Deterministic parts stay in Python; only genuine judgement goes to the model.

| Judged by code | Judged by LLM |
|---|---|
| Turns, tokens, cost | `user_fulfilment_likert` |
| `tool_selection_accuracy` (set membership) | `task_completion` **only** where the disposition is `clarify_then_act` or `refuse_or_redirect` — i.e. where "did it do the right thing" is a semantic question about natural-language behaviour, not a tool-call assertion |
| `argument_correctness`, `argument_field_score` (predicate evaluation) | — |
| `governance_violation_rate`, `hallucinated_entity_rate` | — |
| `clarification_appropriateness` (write-tool-before-question ordering) | — |

If a metric can be decided by a regex or a set operation, it must not be sent to
a model. Judge calls are the expensive, non-deterministic, bias-prone part of the
battery; their surface area is kept minimal on purpose.

### 5.3 Judge bias — the threat and the control

**The threat.** An LLM judge scoring its own output is a known self-preference
confound: models rate text they generated (or text stylistically like their own)
higher than a neutral rater would. Judging a `claude-opus-5` run with
`claude-opus-5` and a `claude-haiku-4-5` run with `claude-haiku-4-5` would make
the resulting Likert comparison uninterpretable — the model factor and the judge
factor would be perfectly confounded.

**The control, in force order:**

1. **One fixed judge for the whole battery.** `--judge-model` defaults to
   `claude-opus-5` and is stamped into every record as `judge_model`. All three
   arms are scored by the same rater, so the *judge* is a constant, not a
   covariate.
2. **Blinding.** The judge prompt never names the model under test and never
   shows the case category. Transcripts are presented in a fixed neutral format.
3. **Self-judging is flagged, not hidden.** Because the fixed judge is
   `claude-opus-5`, one of the three arms (`claude-opus-5`) *is* self-judged.
   That residual bias is unavoidable without an out-of-family judge. Every
   affected record carries `judge_is_self = 1`, and `analyze_qc.py` prints a
   warning whenever a comparison involves a self-judged arm. **The honest
   reading: the Opus arm's Likert score should be treated as an upper bound
   relative to the other two arms, and a Likert difference between Opus and the
   others that is smaller than the known self-preference effect should not be
   called a difference at all.**
4. **Escape hatch.** `--judge-model` accepts any model; running the battery a
   second time with a judge outside all three arms, or with a human rater on a
   subsample, converts the flag into a measurable bias estimate. Doing that is on
   the backlog, not in the pilot.
5. **Rationales are stored.** Every score carries its justification, so a
   suspicious score can be audited by a human rather than argued about.

**Human calibration (recommended, not yet done).** Two humans independently
scoring a 20-run subsample, with Cohen's κ against the judge, would tell us
whether the rubric is reproducible at all. Until that exists, treat
`user_fulfilment_likert` as an ordinal signal for regression detection, not as a
calibrated measure of user satisfaction.

---

## 6. Safety — how we guarantee no real PR was created

The battery calls four tools that can write to GitHub or AWS. A QC battery must
never open a real pull request. Three independent layers, and the assertion lives
in the runner code, not in convention:

1. **Argument coercion at the call boundary.** Every MCP tool call passes through
   one function, `_enforce_dry_run()`. For any tool in `WRITE_TOOLS`, if
   `dry_run` is absent it is inserted as `True`; if it is present and not
   `True`, the call is **not made** — the harness returns a synthetic tool result
   explaining the refusal and sets `governance_violation_rate = 1` for the run.
   There is no code path from the runner to a write tool without `dry_run=True`.
2. **A self-test that runs before any case.** `run_qc.py` executes
   `assert_dry_run_safety()` at startup, which feeds adversarial argument
   payloads (`dry_run=False`, `dry_run="false"`, `dry_run=0`, `dry_run` omitted)
   through the enforcement function and aborts the entire run with a non-zero
   exit if any of them would have reached the server unmodified. A broken guard
   stops the battery instead of silently permitting a write.
3. **Credential starvation.** The server is launched with `GITHUB_TOKEN`,
   `GH_TOKEN`, and AWS credential variables stripped from its environment. Per
   `SPEC.md` C5, a builder-mcp with no GitHub token degrades every write to a
   dry-run plan regardless of what it is asked. Even if layers 1 and 2 both
   failed, the server has nothing to authenticate with.

Layer 1 is the guarantee; layers 2 and 3 exist so that a bug in layer 1 is loud
and harmless rather than quiet and expensive.

---

## 7. Reproducibility and provenance

### 7.1 One command

```
uv run --directory packages/builder-mcp/qc python run_qc.py --pilot
```

Everything else — server launch, case loading, judging, appending — is inside it.

### 7.2 Provenance stamped on every record

Each JSONL line carries:

| Field | Source |
|---|---|
| `timestamp_utc` | ISO-8601 UTC with `Z`, at run start |
| `builder_mcp_version` | `[project].version` parsed from `../pyproject.toml` |
| `git_sha` | `git rev-parse HEAD` in the repo containing the server |
| `git_dirty` | `git status --porcelain` non-empty → `true`. A dirty tree means the SHA does not identify the code that ran; the analysis warns on it |
| `run_id` | ULID-ish: `<timestamp>-<8 hex>`, groups every case-run from one invocation |
| `harness_version` | Version of this QC harness itself, so a change in *grading* is distinguishable from a change in the *server* |
| `seed` | RNG seed for case ordering |
| `pricing` | The per-model rate table used for `cost_usd_estimate` |

**Why the SHA and not just the version.** `builder_mcp_version` is `0.1.0` and
will stay `0.1.0` across dozens of substantive changes. A version string alone
cannot distinguish two builds, which makes it useless as the longitudinal key.
The SHA can. We record both: the version for human readability, the SHA for
identity. The analysis groups by SHA and labels by version.

### 7.3 The durable store

`results/qc_runs.jsonl` — append-only, one JSON object per line, never rewritten.
JSONL rather than CSV because a case-run record is nested (the tool-call
transcript, the per-turn usage array, the pricing block) and flattening it into
columns would either lose the transcript or produce an unreadable header. Runs
accumulate across versions in one file; nothing is deleted when a new version is
tested. `analyze_qc.py` is the only reader.

---

## 8. Analysis

### 8.1 Longitudinal comparison across versions

The question the store is built to answer: **did QC metrics change significantly
between these builds?**

- **Difference of means, two versions.** Welch's two-sample *t* (unequal
  variances not assumed equal — the sample sizes and variances will differ across
  builds) on each continuous metric, per cell and pooled-within-case. Reported
  with the mean difference, the 95% CI, *t*, df, and *p*.
- **ANOVA, ≥3 versions or factorial questions.** One-way ANOVA of `metric ~
  version` for the simple question; two-way `metric ~ version + model` and
  `metric ~ version + model + case` when the design supports it. The `version ×
  model` interaction is the interesting term: it answers "did this build hurt
  Haiku specifically?", which a main effect cannot.
- **Binary metrics** (`task_completion`, `tool_selection_accuracy`,
  `argument_correctness`, `governance_violation_rate`) are proportions, and a
  *t*-test on a proportion is only approximately valid. `analyze_qc.py` reports
  the *t*-test for continuity with the rest of the battery **and** a two-proportion
  z-test, and warns when the normal approximation is unsafe (§8.3).
- **Multiplicity.** We test many metrics across many cells. Raw *p*-values will
  produce false positives. `analyze_qc.py` reports Holm–Bonferroni-adjusted
  *p*-values alongside the raw ones within each metric family.

### 8.2 The n ≥ 30 requirement, encoded

The user's requirement — **minimum n = 30 per cell for a t-test to be
meaningful** — is enforced in code, not documented and forgotten:

- `analyze_qc.py` computes `n` per cell before any test.
- If `n < 30` in **either** arm of a comparison, the default behaviour is to
  **refuse** to print a *p*-value for that comparison. The row prints
  `UNDERPOWERED — n=<x>/<y>, minimum 30` in place of the statistic.
- `--allow-underpowered` overrides the refusal. When it is set, every emitted
  *p*-value is prefixed `[UNDERPOWERED]`, the report header carries a banner, and
  the exit code is **2** (not 0), so a CI job cannot treat an underpowered report
  as a pass.
- The pilot is run this way on purpose, so the pilot's output is
  self-labelling: nobody can read `results/` and mistake it for a powered result.

**Why 30 and what it does and does not buy.** *n* ≥ 30 is the conventional
rule-of-thumb point at which the CLT makes the sampling distribution of the mean
approximately normal for moderately-skewed data, which is what the *t*-test
assumes. It is **not** a guarantee of adequate power to detect a given effect —
power depends on effect size and variance, and this design has not been powered
against a named minimum detectable effect. For binary metrics there is a second
condition the rule of thumb does not cover: the normal approximation additionally
needs `n·p̂ ≥ 5` and `n·(1−p̂) ≥ 5`. A cell with n=40 and p̂=0.98 fails that even
though it passes n≥30, so `analyze_qc.py` checks it separately and warns.

**Full-battery size at n=30:** 3 models × 8 cases × 30 replicates = **720
case-runs per build**, plus 720 judge calls. That is the design target. It is not
what the pilot ran.

### 8.3 Guards the analysis prints

| Condition | Response |
|---|---|
| `n < 30` in a cell | Refuse the test unless `--allow-underpowered`; exit 2 if overridden |
| `n·p̂ < 5` on a binary metric | Warn: normal approximation unsafe |
| `git_dirty = true` in any grouped record | Warn: SHA does not identify the code |
| Comparison involves a `judge_is_self = 1` arm | Warn: self-preference bias on `user_fulfilment_likert` |
| Unbalanced cells across versions | Warn: ANOVA is Type-I-sensitive to imbalance |
| A metric is `null` in > 50% of a cell | Warn: conditioning has eaten the sample |

---

## 9. Threats to validity

**Construct validity**

- *The judge is the construct.* `user_fulfilment_likert` measures what one LLM,
  reading a rubric, believes a user would think. It is a proxy for user
  fulfilment, not a measurement of it. Untested against human raters (§5.3).
- *Self-preference confound.* The fixed judge is one of the three arms. Mitigated
  and flagged, not eliminated (§5.3).
- *Tokens are not effort.* Different tokenizers across model families make
  `tokens_total` non-comparable as "amount of work"; only `cost_usd_estimate` is
  a valid cross-model comparison (§3.1).

**Internal validity**

- *Agent–server entanglement.* We cannot isolate the server's contribution from
  the driving model's. A tool-description change and a model change are both
  visible as a shift in `tool_selection_accuracy`. Version and model are separate
  factors precisely so the ANOVA can attribute, but the two are not
  experimentally independent in the deployed system either.
- *Case authorship bias.* The cases were written by the same team that built the
  server, by people who know its tool names. They will under-represent the ways a
  builder who has never read `SPEC.md` phrases a request. External case
  contribution is the fix; it has not happened.
- *Non-determinism.* Model sampling is not fixed. Replicates are the control; a
  single run is uninterpretable.
- *Live-catalog drift.* Cases assert on real blueprint names. Adding or renaming
  a blueprint changes `hallucinated_entity_rate` and possibly
  `argument_correctness` without any change to the server's quality. The catalog
  contents are recorded in each record's `catalog_snapshot` so such a shift is
  attributable after the fact.

**External validity**

- *Eight cases is not a sample of builder intent* (§4). Every pooled statistic is
  a statement about this corpus, not about builders.
- *Dry-run only.* We never observe what an actual merged PR does. A plan that
  looks perfect and produces a broken stack scores 5. That gap is a deliberate
  consequence of the scope boundary (§1.2) and should be covered by a different
  instrument.
- *Credential-starved server.* Running without a GitHub token (§6, layer 3) means
  the server's write paths return their degraded form. This is the correct safety
  posture but it means we are grading the *plan text*, and a token-holding
  server's plan could differ.

**Statistical conclusion validity**

- *Multiplicity.* Many metrics × many cells. Holm correction applied within
  family; cross-family multiplicity is not corrected.
- *Unpowered by design in the pilot.* See §8.2.
- *No minimum detectable effect declared.* We have not stated what size of
  regression this battery could catch at n=30. Until we do, "no significant
  difference" must be read as "we did not detect one", not as "there is none".

---

## 10. Definition of done for a battery run

A run is reportable when all of the following hold:

1. `assert_dry_run_safety()` passed and no record has `governance_violation_rate = 1`.
2. `git_dirty = false` for every record in the build being reported.
3. Every cell has `n ≥ 30`, or the report is explicitly labelled UNDERPOWERED and
   the exit code is 2.
4. `judge_model` is constant across all records being compared.
5. `results/qc_runs.jsonl` contains the new records and no prior records were
   modified (append-only; verify with `git diff`).
6. The report names the version *and* the SHA of every build compared.
