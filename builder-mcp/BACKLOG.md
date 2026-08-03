# builder-mcp — Task Backlog

Forward work agreed by the mob but deliberately not built yet. One line of context each;
link the contract (SPEC.md) section it touches. Items are added in the PR that agrees
them.

## Catalog & search

- Blueprints move to a **private** repo: the target-state platform generates private
  per-deployment repos once the org moves off GitHub Free (see the workshop repo README),
  so `blueprint_search` must search a private catalog. `catalog.py` `_load_remote` can then
  no longer use unauthenticated GitHub API access — it needs the server-side credential
  (SPEC C5) and a configurable catalog repo (SPEC C7 env var).

## Operations & guardrails

- Cap `restart_deployment` at 3 restarts per deployment per window (window TBD by the mob);
  past the cap the tool refuses and directs the builder to open a PR / contact the platform
  team. Unbounded retries mask real failures and burn pipeline runs. Open design question:
  this needs restart-count state, which the stateless server (SPEC C4) does not keep. (SPEC C3)

## Platform (P1+, from the product proposal)

- GitHub App installation replaces the org PAT (SPEC C5, D3)
- Entra ID (NetID) replaces Cognito client-credentials as inbound auth (SPEC C5)
- AI Gateway registration of the AgentCore endpoint
- Upgrade-bot: version-bump PRs to deployment repos when a blueprint releases (SPEC C2)
