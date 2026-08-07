# Business Logic Model — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Functional Design (artifact 3 of 4)
**Date**: 2026-08-03
**Rules**: `business-rules.md` (CR/SR/AR/ER/OR/DR) · **Entities**: `domain-entities.md`

---

## Totality — which functions can fail

U-01's table said what raises. U-02's is different in kind: almost everything here does I/O, so almost
everything can fail. The interesting rows are the ones that **must not**.

| Function | Total? | Fails on |
|---|---|---|
| `collector.handler` | Partial | any `CollectorFailure` — and that is correct; a failed invocation is the alarm signal |
| `collect_all_resources` | Partial | page limit, throttle exhaustion, upstream error |
| `write_snapshot` | Partial | S3 error |
| `api.handler` | **Total** | never — every path returns a response |
| `route` | **Total** | unmatched → 404 |
| `load_current_snapshot` | **Total** | classifies into three states instead of raising |
| `respond` | **Total** | pure shaping |
| `health` | **Total** | static |

**`api.handler` being total is the design decision here.** Anything that escapes becomes an
unstructured 500 from API Gateway, which loses AR-03's body `status` — and C-09's alarms and the UI both
read that field. A 500 is the one outcome the six-state table cannot express.

**`load_current_snapshot` being total is what makes US-06 possible.** A raising loader forces the caller
into `except`, which is exactly where `ABSENT` and `UNREADABLE` get collapsed into one "it broke".

---

## C-01 — collection

```
handler(event, context):
    started = clock()
    outcome = collect_all_resources(tagging_client, PAGE_LIMIT)   # CR-01, CR-02
    snapshot = build_snapshot(outcome.result, collected_at=clock())  # U-01
    write_snapshot(s3, bucket, key, serialize_snapshot(snapshot))  # CR-05, U-01
    log_skipped(outcome.result)                                    # CR-04
    emit_metrics(outcome, clock() - started)                       # CR-06
    # no return value: success IS the written object
```

```
collect_all_resources(client, page_limit):
    raw, pages, token = [], 0, None
    loop:
        pages += 1
        if pages > page_limit:
            raise CollectorFailure.PAGE_LIMIT_EXCEEDED      # CR-01 — never truncate
        page = client.get_resources(token)                  # CR-02 timeouts + backoff
        raw.extend(page.items)
        token = page.next_token
        if not token: break
    return CollectionOutcome(normalize_all(raw), pages, ...)  # CR-03 — U-01 does the parsing
```

**The clock is read exactly twice**, both in `handler`, and passed down. U-01 forbids itself a clock; C-01
is where "now" enters the system, and keeping it in one function means the snapshot's `collected_at` and
the duration metric cannot disagree.

**`normalize_all` is total**, so a malformed item cannot reach this function as an exception. The only
things that fail a collection are upstream problems and the page limit — never the data's content.

```
log_skipped(result):                                        # CR-04, obligation 3
    for each skipped item:
        log(json: level=warning, reason=<code>, arn=<arn>)
        # ARN yes. Tag values NEVER — cornell:owner is a NetID.
```

### Failure path

On any `CollectorFailure`: log structured with the reason code, emit the failure metric, **raise**. The
invocation fails, OR-01 alarms, and **the previous snapshot is left untouched** — so the dashboard
degrades to *labelled stale* rather than *broken*. Preferring visible staleness to invisible
incompleteness is the central resiliency choice of the whole design.

---

## C-03 — request handling

```
handler(event, context):
    handler_fn = route(method, path)                 # AR-01
    if not handler_fn: return respond(404, "error", {})   # no S3 read
    if path == "/api/health": return health()        # AR-08 — no S3 read
    outcome = load_current_snapshot(s3, bucket, key)  # AR-02
    return shape(outcome, handler_fn, clock())
```

```
load_current_snapshot(s3, bucket, key) -> LoadOutcome:      # AR-02, total
    try: body = s3.get_object(...)
    except NoSuchKey:  return LoadOutcome(ABSENT, None)
    except ClientError: return LoadOutcome(UNREADABLE, None)
    try: return LoadOutcome(PRESENT, deserialize_snapshot(body))
    except (IncompatibleSchema, InvalidSnapshot):
                        return LoadOutcome(UNREADABLE, None)
```

`IncompatibleSchema` and `InvalidSnapshot` are caught **by type**, which is why U-01's error hierarchy
exists rather than one type with a category attribute (U-01 PAT-7). A bare `except CoreError` would work
today and stop distinguishing the moment a fifth error type appears.

