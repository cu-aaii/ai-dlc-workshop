# Business Logic Model — FR-9 / FR-10 increment

**Stage**: CONSTRUCTION → Functional Design (FR-9/FR-10)
**Date**: 2026-08-07
**Purpose**: the algorithms behind the `COST-*` / `TEL-*` / `CAT-*` rules, and the property targets
they create. Pseudocode is indicative; signatures are in
`inception/application-design/component-methods.md`.

---

## 1. Cost collection (C-10)

```
run(config, ce, s3, clock):
    now = clock()                        # read once
    calls = 0
    try:
        windows  = fetch_windows(ce, now)          # day / MTD / YTD      -> calls += 3
        groups   = fetch_groupings(ce, windows.mtd) # SERVICE, USAGE_TYPE, 2x TAG -> calls += 4
    except (ClientError, BotoCoreError) as e:
        emit(cost_collect_failure=1, ce_calls=calls); log(reason); raise    # COST-07
    if calls > config.max_ce_calls:       # COST-05 -- failure, never truncation
        raise CostFailure(CALL_BUDGET_EXCEEDED)

    split      = split_attribution(groups.by_tag)   # COST-02/03
    per_model  = classify_usage_types(groups.by_usage_type)  # COST-08, "other" bucket kept
    section    = CostSection(collected_at=now, covered_through=windows.finalized_through, ...)
    s3.put_object(key=config.cost_key, body=serialize(section))   # ONE write, complete-or-fail
    emit(ce_calls=calls, unattributed_fraction=split.fraction, outcome="success")  # COST-06
```

**`covered_through` is not `now`.** It is the last day the upstream reports as finalized, and it is a
*separate field* from `collected_at` — one says when we asked, the other says what the answer covers.
COST-04 exists because collapsing them is the mistake US-16 guards against.

## 2. Telemetry collection (C-11)

```
run(config, cw, s3, catalog, clock):
    now = clock()
    window = (now - config.lookback, now)
    aws_half = declared_half = None
    try:
        models   = discover_models(cw)               # ModelId VALUES only  -- TEL-02
        aws_half = fetch(cw, AWS_ALLOWLIST, models, window)   # module constant
    except Exception: aws_half = CANNOT_READ         # TEL-05 -- independent
    try:
        declared_half = fetch(cw, catalog.counters(), window) # TEL-03
    except Exception: declared_half = CANNOT_READ

    if aws_half is CANNOT_READ and declared_half is CANNOT_READ:
        raise TelemetryFailure(BOTH_HALVES_UNREADABLE)   # nothing to write
    section = TelemetrySection(collected_at=now, window=window,
                               counters=[with state per TEL-04])
    s3.put_object(key=config.telemetry_key, body=serialize(section))
```

**The bounded-metric rule (TEL-10)** applies at `fetch`: `len(AWS_ALLOWLIST) × len(models)` plus the
declared count must be under `config.max_metrics`, else fail — because the model list is discovered and
therefore unbounded in principle.

## 3. Money arithmetic (C-12, pure)

```
estimate_model_cost(usage, rates):
    out, missing = {}, set()
    for model, tokens in usage.items():
        rate = rates.get(model)
        if rate is None: missing.add(model); continue          # COST-09 -- not zero
        out[model] = (Decimal(tokens.input)  / rate.per_unit) * rate.input_price \
                   + (Decimal(tokens.output) / rate.per_unit) * rate.output_price
    return CostEstimate(per_model=out, missing_rates=frozenset(missing), is_estimate=True)
```

`is_estimate=True` is carried **in the record** (COST-10), so a JSON consumer cannot lose the
distinction the UI shows. All arithmetic is `Decimal` (COST-01); `per_unit` is explicit (rates are
quoted per 1,000 or per 1,000,000 tokens depending on the model, and hardcoding either is how a
1000× error enters).

```
is_unattributed(group_key):   return group_key.endswith("$")      # COST-02
split_attribution(groups):
    att   = [g for g in groups if not is_unattributed(g.key)]
    unatt = [g for g in groups if     is_unattributed(g.key)]
    return AttributionSplit(attributed=att, unattributed=sum(unatt),
                            fraction=sum(unatt)/total if total else None)
```

