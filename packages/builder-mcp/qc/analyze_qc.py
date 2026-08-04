# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""builder-mcp QC — longitudinal analysis.

Reads the append-only JSONL store and answers: did the QC metrics change
significantly between these builds of builder-mcp?

    uv run python analyze_qc.py --summary
    uv run python analyze_qc.py --compare <shaA> <shaB>
    uv run python analyze_qc.py --anova

THE n >= 30 GUARD
-----------------
Per METHODOLOGY.md section 8.2, a difference-of-means test on a cell with fewer
than 30 observations is not reported. The comparison prints
"UNDERPOWERED - n=x/y, minimum 30" instead of a p-value. --allow-underpowered
overrides that, but then every statistic is prefixed [UNDERPOWERED], a banner is
printed, and the process exits 2 so no CI job can mistake it for a pass.

No third-party dependencies: t, F and z distributions are evaluated from
first principles so this runs anywhere `uv` runs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "qc_runs.jsonl"

MIN_N = 30  # METHODOLOGY.md 8.2

CONTINUOUS_METRICS = [
    "turns_to_completion",
    "tool_calls_issued",
    "input_tokens_total",
    "output_tokens_total",
    "tokens_total",
    "cost_usd_estimate",
    "argument_field_score",
    "user_fulfilment_likert",
]

BINARY_METRICS = [
    "task_completion",
    "tool_selection_accuracy",
    "argument_correctness",
    "governance_violation_rate",
    "hallucinated_entity_rate",
    "clarification_appropriateness",
]

ALL_METRICS = CONTINUOUS_METRICS + BINARY_METRICS

EXCLUDED_FROM_ANALYSIS = {"wall_clock_seconds_diagnostic"}  # METHODOLOGY 1.3


# ---------------------------------------------------------------------------
# Distributions (no scipy)
# ---------------------------------------------------------------------------


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - _log_beta(a, b))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1 - x) + a * math.log(x) - _log_beta(b, a)) \
        * _betacf(b, a, 1 - x) / b


def t_sf_two_sided(t: float, df: float) -> float:
    if df <= 0 or not math.isfinite(t):
        return float("nan")
    x = df / (df + t * t)
    return betainc(df / 2.0, 0.5, x)


def f_sf(f: float, df1: float, df2: float) -> float:
    if f <= 0 or df1 <= 0 or df2 <= 0 or not math.isfinite(f):
        return float("nan")
    x = df2 / (df2 + df1 * f)
    return betainc(df2 / 2.0, df1 / 2.0, x)


