# Business Rules — FR-9 / FR-10 increment

**Stage**: CONSTRUCTION → Functional Design (FR-9/FR-10)
**Date**: 2026-08-07
**Components**: C-10 cost collector, C-11 telemetry collector, C-12 money (pure), C-13 telemetry
(pure), C-14 catalog.
**Convention**: continues U-02's rule-code style (CR/SR/AR/ER/OR/DR) with three new families —
`COST-*`, `TEL-*`, `CAT-*`. Every rule cites the clause or story criterion it discharges.

---

## COST — cost collection and money arithmetic

| # | Rule | Source |
|---|---|---|
| **COST-01** | Money is parsed from Cost Explorer's decimal **string** straight to `Decimal`. A `float` MUST never appear on a money path — parsing, arithmetic, aggregation, or serialization. | A4/design; FR-10 generally |
| **COST-02** | A tag group whose key has an **empty value component** (`"cornell:blueprint$"`) is the **unattributed** bucket. It MUST NOT be rendered as a tag value and MUST NOT be counted as an attributed group. | FR-10.3.6, US-17, A3.3 |
| **COST-03** | If the unattributed bucket is the whole period's spend, the breakdown is **attribution-unavailable**, not a one-group breakdown. | US-17, FR-10.5 |
| **COST-04** | The "today" figure is labelled with the **last finalized day** the upstream actually covered, never the wall-clock date. | US-16, FR-10.2.1, FR-10.5.3 |
| **COST-05** | A run MUST make **at most `max_ce_calls`** requests (config, default small). Exceeding it is a failure, not a truncation — a silent truncation would under-report spend, and under-reporting cost is the one error this dashboard exists to prevent. | NFR-T4/T8, FR-10.4.2 |
| **COST-06** | The count of CE calls made MUST be emitted as a metric on every run, success or failure. | NFR-T8, US-25 |
| **COST-07** | **Any** CE call failing fails the whole run: nothing is written, the previous `cost/current.json` survives, the next day retries. | services.md Flow 4; SECURITY-15; A-4 |
| **COST-08** | Per-model cost comes from `USAGE_TYPE` groups matching `<REGION>-<Model>-{input,output}-tokens`. An unrecognized usage type is carried as **other**, never dropped and never guessed into a model. | A3.4, FR-10.8 |
| **COST-09** | A model with token usage but **no configured rate** is reported as *rate missing*. It MUST NOT be priced at zero, and MUST NOT be omitted from the list. | FR-10.6.6, US-18 |
| **COST-10** | An estimate is tagged as an estimate in the data, not only in the UI. The distinction survives serialization so a JSON consumer cannot lose it. | NFR-T1, US-18, FR-3 (JSON parity) |
| **COST-11** | Estimated model cost and billed platform cost MUST NOT be summed into a single unqualified total anywhere — collector, API, or UI. | NFR-T1, US-18 |
| **COST-12** | `cost_per_task` with zero completed tasks returns an explicit **no-tasks** result. Never a division, never zero, never `null` conflated with zero. | FR-10.7.2, US-19 |
| **COST-13** | Infrastructure cost MUST NOT be split per agent. Only estimated model cost may be. | FR-10.3.3, US-23 |
| **COST-14** | The rate table is read from configuration at read time. A missing or malformed table yields *rate missing* for every model — never a fallback rate, and never zero. | NFR-T2, FR-10.6.4 |

### Why COST-05 is a failure rather than a cap
Truncating at a call budget would produce a **smaller** cost figure that looks valid. Every other bound
in this blueprint behaves the same way for the same reason — CR-01 refuses to truncate pagination
because *"silently stopping at page 1 under-reports inventory while looking successful."* Under-reported
spend is the cost-domain equivalent, and worse, because someone may act on it financially.

---

## TEL — telemetry collection and derivation