`is_unattributed` is a **one-line pure predicate on purpose**: it is the entire defence against A3.3's
trap, so it must be trivially reviewable and property-testable without AWS.

## 4. Rate derivation (C-13, pure)

```
derive_rate(numerator, denominator):
    if denominator.value == 0:
        return RateResult(rate=None, state=NO_DATA_YET, num=0, den=0)   # never 0/0, never 0%
    return RateResult(rate=numerator.value / denominator.value,
                      num=numerator.value, den=denominator.value)      # TEL-06 -- both retained
```

Returning `rate=None` with a state, rather than `0.0`, is the difference between *"no requests, so no
error rate"* and *"requests all succeeded"* — TEL-04's distinction applied to arithmetic.

---

## 5. Property targets

The reason C-12/C-13 are in U-01 (Q4 = A): these are checkable without AWS.

### Money (C-12) — the highest-value properties in this increment
| Property | Statement |
|---|---|
| **Zero** | zero tokens ⇒ zero cost, for every rate table |
| **Monotone** | more tokens ⇒ never less cost |
| **Additive** | `estimate(a) + estimate(b) == estimate(a merged with b)` per model — the property that makes per-agent and per-window totals trustworthy |
| **Missing-rate total** | a model in `missing_rates` contributes **nothing** to any total, and appears in no per-model figure (COST-09) |
| **No float** | every monetary value in the output is `Decimal` (type-level, checkable by assertion) |
| **Estimate flag survives** | `deserialize(serialize(e)).is_estimate == e.is_estimate` (COST-10 round-trip) |

### Unattributed predicate (C-12)
| Property | Statement |
|---|---|
| **Partition** | attributed and unattributed groups partition the input — none dropped, none double-counted |
| **Sum preserved** | attributed total + unattributed total == input total (the accounting identity, as U-01 already does for resource counts) |
| **Empty-value detection** | for any key `k`, `is_unattributed(k + "$") is True` and `is_unattributed(k + "$" + v) is False` for non-empty `v` |

### Telemetry (C-13)
| Property | Statement |
|---|---|
| **Agent default** | `counter_key(d, None, m).agent_id == d` for all `d` (TEL-01) |
| **Agent sum** | per-agent totals sum to the deployment total (TEL-07 / US-23.3) |
| **Rate re-aggregation** | deriving a rate from summed numerators and denominators equals the correctly weighted combination — the property that justifies TEL-06's refusal to store ratios |
| **State totality** | every counter maps to exactly one of the four states; no input yields two or none |

### Catalog (C-14)
| Property | Statement |
|---|---|
| **Absence ⇒ false** | a manifest with no `telemetry:` block yields `emits() is False` (CAT-01) |
| **Round-trip** | `parse_catalog(serialize(c)) == c` |

**Deliberately not property-tested**: the collectors (C-10/C-11). Consistent with
U-02's `business-logic-model.md`, which chose table-driven tests over property tests against mocks —
a property test over a stubbed AWS client tests the stub. Their rules are covered by example-based
tests instead.

---

## 6. Failure vocabulary

Closed enums, matching U-01's `SkipReason` / U-02's `CollectorReason` precedent rather than free text:

- `CostReason`: `CALL_BUDGET_EXCEEDED`, `UPSTREAM_UNAVAILABLE`, `UPSTREAM_THROTTLED`,
  `ACCESS_DENIED` (the linked-account/payer case of A3.3 — distinct, because it is *permanent* and a
  retry tomorrow will not fix it)
- `TelemetryReason`: `BOTH_HALVES_UNREADABLE`, `METRIC_BUDGET_EXCEEDED`
- `TelemetryState`: `OK`, `NO_DATA_YET`, `NOT_INSTRUMENTED`, `CANNOT_READ`

`ACCESS_DENIED` being its own reason matters operationally: an alarm on it should not page anyone to
"retry", it should tell them **the Organization payer must act** (A3.3). Every other reason is
retry-shaped; that one is not.