```
shape(outcome, handler_fn, now) -> ApiResponse:               # AR-03 — the six states
    if outcome.state is ABSENT:      return respond(200, "no_data", {})
    if outcome.state is UNREADABLE:  return respond(503, "error", {})

    freshness = evaluate_freshness(outcome.snapshot.collected_at, now, STALE_AFTER)  # U-01
    if freshness is INVALID:         return respond(503, "error", {})   # obligation 1

    body_status = "stale" if freshness is STALE else "ok"
    return respond(200, body_status, {
        "collected_at": ..., "freshness": freshness,
        "counts": counts_of(outcome.snapshot),     # AR-05 — obligation 2
        "data": handler_fn(outcome.snapshot),      # AR-04 — U-01 derives
    })
```

**Order matters.** `INVALID` is checked before the stale/ok split, for the same reason U-01 checks it
first inside `evaluate_freshness`: a future timestamp gives a negative age, which is trivially under any
threshold and would otherwise read as `ok`.

**`counts_of` is unconditional**, on every data response. Slimming it away would end the skip-and-count
guarantee at a boundary nobody sees.

`handler_fn` is one of: identity (inventory), `group_by_tag` (with the validated key),
`classify_tag_gaps`, or a status summary. **All four are U-01's** — C-03 chooses which and passes the
snapshot; it never iterates records itself.

---

## Where the three counts travel — obligation 2, end to end

```
Tagging API
  → normalize_all       raw_returned / skipped_count / duplicates_removed  (U-01)
  → build_snapshot      carried onto the Snapshot, P8 asserted             (U-01)
  → serialize_snapshot  written into the stored JSON                       (U-01)
  → deserialize         read back, P8 re-asserted                          (U-01)
  → counts_of           into every API response envelope                   (AR-05)
  → UI status strip     rendered on every view                             (frontend-components.md)
```

Written as a chain because the obligation is only discharged if **every** hop carries it. Six hops exist
already in U-01 and are property-tested; the last two are U-02's, and they are the two that have never
been built.

---

## Testing at this level — honestly not properties

U-01 has ten property-based tests because it is pure. **U-02 is mostly I/O, and pretending otherwise
would produce property tests over mocks — which test the mocks.** What is genuinely worth testing here:

| What | Kind | Why |
|---|---|---|
| The six-state mapping, all six rows | **Example-based, table-driven** | The highest-value tests in this unit. Each row is a distinct user-visible outcome, and rows 3/4 (`ok` with zero resources vs. `no_data`) are the pair US-06 exists for. |
| `load_current_snapshot` classification | Example-based with stubbed S3 errors | Three states from three distinct failures |
| `route` | **Property**: no input outside the table reaches a handler | Genuinely a property — a closed allowlist over arbitrary strings |
| `counts_of` present in every non-health response | **Property** over response shapes | Cheap, and guards obligation 2 against slimming |
| Pagination: termination, page-limit breach, one-page, empty | Example-based with a stubbed pager | The breach must raise, not truncate |
| `log_skipped` never emits a tag value | **Example-based, asserting absence** | The privacy rule; the analogue of U-01's no-leak test |
| CSP contains no `unsafe-inline`/`unsafe-eval` | Example-based over the built template | Cheap, and catches the bundler-driven loosening |
| Cache policy: `/api/*` no-cache, site cached | Example-based over the template | ER-03 — silent when wrong, and the failure US-05 prevents |

The last two are template assertions rather than code tests, which is unusual — recorded because they
guard two of the design's most-emphasized invariants and nothing else would catch them before deploy.

**Not proposed**: property tests over the collector or the API with mocked AWS. RESILIENCY-14 was
satisfied for U-01 by real property testing; for U-02 the honest equivalent is the table-driven state
mapping plus deployed smoke checks, and that should be stated rather than dressed up.

---

## Carried to Infrastructure Design

| Item | Why it is not settled here |
|---|---|
| **§6.4 site-sync ordering** | Pipeline topology. `Build` precedes `BlueprintDeploy`, so the site bucket does not exist when `s3 sync` runs. Likely: emit the bundle as a CodePipeline artifact and sync at `RunOrder: 2` inside `BlueprintDeploy`. |
| **WAF IPv6** | IPSets are per-address-family; an IPv4-only allowlist silently locks out IPv6-only clients (Part A2 Interaction 3) |
| **notify-topic ARN mechanism** | Its outputs carry no `Export:`, so parameter or naming-convention (Part A2 Interaction 7) |
| Two arm64 images, `Dockerfile` targets, digest pinning | Container mechanics |
| The two templates' resource-by-resource shape | Infrastructure Design's whole job |
| Lambda memory, timeout, reserved concurrency | Sizing |
