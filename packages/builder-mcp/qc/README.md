# builder-mcp QC

Reproducible quality-control battery for the eight-tool builder-mcp MCP server.
Runs sample builder chats against the live server across models, grades tool
selection and argument correctness deterministically, scores user fulfilment with
an LLM judge against an anchored rubric, and appends version-stamped records to a
durable store so QC metrics can be compared across builds.

| File | What it is |
|---|---|
| [`METHODOLOGY.md`](METHODOLOGY.md) | The research design. Metric definitions, Likert rubric, unit of analysis, power rationale, threats to validity. **Read this first.** |
| [`SKILL.md`](SKILL.md) | The agent-guided operating procedure — how an agent runs the battery, does the LLM judging, and appends results. |
| [`cases/`](cases/) | The sample builder chats, one JSON file each, with expected tools, argument assertions and gold-standard answer sketches. |
| `run_qc.py` | The runner. Launches the server over stdio, executes the matrix, grades, judges, appends. |
| `analyze_qc.py` | Difference-of-means (Welch *t*) + ANOVA across builds, with the n≥30 power guard. |
| `results/qc_runs.jsonl` | Append-only JSONL store. One line = one case-run. |

---

## Run it — one command

**Pilot, no API key needed** (deterministic gold-call replay; validates the whole
pipeline and writes real version-stamped records):

```sh
cd packages/builder-mcp/qc
uv run --with mcp python run_qc.py --pilot
```

**Full battery** (3 models × the case corpus × 30 replicates; needs
`ANTHROPIC_API_KEY`):

```sh
uv run --with mcp --with anthropic python run_qc.py --replicates 30
```

**Analyse:**

```sh
uv run python analyze_qc.py --summary --by-model
uv run python analyze_qc.py --compare <shaA> <shaB> --by-cell   # across builds
uv run python analyze_qc.py --anova version
```

---

## Safety — no real pull request, ever

Every write tool (`deployment_create`, `deployment_update`, `deployment_restart`,
`deployment_delete`) is called with `dry_run=True` and nothing else. Three
independent layers, asserted in code rather than by convention:

1. **`_enforce_dry_run()`** — the single call boundary. Missing `dry_run` is
   inserted as `True`; a `dry_run` that is not exactly boolean `True` means the
   call is **never forwarded** to the server and the run is flagged
   `governance_violation_rate = 1`.
2. **`assert_dry_run_safety()`** — runs before any case, feeding adversarial
   payloads (`False`, `"false"`, `0`, `"true"`, omitted, …) through the guard and
   aborting the battery with exit 3 if any could slip past.
3. **Credential starvation** — the server is launched with `GITHUB_TOKEN`,
   `GH_TOKEN` and AWS credentials stripped. Per SPEC C5 a token-less builder-mcp
   degrades every write to a dry-run plan regardless of what it is asked.

---

## Reproducibility

Every record carries `timestamp_utc` (ISO-8601 Z), `builder_mcp_version` (from
`../pyproject.toml`), `git_sha` + `git_dirty`, `harness_version`, `run_id`,
`seed`, the pricing table used, and a snapshot of the blueprint catalog. The
version string alone is too coarse to identify a build — `0.1.0` will span dozens
of substantive changes — so the SHA is the longitudinal key and the version is
the human label.

`results/qc_runs.jsonl` is append-only. Runs accumulate across versions in one
file; nothing is rewritten.

## The n ≥ 30 guard

`analyze_qc.py` **refuses** to print a *p*-value for any cell with fewer than 30
observations, printing `UNDERPOWERED — n=x/y, minimum 30` instead.
`--allow-underpowered` forces them out, but then every statistic is prefixed
`[UNDERPOWERED]`, a banner is printed, and the **exit code is 2** — so no CI job
and no reader can mistake an underpowered report for a pass. Rationale and the
extra `n·p̂ ≥ 5` condition for binary metrics are in METHODOLOGY.md §8.2.

## Scope boundary

A case ends when the registration PR is **submitted** (as a dry-run plan),
optionally followed by a `deployment_read`/`deployment_health` status check. This
battery does not measure whether the AWS pipeline finished — that is the
platform's outcome, not this server's. It also does not report latency as a
quality metric: speed is a property of the agent executing the MCP, so turns and
tokens are the comparable units. See METHODOLOGY.md §1.