| # | Rule | Source |
|---|---|---|
| **TEL-01** | `agent_id` defaults to `deployment_id` when absent. Applied once, at key construction, so no reader can forget it. | T8, FR-9.3.2, US-23 |
| **TEL-02** | The AWS metric allowlist is a **module-level constant**. Only `ModelId` dimension **values** are discovered at runtime; which metrics to read is never discovered. | NFR-T5, FR-9.5.2, A4.2 |
| **TEL-03** | `Cornell/Blueprints/*` counters are read **only** if the baked catalog declares them. An undeclared counter present in CloudWatch is ignored, not rendered. | FR-9.5.2, US-24 |
| **TEL-04** | Every counter carries exactly one state: `OK`, `NO_DATA_YET`, `NOT_INSTRUMENTED`, `CANNOT_READ`. Collapsing any two is a defect. | NFR-T7, FR-9.7.3, US-20 |
| **TEL-05** | The AWS half and the declared half are **independent**. One failing MUST NOT prevent the other being written. | services.md Flow 5 |
| **TEL-06** | Rates are derived from a numerator **and** a denominator counter, both retained in the output. A pre-computed ratio MUST NOT be stored — it cannot be re-aggregated across agents or windows. | FR-9.6, US-21.3 |
| **TEL-07** | Per-agent counters within a deployment MUST sum to the deployment total. | US-23.3 |
| **TEL-08** | Two applications' `prompt success rate` MUST NOT be aggregated into one figure; each carries its own declared definition. | US-22.2, US-22.3 |
| **TEL-09** | A dimension value MUST NOT be a tag value, ARN, NetID, or end-user identifier, and MUST be low-cardinality. Enforced by the API shape carrying no parameter for one. | NFR-T3, FR-9.3.4, CR-04 |
| **TEL-10** | The metric count requested per run MUST be bounded — the allowlist × discovered models is a product, not a constant. | NFR-T8 |

### Why TEL-05 differs from COST-07, deliberately
Same component shape, opposite failure policy, because the upstreams differ. Cost Explorer is
**expensive per call and daily**, so a partial write is both avoidable and dangerous → fail whole.
CloudWatch is **cheap and continuous**, and the two halves have genuinely different availability (AWS
metrics exist today; declared counters do not exist at all until a blueprint opts in) → so failing the
run because an uninstrumented namespace returned nothing would erase real AWS data. Recorded here
because a reviewer seeing two collectors with different policies will otherwise read it as an
inconsistency.

---

## CAT — the declared-counter catalog

| # | Rule | Source |
|---|---|---|
| **CAT-01** | A blueprint with no `telemetry:` block is `emits: false`. Absence is a valid, first-class declaration — not an error and not unknown. | FR-9.4.2 |
| **CAT-02** | A **malformed** `telemetry:` block fails the **build**. It must not degrade to `emits: false`, which would silently drop a blueprint that intended to emit. | FR-9.4, A4.2 |
| **CAT-03** | A declared counter MUST carry `name`, `unit`, and `description`; the UI renders from those and never from blueprint-specific code. | FR-9.4.3 |
| **CAT-04** | The catalog is produced at build time and read at runtime. The runtime parser MUST be pure and MUST NOT reach the network or the filesystem outside its input. | A4.2, U-01 boundary |
| **CAT-05** | A blueprint absent from the catalog entirely is `NOT_INSTRUMENTED`, distinct from declared-with-no-data. | TEL-04, NFR-T7 |

---

## Rules that are prohibitions, verified by absence

Recorded so their absence is deliberate rather than an oversight, in the same way FR-5.4's
no-VPC prohibition was:

- **No per-user dimension or per-user cost path exists** (FR-10.9). There is no parameter, field, or
  dimension to carry one, which is the enforcement.
- **No budget or budget-remaining figure exists** (T4).
- **No department attribution exists** (T2).
- **No `float` on any money path** (COST-01) — checkable by grep in Build and Test.
- **No emitter is added to any blueprint** (T6, FR-9.7.1).

---

## Traceability check (plan step F3)

Every rule above cites a clause or criterion. In the other direction, each FR-9/FR-10 clause with
*business logic* (as opposed to infrastructure) has at least one rule: FR-9.3 → TEL-01/09; FR-9.4 →
CAT-01..05; FR-9.5 → TEL-02/03; FR-9.6 → TEL-06; FR-9.7 → TEL-04; FR-10.2 → COST-04; FR-10.3 →
COST-02/03/13; FR-10.4 → COST-05/06; FR-10.5 → COST-03/04; FR-10.6 → COST-09/10/11/14; FR-10.7 →
COST-12; FR-10.8 → COST-08.

FR-9.1, FR-9.2 and FR-10.1 carry **no rule here by design**: the first two describe the contract and
the *emitting* side (another blueprint's code, per T6), and FR-10.1 is a source choice, not a rule.
