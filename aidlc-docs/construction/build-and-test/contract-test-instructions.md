# Contract Test Instructions

**Date**: 2026-08-04. Applicable from U-02 (U-01's Build and Test recorded this becomes real once a
consumer of `dashboard.core` exists).

## The contract

`dashboard.core`'s `__all__` is the contract between U-01 and U-02 (`nfr-design/logical-components.md`
§4). U-02 may depend only on those names, and only via `from dashboard.core import …` — never
`dashboard.core.model` / `.aggregation` / `.errors`, whose internal layout is free to change.

## Run

```sh
cd blueprints/dashboard
# 1. No submodule imports bypass the public surface:
grep -rnE "from dashboard\.core\.(model|aggregation|errors)|import dashboard\.core\.(model|aggregation|errors)" \
  src/dashboard/collector src/dashboard/api src/dashboard/shared && echo "VIOLATION" || echo "clean"
# 2. Every name U-02 imports is in __all__:
grep -rhE "from dashboard\.core import" src/dashboard/collector src/dashboard/api
uv run python -c "import dashboard.core as c; print(sorted(c.__all__))"
```

## Result 2026-08-04

**Clean.** U-02 imports only `from dashboard.core import …`; the names used — `build_snapshot`,
`serialize_snapshot`, `deserialize_snapshot`, `normalize_all`, `NormalizationResult`, `Snapshot`,
`REQUIRED_TAGS`, `Freshness`, `evaluate_freshness`, `group_by_tag`, `classify_tag_gaps`,
`IncompatibleSchema`, `InvalidSnapshot` — are all in `__all__`. No submodule import.

## The other contract: the `/api/*` response envelope

C-03 produces the envelope the UI consumes (`{status, collected_at, freshness, counts, data}`). It is
enforced from both ends in code, not by a schema test: `shaping.py` builds it and `test_api_states.py`
asserts every field; the UI's `types.ts` `Envelope<T>` mirrors it and `tsc` fails a drift. A
consumer-driven schema test would add a third source of truth; the typed mirror + the state tests are
the control. A live contract test (UI fetch against a running API) is **deployed-only**.
