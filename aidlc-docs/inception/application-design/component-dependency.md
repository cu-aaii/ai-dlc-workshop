# Component Dependencies — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 4 of 5)
**Date**: 2026-08-03

---

## Dependency matrix

Rows depend on columns. `R` = reads, `W` = writes, `C` = calls, `S` = serves through.

| ↓ depends on → | C-01 | C-02 | C-03 | C-04 | C-05 | C-06 | C-07 | Tagging API |
|---|---|---|---|---|---|---|---|---|
| **C-01** Collector | — | W | — | C | — | — | — | R |
| **C-02** Snapshot Store | — | — | — | — | — | — | — | — |
| **C-03** Read API | — | R | — | C | C | — | — | — |
| **C-04** Inventory Model | — | — | — | — | — | — | — | — |
| **C-05** Aggregation Core | — | — | — | C | — | — | — | — |
| **C-06** Web UI | — | — | — | — | — | — | S | — |
| **C-07** Edge | — | — | S | — | — | S | — | — |
| **C-08** Deployment Marker | — | — | — | — | — | — | — | — |
| **C-09** Observability | — | — | — | — | — | — | — | — |

**Three things this matrix is meant to show:**

1. **C-04's row is empty.** It depends on nothing. C-05's row contains only C-04. Neither touches AWS.
   That is §4.5's requirement made structural, and it is what lets PBT-01..10 attach to real units
   rather than to mocked-out AWS calls.
2. **C-01 and C-03 never reference each other.** No column entry links them. Their only relationship
   is that both name C-02 — the invariant from `services.md` read off the matrix.
3. **No cycles.** The graph is a DAG rooted at C-07 and terminating at C-04. Nothing depends on C-02
   except the two functions, and C-02 depends on nothing, so the storage seam cannot introduce one.

C-08 and C-09 have empty rows because they are deployment-time and observation-time artifacts. They
are not called by anything at runtime.

---

## Runtime data flow

```mermaid
flowchart TB
    subgraph collect["S-01 Collection Service (scheduled)"]
        direction TB
        SCHED["EventBridge Schedule<br/>interval = stack parameter"]
        COLL["C-01 Tag Inventory Collector<br/>Lambda, container image"]
        TAG["Resource Groups Tagging API<br/>upstream, not controlled here"]
        SCHED --> COLL
        COLL -->|"paginate to exhaustion"| TAG
    end

    STORE[("C-02 Snapshot Store<br/>one versioned encrypted<br/>JSON object in S3")]

    subgraph query["S-02 Query Service (on demand)"]
        direction TB
        EDGE["C-07 Edge<br/>CloudFront + WAF<br/>default action BLOCK"]
        UI["C-06 Web UI<br/>React + Vite bundle in S3"]
        APIGW["API Gateway HTTP API<br/>throttled"]
        API["C-03 Inventory Read API<br/>Lambda, container image"]
        EDGE -->|"default path<br/>CACHED"| UI
        EDGE -->|"/api/*<br/>NO-CACHE"| APIGW
        APIGW --> API
    end

    subgraph pure["Pure logic — no AWS, no clock, no network"]
        direction TB
        MODEL["C-04 Inventory Model<br/>normalize / serialize / round-trip"]
        AGG["C-05 Aggregation Core<br/>group / classify gaps / freshness"]
        AGG --> MODEL
    end

    VIEWER(["Viewer<br/>inside Cornell IP allowlist"])
    OBS["C-09 Observability Set<br/>alarms, metrics, logs"]

    VIEWER -->|"HTTPS only, TLS 1.2+"| EDGE
    COLL -->|"build + serialize"| MODEL
    COLL -->|"single PutObject<br/>complete or fail"| STORE
    STORE -->|"GetObject<br/>read-only"| API
    API -->|"derive views"| AGG
    COLL -.->|"metrics + logs"| OBS
    API -.->|"metrics + logs"| OBS
    STORE -.->|"staleness alarm"| OBS

    classDef service fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef storage fill:#FFF8E1,stroke:#F9A825,stroke-width:2px,color:#E65100
    classDef purelogic fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef edge fill:#FCE4EC,stroke:#C2185B,stroke-width:2px,color:#880E4F
    classDef external fill:#EEEEEE,stroke:#616161,stroke-width:2px,color:#212121
    classDef observ fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class SCHED,COLL,APIGW,API service
    class STORE storage
    class MODEL,AGG purelogic
    class EDGE,UI edge
    class TAG,VIEWER external
    class OBS observ
```

