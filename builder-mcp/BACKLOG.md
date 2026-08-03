# builder-mcp — Task Backlog

Forward work agreed by the mob but deliberately not built yet. One line of context each;
link the contract (SPEC.md) section it touches. Items are added in the PR that agrees
them.

## Demo

- **Restore Entra inbound auth after the testing phase.** The runtime currently deploys
  with `AuthMode=open` (DECISION-22): the Entra JWT authorizer is masked — not removed —
  and AgentCore falls back to its default IAM SigV4 inbound auth (there is no
  unauthenticated mode). To restore: flip `AuthMode` to `entra` and re-add the two Entra
  parameter overrides in `pipeline/pipeline.yml`, after the Entra pre-flight — exact
  checklist in `deploy/HANDOFF.md`, section "Testing phase: AuthMode=open". (SPEC C5)

- **Time-critical — the demo is 2026-08-04.** Make the process reliably showable two ways:
  (1) record a successful end-to-end run as a fallback, (2) drive the real server live from
  Claude Cowork. Live Cowork use depends on the deployed AgentCore endpoint plus an OAuth
  token (SPEC C5); if that is not ready by demo time, the recording is what gets shown.

## Catalog & search

- Blueprints move to a **private** repo: the target-state platform generates private
  per-deployment repos once the org moves off GitHub Free (see the workshop repo README),
  so `blueprint_search` must search a private catalog. `catalog.py` `_load_remote` can then
  no longer use unauthenticated GitHub API access — it needs the server-side credential
  (SPEC C5) and a configurable catalog repo (SPEC C7 env var).

- Integrate a **custom vector store as a tool call**, so the server can retrieve extra
  information while it builds. This adds a tool, so it is a SPEC C3 contract change. Open
  questions: what corpus it holds (blueprint docs? Cornell platform docs? past deployments?),
  and that a retrieval tool is a new outbound dependency for a read-mostly server (SPEC C5).

## Verification & performance

- **Speed check**: measure how long creating a new spec takes end to end. Needs an agreed
  start/stop boundary first — first builder utterance → PR open? No performance targets exist
  anywhere (the NFR Requirements stage was skipped), so this item produces the first latency
  number we have.

- **End-to-end reliability test**: can we actually launch a blueprint, reliably? The current
  22 tests cover pure logic; the GitHub and AWS edges are exercised only through dry-run
  paths. This is a real `deployment_create` → merge → pipeline → running stack run, repeated
  enough times to say something about reliability rather than "it worked once".

## Cost

- Cost-spec the minimum cost of **one** builder using builder-mcp to create and host a
  blueprint and serve one call. Quote it per stage, marking which parts are fixed and which
  scale, and with what (calls, storage, build minutes). Grounded estimates preferred, but
  guesswork rooted in reality beats nothing. Connects to the manifest `cost` block (SPEC C1:
  `baseline_monthly_usd` / `scales_with`), which today carries a per-blueprint figure only and
  has no notion of the platform's own overhead — AgentCore runtime, CodeBuild minutes, ECR
  storage.

## Operations & guardrails

- Cap `deployment_restart` at 3 restarts per deployment per window (window TBD by the mob)
  **and** time-box each restart at 30 minutes (mob 2026-08-03): a re-run that has not gone
  green in 30 minutes is treated as failed and counts against the cap. Past the cap the tool
  refuses and directs the builder to open a PR / contact the platform team. Unbounded retries
  mask real failures and burn pipeline runs. Open design questions: this needs restart-count
  state, which the stateless server (SPEC C4) does not keep, and the time-box enforcement
  mechanism is open — possibly `codepipeline:StopPipelineExecution` after timeout. (SPEC C3)

## UX

- Revisit the `dry_run` confirm UX (deprioritized by the mob 2026-08-03). `dry_run` stays in
  the code — it is how every mutating tool works — but refining it as a confirmation
  *experience* is not current work. Includes re-checking whether true MCP elicitation becomes
  possible if the transport constraints change (SPEC C4).

## Platform (P1+, from the product proposal)

- GitHub App installation replaces the org PAT (SPEC C5, D3)
- ~~Entra ID replaces Cognito client-credentials as inbound auth (SPEC C5)~~ **done
  2026-08-03** — pulled forward by platform-lead directive; see DECISION-20
- Per-user (NetID) identity via the Entra **authorization-code flow** replacing the shared
  client-credentials grant: client-credentials is app identity, not user identity, so
  object-level authorization (security F2) still needs the user-identity step (SPEC C5)
- AI Gateway registration of the AgentCore endpoint
- Upgrade-bot: version-bump PRs to deployment repos when a blueprint releases (SPEC C2)
- Strands agent pilot — parked by the mob 2026-08-03. The research concluded a rewrite is a
  category error; the coherent build is an agent *wrapping* the MCP tool surface (~2–4 days,
  needs an LLM at runtime). See `aidlc-docs/construction/strands-research.md`.