def normal_sf_two_sided(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def holm(pvals: list[tuple[str, float]]) -> dict[str, float]:
    """Holm-Bonferroni step-down adjustment within a family."""
    usable = [(k, p) for k, p in pvals if p == p]      # drop NaN
    ordered = sorted(usable, key=lambda kv: kv[1])
    m = len(ordered)
    out: dict[str, float] = {}
    running = 0.0
    for i, (k, p) in enumerate(ordered):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    for k, p in pvals:
        out.setdefault(k, float("nan"))
    return out


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def var(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def welch_t(a: list[float], b: list[float]) -> dict[str, float]:
    na, nb = len(a), len(b)
    ma, mb = mean(a), mean(b)
    va, vb = var(a), var(b)
    if na < 2 or nb < 2 or not math.isfinite(va) or not math.isfinite(vb):
        return {"t": float("nan"), "df": float("nan"), "p": float("nan"),
                "diff": mb - ma, "ci_lo": float("nan"), "ci_hi": float("nan")}
    se2 = va / na + vb / nb
    if se2 == 0:
        return {"t": 0.0, "df": float(na + nb - 2), "p": 1.0,
                "diff": mb - ma, "ci_lo": 0.0, "ci_hi": 0.0}
    se = math.sqrt(se2)
    t = (mb - ma) / se
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    # t critical at 95% via bisection on the two-sided survival function
    lo, hi = 0.0, 100.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if t_sf_two_sided(mid, df) > 0.05:
            lo = mid
        else:
            hi = mid
    tcrit = (lo + hi) / 2
    return {"t": t, "df": df, "p": t_sf_two_sided(t, df), "diff": mb - ma,
            "ci_lo": (mb - ma) - tcrit * se, "ci_hi": (mb - ma) + tcrit * se}


def two_proportion_z(a: list[float], b: list[float]) -> dict[str, float]:
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return {"z": float("nan"), "p": float("nan"), "safe": False}
    pa, pb = mean(a), mean(b)
    pool = (sum(a) + sum(b)) / (na + nb)
    se = math.sqrt(pool * (1 - pool) * (1 / na + 1 / nb))
    safe = all(n * p >= 5 and n * (1 - p) >= 5
               for n, p in ((na, pa), (nb, pb)))
    if se == 0:
        return {"z": 0.0, "p": 1.0, "safe": safe}
    z = (pb - pa) / se
    return {"z": z, "p": normal_sf_two_sided(z), "safe": safe}


def one_way_anova(groups: dict[str, list[float]]) -> dict[str, float]:
    gs = {k: v for k, v in groups.items() if len(v) >= 2}
    k = len(gs)
    if k < 2:
        return {"F": float("nan"), "df1": float("nan"), "df2": float("nan"),
                "p": float("nan"), "eta_sq": float("nan")}
    allx = [x for v in gs.values() for x in v]
    n = len(allx)
    gm = mean(allx)
    ssb = sum(len(v) * (mean(v) - gm) ** 2 for v in gs.values())
    ssw = sum((x - mean(v)) ** 2 for v in gs.values() for x in v)
    df1, df2 = k - 1, n - k
    if df2 <= 0 or ssw == 0:
        return {"F": float("nan"), "df1": float(df1), "df2": float(df2),
                "p": float("nan"), "eta_sq": float("nan")}
    F = (ssb / df1) / (ssw / df2)
    return {"F": F, "df1": float(df1), "df2": float(df2),
            "p": f_sf(F, df1, df2), "eta_sq": ssb / (ssb + ssw)}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def load(path: Path, driver: str | None) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"FATAL: no results store at {path}. Run run_qc.py first.")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    if driver:
        rows = [r for r in rows if r.get("driver") == driver]
    return rows


def build_key(r: dict) -> str:
    return f"{r['builder_mcp_version']}@{r.get('git_sha_short') or r['git_sha'][:8]}"


def values(rows: list[dict], metric: str) -> list[float]:
    out = []
    for r in rows:
        v = r.get("metrics", {}).get(metric)
        if v is not None and isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
    return out


def fmt_p(p: float) -> str:
    if p != p:
        return "  n/a "
    return f"{p:.4f}" if p >= 1e-4 else "<1e-4"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def report_summary(rows: list[dict]) -> bool:
    """Returns True if any build has a cell below MIN_N."""
    underpowered = False
    print("=" * 92)
    print("STORE SUMMARY")
    print("=" * 92)
    builds = defaultdict(list)
    for r in rows:
        builds[build_key(r)].append(r)
    for b, rs in sorted(builds.items()):
        drivers = sorted({r.get("driver", "?") for r in rs})
        judges = sorted({str(r.get("judge_model")) for r in rs})
        dirty = any(r.get("git_dirty") for r in rs)
        print(f"\nbuild {b}   n={len(rs)} case-runs   drivers={drivers}   "
              f"judge={judges}   git_dirty={dirty}")
        cells = defaultdict(int)
        for r in rs:
            cells[(r["model"], r["case_id"])] += 1
        ns = sorted(cells.values())
        if ns[0] < MIN_N:
            underpowered = True
        print(f"  cells (model x case): {len(cells)}   n/cell min={ns[0]} "
              f"max={ns[-1]}   "
              f"{'OK' if ns[0] >= MIN_N else f'*** UNDERPOWERED: n/cell < {MIN_N} ***'}")
        print(f"  {'metric':<32}{'n':>6}{'mean':>12}{'sd':>12}")
        for m in ALL_METRICS:
            v = values(rs, m)
            if not v:
                continue
            sd = math.sqrt(var(v)) if len(v) > 1 else float("nan")
            print(f"  {m:<32}{len(v):>6}{mean(v):>12.4f}{sd:>12.4f}")
    return underpowered


def report_by_model(rows: list[dict]) -> None:
    print("\n" + "=" * 92)
    print("EFFICIENCY / COST ACROSS MODELS  (turns and tokens; latency is NOT a "
          "quality metric)")
    print("=" * 92)
    models = sorted({r["model"] for r in rows})
    head = f"{'metric':<28}" + "".join(f"{m[:22]:>24}" for m in models)
    print(head)
    for m in ["turns_to_completion", "tool_calls_issued", "input_tokens_total",
              "output_tokens_total", "tokens_total", "cost_usd_estimate",
              "user_fulfilment_likert", "task_completion",
              "tool_selection_accuracy", "argument_correctness"]:
        cells = []
        for mo in models:
            v = values([r for r in rows if r["model"] == mo], m)
            cells.append(f"{mean(v):.3f} (n={len(v)})" if v else "-")
        print(f"{m:<28}" + "".join(f"{c:>24}" for c in cells))


def guard(na: int, nb: int, allow: bool) -> str | None:
    if na >= MIN_N and nb >= MIN_N:
        return None
    msg = f"UNDERPOWERED - n={na}/{nb}, minimum {MIN_N}"
    return f"[UNDERPOWERED] {msg}" if allow else msg


def report_compare(rows: list[dict], a_key: str, b_key: str,
                   allow: bool, by_cell: bool) -> bool:
    """Difference of means between two builds. Returns True if anything was
    suppressed or flagged as underpowered."""
    A = [r for r in rows if build_key(r).startswith(a_key)]
    B = [r for r in rows if build_key(r).startswith(b_key)]
    if not A or not B:
        raise SystemExit(f"FATAL: build not found (A n={len(A)}, B n={len(B)}). "
                         f"Run --summary to see available builds.")
    print("\n" + "=" * 92)
    print(f"DIFFERENCE OF MEANS   A={build_key(A[0])} (n={len(A)})   "
          f"-> B={build_key(B[0])} (n={len(B)})")
    print("=" * 92)

    for label, rs in (("A", A), ("B", B)):
        if any(r.get("git_dirty") for r in rs):
            print(f"  [warn] build {label} contains records with git_dirty=true - "
                  f"the SHA does not identify the code that ran.")
        if any(r.get("judge_is_self") for r in rs):
            print(f"  [warn] build {label} contains self-judged runs "
                  f"(judge_is_self=1): user_fulfilment_likert carries a "
                  f"self-preference bias. See METHODOLOGY.md 5.3.")
        if len({r.get("judge_model") for r in rs}) > 1:
            print(f"  [warn] build {label} mixes judge models - Likert is not "
                  f"comparable across them.")

    underpowered = False
    raw: list[tuple[str, float]] = []
    lines: list[tuple[str, str]] = []

    print(f"\n{'metric':<30}{'meanA':>10}{'meanB':>10}{'diff':>10}"
          f"{'95% CI':>22}{'t':>9}{'p':>9}")
    print("-" * 92)
    for m in CONTINUOUS_METRICS:
        a, b = values(A, m), values(B, m)
        if not a and not b:
            continue
        g = guard(len(a), len(b), allow)
        if g and not allow:
            print(f"{m:<30}{mean(a):>10.3f}{mean(b):>10.3f}   {g}")
            underpowered = True
            continue
        if g:
            underpowered = True
        st = welch_t(a, b)
        raw.append((m, st["p"]))
        ci = f"[{st['ci_lo']:.3f}, {st['ci_hi']:.3f}]"
        prefix = "[UNDERPOWERED] " if g else ""
        print(f"{m:<30}{mean(a):>10.3f}{mean(b):>10.3f}{st['diff']:>10.3f}"
              f"{ci:>22}{st['t']:>9.3f}{fmt_p(st['p']):>9}  {prefix}")

    print(f"\n{'binary metric':<30}{'pA':>10}{'pB':>10}{'diff':>10}"
          f"{'t p':>12}{'z p':>12}  note")
    print("-" * 92)
    for m in BINARY_METRICS:
        a, b = values(A, m), values(B, m)
        if not a and not b:
            continue
        g = guard(len(a), len(b), allow)
        if g and not allow:
            print(f"{m:<30}{mean(a):>10.3f}{mean(b):>10.3f}   {g}")
            underpowered = True
            continue
        if g:
            underpowered = True
        st = welch_t(a, b)
        zt = two_proportion_z(a, b)
        raw.append((m, st["p"]))
        note = "" if zt["safe"] else "normal approx UNSAFE (n*p<5)"
        if g:
            note = ("[UNDERPOWERED] " + note).strip()
        print(f"{m:<30}{mean(a):>10.3f}{mean(b):>10.3f}{st['diff']:>10.3f}"
              f"{fmt_p(st['p']):>12}{fmt_p(zt['p']):>12}  {note}")

    if raw:
        adj = holm(raw)
        print("\nHolm-Bonferroni adjusted p-values (within this comparison family):")
        for k, _ in raw:
            print(f"  {k:<34}{fmt_p(adj[k])}")

    if by_cell:
        print("\nPer-cell (model x case) breakdown, tokens_total:")
        keys = sorted({(r["model"], r["case_id"]) for r in A + B})
        for mo, ci in keys:
            a = values([r for r in A if r["model"] == mo and r["case_id"] == ci],
                       "tokens_total")
            b = values([r for r in B if r["model"] == mo and r["case_id"] == ci],
                       "tokens_total")
            if not a or not b:
                continue
            g = guard(len(a), len(b), allow)
            if g and not allow:
                print(f"  {mo:<28}{ci:<34}{g}")
                underpowered = True
                continue
            st = welch_t(a, b)
            print(f"  {mo:<28}{ci:<34}{mean(a):>9.1f}->{mean(b):>9.1f}  "
                  f"p={fmt_p(st['p'])}")
    return underpowered


def report_anova(rows: list[dict], factor: str, allow: bool) -> bool:
    print("\n" + "=" * 92)
    print(f"ONE-WAY ANOVA  metric ~ {factor}")
    print("=" * 92)
    if factor == "version":
        keyf = build_key
    elif factor == "model":
        keyf = lambda r: r["model"]
    else:
        keyf = lambda r: r["case_id"]

    groups_all = defaultdict(list)
    for r in rows:
        groups_all[keyf(r)].append(r)
    if len(groups_all) < 2:
        print(f"  only {len(groups_all)} level of '{factor}' present - ANOVA needs "
              f">=2. Nothing to test.")
        return False

    ns = {k: len(v) for k, v in groups_all.items()}
    print(f"  levels: " + ", ".join(f"{k} (n={n})" for k, n in sorted(ns.items())))
    if len(set(ns.values())) > 1:
        print("  [warn] unbalanced design - one-way ANOVA is sensitive to "
              "imbalance under heteroscedasticity.")

    underpowered = False
    print(f"\n{'metric':<30}{'F':>10}{'df1':>6}{'df2':>8}{'p':>10}{'eta^2':>9}  note")
    print("-" * 92)
    raw: list[tuple[str, float]] = []
    for m in ALL_METRICS:
        groups = {k: values(v, m) for k, v in groups_all.items()}
        groups = {k: v for k, v in groups.items() if v}
        if len(groups) < 2:
            continue
        small = [k for k, v in groups.items() if len(v) < MIN_N]
        if small and not allow:
            print(f"{m:<30}{'':>34}UNDERPOWERED - levels below n={MIN_N}: "
                  f"{', '.join(f'{k}({len(groups[k])})' for k in small)}")
            underpowered = True
            continue
        if small:
            underpowered = True
        st = one_way_anova(groups)
        raw.append((m, st["p"]))
        note = "[UNDERPOWERED]" if small else ""
        print(f"{m:<30}{st['F']:>10.3f}{st['df1']:>6.0f}{st['df2']:>8.0f}"
              f"{fmt_p(st['p']):>10}{st['eta_sq']:>9.3f}  {note}")
    if raw:
        adj = holm(raw)
        print("\nHolm-Bonferroni adjusted p-values:")
        for k, _ in raw:
            print(f"  {k:<34}{fmt_p(adj[k])}")
    return underpowered


def report_integrity(rows: list[dict]) -> None:
    print("\n" + "=" * 92)
    print("INTEGRITY CHECKS")
    print("=" * 92)
    viol = [r for r in rows if r["metrics"].get("governance_violation_rate")]
    print(f"  governance violations (attempted non-dry-run write): {len(viol)}"
          + ("  <-- INVESTIGATE" if viol else "  (clean)"))
    hall = [r for r in rows if r["metrics"].get("hallucinated_entity_rate")]
    print(f"  hallucinated blueprint/tool references:              {len(hall)}")
    errs = [r for r in rows if r.get("run_error")]
    print(f"  runs with a harness/API error:                       {len(errs)}")
    jerr = [r for r in rows if r["metrics"].get("judge_error")]
    print(f"  runs where judging did not produce a score:          {len(jerr)}")
    incomplete = [r for r in rows if not r.get("metrics_complete")]
    if incomplete:
        print(f"  records with metrics_complete=false:                 "
              f"{len(incomplete)}  (no Likert; do not pool with api-driver runs)")
    for m in ALL_METRICS:
        cells = defaultdict(list)
        for r in rows:
            cells[(r["model"], r["case_id"])].append(r["metrics"].get(m))
        for (mo, ci), vs in cells.items():
            if vs and sum(v is None for v in vs) / len(vs) > 0.5:
                print(f"  [warn] {m} is null in >50% of cell ({mo}, {ci}) - "
                      f"conditioning has eaten the sample")
                break


def main() -> int:
    p = argparse.ArgumentParser(description="builder-mcp QC longitudinal analysis")
    p.add_argument("--results", type=Path, default=RESULTS_PATH)
    p.add_argument("--driver", default=None,
                   help="restrict to one driver ('api' or 'harness'). Records from "
                        "different drivers must never be pooled.")
    p.add_argument("--summary", action="store_true")
    p.add_argument("--by-model", action="store_true")
    p.add_argument("--compare", nargs=2, metavar=("BUILD_A", "BUILD_B"),
                   help="difference of means between two builds "
                        "(version@sha prefix, or just the sha prefix)")
    p.add_argument("--by-cell", action="store_true",
                   help="with --compare, also break down per (model x case)")
    p.add_argument("--anova", nargs="?", const="version",
                   choices=["version", "model", "case"],
                   help="one-way ANOVA over the named factor (default: version)")
    p.add_argument("--allow-underpowered", action="store_true",
                   help="emit statistics for cells with n<30. Every result is "
                        "prefixed [UNDERPOWERED] and the exit code becomes 2.")
    args = p.parse_args()

    rows = load(args.results, args.driver)
    if not rows:
        raise SystemExit("FATAL: no records matched.")

    if args.allow_underpowered:
        print("!" * 92)
        print("!!  --allow-underpowered IS SET. Statistics below may be computed "
              "from cells with n < 30.")
        print("!!  Per METHODOLOGY.md 8.2 these p-values are NOT interpretable as "
              "evidence. Exit code 2.")
        print("!" * 92)

    if not any([args.summary, args.by_model, args.compare, args.anova]):
        args.summary = True
        args.by_model = True

    underpowered = False
    tested = bool(args.compare or args.anova)
    if args.summary:
        underpowered |= report_summary(rows)
    if args.by_model:
        report_by_model(rows)
    if args.compare:
        underpowered |= report_compare(rows, args.compare[0], args.compare[1],
                                       args.allow_underpowered, args.by_cell)
    if args.anova:
        underpowered |= report_anova(rows, args.anova, args.allow_underpowered)
    report_integrity(rows)

    print("\n" + "=" * 92)
    if args.allow_underpowered:
        print("RESULT: UNDERPOWERED. n < 30 in at least one cell. Exit 2.")
        print("=" * 92)
        return 2
    if underpowered:
        print(f"RESULT: *** UNDERPOWERED *** at least one (model x case) cell has "
              f"n < {MIN_N}.")
        if tested:
            print("        Comparisons were SUPPRESSED. Re-run with more "
                  "replicates, or pass --allow-underpowered to see them clearly "
                  "labelled.")
        else:
            print("        No difference-of-means or ANOVA was requested, and none "
                  "would be reportable from this data.")
        print("        Nothing in this report may be quoted as evidence of a "
              "difference between builds or models. Exit 2.")
        print("=" * 92)
        return 2
    if not tested:
        print(f"RESULT: descriptive only — no comparison was requested. All cells "
              f"meet n >= {MIN_N}.")
        print("=" * 92)
        return 0
    print(f"RESULT: all reported comparisons met n >= {MIN_N}.")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