The one solid arrow crossing between the two service subgraphs is `STORE → API`, and the one entering
it is `COLL → STORE`. Everything else stays inside its own box. Dotted arrows are telemetry, which by
definition never carries a runtime dependency.

---

## Deployment-time dependencies

Distinct from runtime, and the ones most likely to be got wrong.

```mermaid
flowchart LR
    PR["Approved PR<br/>merged to main"]
    SRC["Source<br/>webhook"]
    PDEP["PipelineDeploy<br/>pipeline deploys itself"]
    BUILD["Build ← NEW<br/>container images +<br/>Vite build + s3 sync"]
    BDEP["BlueprintDeploy<br/>+ NEW dashboard action"]
    REG["pipeline/stacks.yml<br/>registry entry"]

    PR --> SRC --> PDEP --> BUILD --> BDEP
    REG -.->|"must match, or the stack<br/>deploys nothing silently"| BDEP

    classDef existing fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef new fill:#FFF3E0,stroke:#EF6C00,stroke-width:3px,color:#E65100
    classDef guard fill:#FFEBEE,stroke:#C62828,stroke-width:2px,color:#B71C1C

    class PR,SRC,PDEP existing
    class BUILD,BDEP new
    class REG guard
```

| Dependency | Direction | Consequence of getting it wrong |
|---|---|---|
| Build **before** BlueprintDeploy | strict | CloudFormation fails on a missing image tag — reads as a template bug, not a stage-order bug |
| Registry entry **matches** a BlueprintDeploy action | bidirectional | Green PR, all stages `Succeeded`, **no stack**. `validate_stacks.py` now catches both directions. |
| Stack name is `aidlc-<env>-<name>` | strict | Opaque authorization failure, not a naming complaint — `BuildPipelineRole` scopes to `stack/${Application}-${Environment}*` |
| Site bucket exists **before** `s3 sync` | strict | **Unresolved** — see `services.md`; deferred to Infrastructure Design rather than guessed |
| Every parameter passed explicitly | strict | Silent divergence between pipeline and by-hand deploys |

---

## Cross-cutting obligations, and which component owns each

The point of this table is that every one has exactly one owner. An obligation owned by "the design"
is an obligation nobody implements.

| Obligation | Owner | Requirement |
|---|---|---|
| Deny-by-default IP allowlist | C-07 | FR-5.1, SECURITY-07 |
| API path covered by the same ACL | C-07 | FR-5.2 |
| HTTPS only, TLS 1.2+ | C-07 | SECURITY-02 |
| Security response headers, strict CSP | C-07 (set) + C-06 (comply) | SECURITY-11, US-01 |
| **`/api/*` no-cache while site is cached** | C-07 | US-05, and the cost of Q4 = A |
| Encryption at rest | C-02 | SECURITY-01 |
| Least-privilege IAM, per function | C-01, C-03 | SECURITY-06 |
| No internals in error bodies | C-03 | FR-3.4, SECURITY-09 |
| Request validation | C-03 (closed allowlist) | SECURITY-05 |
| Rate limiting | API Gateway under C-03 | FR-3.5, SECURITY-12 |
| Four required tags on every resource | every template | `CLAUDE.md`, FR-1.4 |
| Access logging | C-07 | SECURITY-03, US-11 |
| Application logging | C-01, C-03 | SECURITY-04, US-12 |
| Alarms on the two silent failures | C-09 | US-13, RESILIENCY-07 |
| Bounded concurrency | C-01, C-03 | RESILIENCY-09 |
| Explicit timeouts, bounded retries | C-01, C-03 | RESILIENCY-10 |
| Complete-or-fail collection | C-01 | FR-1.1, US-02 |
| Server-side staleness judgement | C-05, surfaced by C-03 | US-05, Q8 = A |
| Round-trip and determinism properties | C-04 | PBT §4.2 |
| Grouping and gap properties | C-05 | PBT §4.2 |
| Supply-chain pinning, Python + container | C-01, C-03 images | SECURITY-10, US-09 |
| Supply-chain pinning, npm | C-06 lockfile | Q11 = B — **pinning only; no scan, no SBOM** |

The last row is the only obligation in this table that is narrower than the rule it cites. It is
recorded as such in `application-design.md` rather than presented as full compliance.
