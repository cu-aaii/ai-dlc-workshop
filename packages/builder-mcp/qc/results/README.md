# results/

`qc_runs.jsonl` — the append-only QC store. One JSON object per line, one line
per **case-run** (`version × sha × model × case × replicate`). Never rewrite a
line; only append.

`pilot_report.txt` — output of `analyze_qc.py` for the committed pilot.

---

## ⚠️ WHAT IS CURRENTLY IN THIS STORE IS A PILOT. IT IS UNDERPOWERED. ⚠️

**n = 2 per (model × case) cell against a design minimum of 30.**
**Driver = `harness`, not `api`. There is no model comparison in this data and no
Likert score in this data.**

| | |
|---|---|
| Records | 20 case-runs |
| Build | `0.1.0 @ c60c7a92` (`git_dirty = true` — the SHA does not fully identify the tree) |
| Driver | `harness` — deterministic gold-call replay against the live MCP server. **No LLM was in the loop.** |
| Models compared | **none.** `model = "harness-gold-replay"` on every record |
| `user_fulfilment_likert` | `null` on every record (no `ANTHROPIC_API_KEY` was available) |
| `metrics_complete` | `false` on every record |
| n per cell | **2** (design minimum: **30**) |
| `analyze_qc.py` exit code | **2** |

### What this pilot does and does not establish

**Does:** the server launches over stdio, exposes exactly the eight C3 tools, the
dry-run guard holds under adversarial payloads, the argument predicates evaluate,
and a timestamped + version-stamped + SHA-stamped record reaches the store. The
pipeline is proven end to end.

**Does not:** say anything whatsoever about model quality, efficiency, cost, or
user fulfilment. `turns_to_completion = 1.000` and `tokens_total = 0` are
artefacts of the harness driver replaying a scripted call — they are **not**
measurements of any model. Do not put these numbers on a slide as model results.

### Before anything here is quotable

1. Re-run with `--driver api --replicates 30` and an `ANTHROPIC_API_KEY`.
2. Confirm `analyze_qc.py` exits 0.
3. Filter with `--driver api`. Harness and api records must never be pooled.

Rationale for the n ≥ 30 threshold and the extra `n·p̂ ≥ 5` condition on binary
metrics: [`../METHODOLOGY.md`](../METHODOLOGY.md) §8.2.
