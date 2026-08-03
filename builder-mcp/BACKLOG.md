# builder-mcp — Task Backlog

Forward work agreed by the mob but deliberately not built yet. One line of context each;
link the contract (SPEC.md) section it touches. Items are added in the PR that agrees
them.

## Demo

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

- Cap `deployment_restart` at 3 restarts per deployment per window (window TBD by the mob);
  past the cap the tool refuses and directs the builder to open a PR / contact the platform
  team. Unbounded retries mask real failures and burn pipeline runs. Open design question:
  this needs restart-count state, which the stateless server (SPEC C4) does not keep. (SPEC C3)

## Platform (P1+, from the product proposal)

- GitHub App installation replaces the org PAT (SPEC C5, D3)
- Entra ID (NetID) replaces Cognito client-credentials as inbound auth (SPEC C5)
- AI Gateway registration of the AgentCore endpoint
- Upgrade-bot: version-bump PRs to deployment repos when a blueprint releases (SPEC C2)
