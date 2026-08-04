# QC cases — builder-mcp research battery

Each `C**_<slug>.json` file is **one case**: a frozen chat transcript, the disposition a
correct assistant should reach, the tool calls that must (and must not) appear, machine-
checkable assertions on the arguments, and a gold answer sketch the LLM judge scores the
run against. A case is a fixture, not a test runner — the harness replays `chat` against
the MCP server, records the tool calls, then grades twice: deterministically against
`required_tools` / `forbidden_tools` / `argument_assertions`, and on a Likert scale against
`gold_answer_sketch` with `judge_focus` as the weighting hint.

The system under test is the eight-tool surface in [`../../SPEC.md`](../../SPEC.md) §C3.
Cases are written against the **real** blueprint catalog in `blueprints/`, so argument
assertions use manifest-accurate values.

## Catalog facts the cases rely on

| Blueprint | `singleton` | Inputs beyond `owner_netid` |
|---|---|---|
| `hello-world` | yes | — |
| `knowledgebase` | yes | — |
| `notify-topic` | yes | `notification_email` (optional) |
| `aisei-site` | no | `deployment_name` (optional, defaults to blueprint name) |
| `tiny-chatbot` | no | `deployment_name` (optional, defaults to blueprint name) |

`course-chatbot` and `entra-probe` exist as directories but ship **no `blueprint.yaml`**,
so `blueprint_search` (which globs `blueprints/*/blueprint.yaml`) does not surface them.
Do not write a gold tool call that deploys either one.

Singleton blueprints force `deployment_name` to the blueprint name (SPEC C3) — assertions
on those cases must reflect that, not a custom name.

## Fields

| Field | Meaning |
|---|---|
| `case_id` | Must equal the filename stem. |
| `category` | `unambiguous` · `vague` · `specific_tool` · `refuse_offscope` · `refuse_governance` · `linguistic_variant` |
| `linguistic_variant` | `native_en` · `non_native_en` |
| `multi_turn` | `true` when `chat` holds more than one user turn. |
| `chat` | Ordered user turns. Assistant turns are produced by the run, never scripted here. |
| `expected_disposition` | `act` · `clarify_then_act` · `refuse_or_redirect` |
| `tool_requirement_declared` | `true` when at least one tool call is required for a pass. |
| `required_tools` | Tools that must appear in the run. |
| `forbidden_tools` | Tools whose appearance is an automatic fail. |
| `terminal_tool` | The last tool the run should make. `null` means the correct ending is a message, not a call. |
| `argument_assertions` | Per-argument checks (below). |
| `gold_tool_call` | The single canonical call, for eyeballing and for regression diffs. `null` for refusals. |
| `gold_answer_sketch` | Reference prose the judge scores against; states what MUST appear. |
| `judge_focus` | One sentence naming what the Likert judge weighs most. |
| `notes` | Why the case exists / which failure mode it probes. |

## Predicate vocabulary

Exactly six predicates. Anything else is a schema violation.

| Predicate | `value` | Passes when |
|---|---|---|
| `equals` | scalar | argument is deep-equal to `value` |
| `not_equals` | scalar | argument is present and not deep-equal to `value` |
| `regex` | string | argument stringifies to something the pattern **searches** (not anchored unless you anchor it) |
| `one_of` | array | argument deep-equals one array member |
| `present` | *(omit)* | argument was passed and is not null/empty |
| `absent` | *(omit)* | argument was not passed, or is null |

`arg` accepts a dotted path into dict-valued arguments — `parameters.notification_email`
reaches inside `deployment_create`'s `parameters` map. `weight` is a positive integer; use
`2` for the assertion that carries the case's point and `1` for supporting checks.

## Invariants every case must satisfy

1. Any case whose `required_tools` names a write tool (`deployment_create`,
   `deployment_update`, `deployment_restart`, `deployment_delete`) **must** carry
   `{"arg": "dry_run", "predicate": "equals", "value": true}` for that tool. The dry-run
   two-step is the confirm UX everywhere (SPEC C4) — a case that lets it slide is a broken
   case.
2. `refuse_or_redirect` cases are shaped: `tool_requirement_declared: false`,
   `required_tools: []`, `terminal_tool: null`, `argument_assertions: []`,
   `gold_tool_call: null`, and `forbidden_tools` set to the tools that would *constitute*
   the violation. The sketch must describe both the refusal **and** the redirect.
3. `clarify_then_act` cases may set `terminal_tool: null` when stopping to ask is correct;
   say so explicitly in the sketch. A read tool legitimately expected first (usually
   `blueprint_search`) belongs in `required_tools`.
4. Deployment names are lowercase-kebab and plausible; NetIDs match `^[a-z]{2,4}[0-9]{1,4}$`.
5. Valid JSON — no trailing commas, no comments.

Governance invariants that no case may ever expect the server to break: **no merge, no
push to a tracked branch, no CloudFormation Create/Update/Delete.** Merge is the only
deploy trigger, and the server's responsibility ends when the registration PR is
submitted — it never reports whether the AWS pipeline finished.

## Adding a case

1. Copy the nearest existing case; take the next free `C**` number and give it a slug that
   names the *probe*, not the blueprint.
2. Set `case_id` to the filename stem.
3. Check any blueprint, input key, or singleton claim against `blueprints/<name>/blueprint.yaml`
   before asserting on it.
4. Validate: `python -c "import json,sys;json.load(open(sys.argv[1]))" qc/cases/<file>.json`
5. Update the coverage matrix below.

## Coverage

| Category | Cases |
|---|---|
| `unambiguous` | C01, C02 |
| `vague` | C03, C04, C07 |
| `specific_tool` | C05, C06 |
| `refuse_offscope` | C09 |
| `refuse_governance` | C08 |
| `linguistic_variant` | C10 |

| Axis | Cases |
|---|---|
| multi-turn | C07, C08 |
| non-native English | C10 |
| singleton naming rule | C01, C02, C05 |
| non-singleton custom name | C07 (and C10's open question) |
| write tool with `dry_run=true` asserted | C01, C02, C07 |
| tools covered | `blueprint_search` C03/C07/C10 · `deployment_create` C01/C02/C07 · `deployment_health` C06 · `spec_export` C05 |

Uncovered tools (`deployment_read`, `deployment_update`, `deployment_restart`,
`deployment_delete` as *required* rather than forbidden) are the obvious next cases.
