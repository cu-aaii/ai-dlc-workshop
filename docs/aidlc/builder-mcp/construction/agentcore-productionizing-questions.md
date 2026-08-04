# AgentCore Hosting — Productionizing Questions

Decision confirmed: builder-mcp hosts on **Amazon Bedrock AgentCore**. These are the
productionizing choices that hosting forces. Same drill: fill in `[Answer]:` tags, ⭐ =
recommendation. P1–P3 block today's deploy; P4–P6 can land tomorrow morning.

## P1 — Topology: Runtime, Gateway, or both?

AgentCore *Runtime* hosts our container as a managed MCP server. AgentCore *Gateway* is a
separate front door that aggregates tools and handles inbound OAuth — closer to the "AI
Gateway registration" in the vision diagram.

- A) ⭐ **Runtime only today** — deploy the container, clients hit the Runtime MCP
  endpoint directly. Fewest moving parts before 5 PM.
- B) **Runtime + Gateway in front** — Gateway gives the catalog/auth surface the vision
  promises, but it's a second service to configure and debug today.
- C) Gateway with Lambda targets (rewrite each tool as a Lambda) — a different
  architecture, not a hosting choice. Not recommended.
- X) Other

[Answer]:

## P2 — Inbound authentication (who may call the Builder?)

AgentCore requires one of two inbound auth modes; "no auth" is not an option.

- A) **IAM SigV4** — zero new infrastructure, but callers need AWS credentials and a
  SigV4-signing MCP client; awkward from Claude Code/Cowork, and it puts AWS creds back
  in builders' hands, which the product explicitly avoids.
- B) ⭐ **OAuth client-credentials via a Cognito user pool stood up today** — the client
  id/secret plays the role of "the builder's API key" from the vision; Claude Code
  supports OAuth-bearing HTTP MCP. One extra resource to create and tag.
- C) **Entra ID (Cornell SSO) as the OAuth authorizer** — the real end state (builder
  identity = NetID), but needs an Azure app registration and Track C-adjacent help; not a
  today thing.
- X) Other

[Answer]: X — **Entra ID now**, by platform-lead directive (Marty, 2026-08-03),
superseding the earlier Cognito assumption (⭐B / DECISION-16). Cornell is an M365 shop
and Entra was already the stated end state; Marty hand-creates the Azure app registration
and its ids reach the stack via SSM parameters (`/entra/builder-mcp/*`). Still
client-credentials (app identity) — per-user NetID identity via authorization-code flow
stays a P1 item (BACKLOG). See DECISION-20.

## P3 — Account, tags, and blast radius for today's CLI deploy

The deploy uses the presenter's AWS CLI. Confirmations needed:

1. The account my CLI points at is the shared workshop account — correct, and is a
   CLI-created AgentCore runtime acceptable there this week? (CLAUDE.md says everything
   is IaC through GitHub; this is a knowing, temporary exception.)
2. ⭐ I will tag every created resource (runtime, ECR repo, Cognito pool, secret, role)
   with the four `cornell:*` tags (`owner=tmf77`, `blueprint=builder-mcp`,
   `blueprint-version=0.1.0`, `deployment-id=aidlc-main-builder-mcp`) so Track E's
   dashboard sees it — confirm.
3. Who tears it down / owns it after Tuesday?

[Answer]:

## P4 — Server-side GitHub credential

The server needs a GitHub credential to create repos and open PRs (the builder's client
never gets one). Note: `timothyfraser` currently has **read-only** access to the org repo,
so until access is granted every GitHub write returns a dry-run plan regardless.

- A) ⭐ **Fine-grained PAT, org-scoped, stored in AWS Secrets Manager**
  (`aidlc/main/builder-mcp/github-token`), injected as an env var by the runtime. Rotate
  Wednesday. Never in the repo — it's public with no secret scanning.
- B) A GitHub App installation *this week* — the correct end state (D3), but app
  registration + key management is P1 work, not pre-demo work.
- X) Other

[Answer]:

## P5 — Paying down the IaC debt

- A) ⭐ **Register the debt now**: `builder-mcp/infra/` CloudFormation template for the
  AgentCore runtime + role (+ Cognito if P2-B), added to `pipeline/stacks.yml` as
  `deployed_by: manual` this week, promoted to a pipeline action in P1. The CLI deploy
  and the template stay in lockstep.
- B) CLI-only today, template later — faster now, and the classic way expedients become
  permanent.
- X) Other

[Answer]:

## P6 — Observability & cost guardrails

- A) ⭐ **CloudWatch logs on, AgentCore observability on, one budget alarm** on the
  workshop account for AgentCore spend, alarm to the platform team's channel. ~15 min.
- B) Logs only today.
- X) Other

[Answer]:
