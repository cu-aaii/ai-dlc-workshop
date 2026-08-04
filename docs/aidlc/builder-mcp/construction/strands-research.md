# Strands Agents research: should the Cornell Builder adopt it?

Research date: 2026-08-03. Prompted by an external suggestion that "STRANDS" is "an
alternative to FastAPI, well optimized for working with genAI" and might replace the way we
write the Builder's MCP API.

## TL;DR verdict

**Strands is not an alternative to FastAPI or to the MCP Python SDK, and it cannot replace
our MCP server.** It is AWS's open-source *agent* framework: it builds LLM-driven agents that
**consume** MCP tools as a client and are served through AgentCore's HTTP invocation contract
or the A2A protocol. The thing that serves MCP on AgentCore Runtime is the official MCP
Python SDK's `FastMCP` — which is exactly what `builder-mcp` already uses. The description
relayed to the team ("alternative to FastAPI for writing AI/MCP APIs") is a
mischaracterization.

The only parallel implementation that makes sense is **shape (b)**: a small Strands *agent*
("Cornell Builder agent") that wraps our existing seven-tool MCP server and adds
reasoning/orchestration, deployed beside — not instead of — the MCP server. That is a
legitimate 2–4 day pilot, but it introduces a runtime LLM dependency (and per-invocation
Bedrock cost) that our current server deliberately does not have. Recommendation: keep the
MCP server as-is; treat the Strands agent as an optional post-workshop experiment.

*(Note: the request described an "8-tool" server; the server registers seven tools —
`blueprint_search`, `create_deployment`, `deployment_status`, `propose_change`,
`health_check`, `restart_deployment`, `export_spec` — per
`builder-mcp/src/builder_mcp/server.py` and SPEC.md §C3 "Tool surface (seven tools)".)*

## What Strands is (verified)

- **Strands Agents** is an open-source, model-driven SDK for building AI agents, created and
  maintained by AWS ("built from production systems inside Amazon"), announced on the AWS
  Open Source Blog in May 2025. Python and TypeScript SDKs. GitHub org: `strands-agents`.
  [strandsagents.com](https://strandsagents.com/), [AWS blog](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/)
- **Current state (Aug 2026):** PyPI `strands-agents` is at **v1.50.2** (released
  2026-07-27), Python >=3.10, **Apache-2.0** license. The GitHub repo shows active
  maintenance (~2,300 commits, ~6.8k stars, hundreds of open issues/PRs). The org is
  consolidating repos into a `strands-agents/harness-sdk` monorepo (e.g. the old
  `mcp-server` docs repo was archived into it on 2026-07-27). Related packages:
  `strands-agents-tools` (prebuilt tools), `bedrock-agentcore` (runtime wrapper).
  [PyPI](https://pypi.org/project/strands-agents/), [GitHub](https://github.com/strands-agents/sdk-python)
- **Core model:** you construct an `Agent(model=..., tools=[...], system_prompt=...)`; the
  framework runs the LLM-driven tool-use loop. Model-agnostic (Bedrock default; Anthropic,
  OpenAI, Gemini, Ollama, LiteLLM providers). Adds multi-agent orchestration, A2A protocol
  support, sessions, hooks/guardrails, and observability.
- **`strands-agents-mcp-server` is a red herring** for our question: it is an MCP server
  that serves *Strands documentation* (llms.txt search) to coding assistants — a
  documentation delivery tool, not a framework for building MCP servers.
  [github.com/strands-agents/mcp-server](https://github.com/strands-agents/mcp-server) (archived)

## The load-bearing answer: agent framework, not MCP-serving framework

**Strands consumes MCP; it does not serve it.**

- Strands's MCP integration is the **`MCPClient`** class (`strands.tools.mcp.MCPClient`),
  which connects an *agent* to external MCP servers over stdio or streamable HTTP so the
  agent can call their tools. Every MCP example in the official docs is client-side.
  [strandsagents.com docs](https://strandsagents.com/docs/user-guide/build-with-ai)
- For **serving**, Strands offers: (1) the AgentCore **HTTP invocation contract**
  (`/invocations` + `/ping`, via `BedrockAgentCoreApp` in Python or an Express server in
  TypeScript), and (2) an **`A2AServer`** (`strands.multiagent.a2a.A2AServer`) that exposes
  an agent to other agents over the A2A protocol. Neither is MCP.
- Conversely, AWS's own AgentCore documentation for **hosting an MCP server** uses the
  **official MCP Python SDK** (`from mcp.server.fastmcp import FastMCP`,
  `mcp.run(transport="streamable-http")`, `stateless_http=True`) — the identical stack and
  pattern `builder-mcp/src/builder_mcp/server.py` uses today. Strands appears nowhere in
  that path.
  [AgentCore MCP hosting guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)

So "rewrite our MCP server in Strands" is a category error: if we want an MCP tool server
(we do — our client is Claude/other MCP hosts, and merge-is-the-only-deploy governance lives
in the human-confirmed client loop), the MCP SDK **is** the right and AWS-recommended tool.
A Strands "parallel implementation" is necessarily a different *kind* of artifact: an agent.

## AgentCore Runtime integration specifics

AgentCore Runtime hosts three protocol shapes; our current deployment uses the first:

| Protocol | Contract | Who implements it | Our status |
|---|---|---|---|
| **MCP** | streamable HTTP at `0.0.0.0:8000/mcp`; stateless (`stateless_http=True`) recommended; platform injects `Mcp-Session-Id`; stateful mode exists for elicitation/sampling | official MCP SDK (`FastMCP`) | **This is builder-mcp today** (server.py `main()` matches the contract exactly) |
| **HTTP invocation** | `POST /invocations` + `GET /ping` on port 8080 | `bedrock-agentcore`'s `BedrockAgentCoreApp` (`@app.entrypoint`) wrapping a Strands (or any) agent | What a Strands agent would use |
| **A2A** | agent-to-agent protocol; `A2AServer(agent=...).serve()` | Strands `strands.multiagent.a2a` | Not relevant yet |

Strands's official AgentCore deployment path
([docs](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python))
is ~10 lines: instantiate `BedrockAgentCoreApp`, decorate an `invoke(payload)` entrypoint
that calls the Strands `Agent`, `app.run()`. Note that `BedrockAgentCoreApp` comes from the
separate `bedrock-agentcore` package, not from Strands itself — Strands is the agent brain,
`bedrock-agentcore` is the serving shim. AgentCore Runtime treats all three shapes
identically for auth (Cognito/OAuth inbound auth, `InvokeAgentRuntime` passthrough), so a
Strands agent would sit behind the same identity setup we already have.

## The two parallel-implementation shapes

### Shape (a): reimplement the seven-tool MCP surface "in Strands" — **not viable**

Strands has no MCP-serving primitive. To keep serving MCP we would still write
`@mcp.tool()` functions on `FastMCP` — i.e., we would be rewriting our server *with the same
SDK we already use*, with Strands contributing nothing. The only way to make Strands central
here would be to abandon MCP as our protocol, which breaks our deploy contract (stateless
streamable HTTP MCP on `0.0.0.0:8000/mcp`) and every MCP client integration. **Rejected on
technical grounds, not preference.**

### Shape (b): a Strands "Cornell Builder agent" beside the MCP server — **the honest candidate**

A Strands agent, deployed as a second AgentCore Runtime (HTTP protocol), that consumes the
existing MCP server via `MCPClient` over streamable HTTP and adds an orchestration layer:
multi-step flows ("find me a blueprint, check the catalog contract, draft the deployment,
show me the plan"), status narration, spec summarization. The MCP server stays the single
governed write path; the agent is a client of it like any other.

```
builder-agent/                      # new sibling of builder-mcp/
├── pyproject.toml                  # deps below
├── Dockerfile                      # container image for AgentCore Runtime (port 8080)
├── src/builder_agent/
│   ├── __init__.py
│   ├── app.py                      # BedrockAgentCoreApp; @app.entrypoint invoke(payload)
│   ├── agent.py                    # strands.Agent(model=BedrockModel(us-east-1),
│   │                               #   tools=[mcp_client], system_prompt=POLICY)
│   ├── mcp_tools.py                # MCPClient(streamablehttp_client(BUILDER_MCP_URL))
│   │                               #   + auth header wiring (AgentCore outbound identity)
│   └── policy.py                   # system prompt encoding governance: always dry_run
│                                   #   first, surface the plan verbatim, never call
│                                   #   dry_run=false without explicit user confirmation
│                                   #   text in the payload
└── tests/
    └── test_policy.py              # prompt/contract tests against a stubbed MCP server
```

Dependencies: `strands-agents>=1.50`, `bedrock-agentcore` (runtime wrapper), `mcp>=1.10`
(client transport; already a dependency of builder-mcp), plus the existing container
toolchain. Model: Bedrock (Claude) in `us-east-1` via IAM — no new secrets, consistent with
the Secrets Manager rule since Bedrock auth is role-based.

**Recommendation: shape (b), as a bounded post-workshop pilot — and only if a use case
actually needs server-side orchestration.** Today the reasoning loop lives in the user's MCP
host (Claude), which already orchestrates the seven tools and — critically — puts the
dry_run confirmation in front of a human for free. A Strands agent re-creates that loop
server-side, which is only worth it for headless/scheduled flows or non-MCP entry points
(e.g., a future Teams bot, which is on the roadmap and where Strands is explicitly named in
CLAUDE.md's deliberately-not-built `course-chatbot` item).

## Costs and risks

- **Runtime LLM dependency — the big one.** A Strands `Agent` requires a model provider at
  runtime (defaults to Bedrock); the agentic loop *is* model invocation. Our MCP server
  requires no LLM at runtime — the intelligence lives in the caller's client. Shape (b) adds
  per-invocation Bedrock token cost, model latency, model-version drift, and a new failure
  mode (model errors/refusals) to a path that currently has none.
- **Governance surface.** Our human-in-the-loop invariant is enforced by UX: mutating tools
  default to `dry_run=true` and the *human's* client re-calls with `dry_run=false`. An
  autonomous agent holding those tools could decide to flip `dry_run` itself. Mitigable
  (policy prompt + agent-side tool wrapper that hard-blocks `dry_run=false` unless the
  payload carries explicit confirmation), but it is a new thing to get wrong. The hard D4
  invariant is safe either way — the MCP server still cannot deploy/merge/push, and the
  agent has no write path the server doesn't have.
- **Maturity/churn.** Apache-2.0, genuinely active, AWS-backed — good. But the ecosystem is
  reorganizing right now (repos archived into a `harness-sdk` monorepo in July 2026; the SDK
  moved from 1.0 to 1.50.x within months). Expect API movement; pin versions.
- **Lock-in.** The Strands SDK itself is model- and cloud-agnostic (mild lock-in), but the
  serving shim (`bedrock-agentcore`, `BedrockAgentCoreApp`) and the AgentCore deploy path
  are AWS-specific — the same coupling we already accepted for the MCP server, so no net
  change.
- **Operational.** A second AgentCore Runtime to build, tag (all four `cornell:*` tags),
  register in `pipeline/stacks.yml`, mirror in `pipeline.yml`, and observe. Different port
  (8080) and contract (`/invocations`+`/ping`) than the MCP server; two container images
  instead of one.
- **No governance-invariant violation** in shape (b) as designed: the agent opens PRs
  through the same server-side tools; merge remains the only deploy trigger; no
  deploy/merge/push capability is added anywhere.

## Go/no-go

- **Replacing the MCP server with Strands: NO-GO.** Technically incoherent — Strands does
  not serve MCP; AWS's own MCP-hosting guidance uses the SDK we already use. Zero benefit,
  guaranteed breakage of the deploy contract.
- **Shape (b) pilot (Strands agent beside the server): CONDITIONAL GO, low priority.**
  Estimated effort: **2–4 builder-days** — ~0.5 day for agent + entrypoint + MCPClient
  wiring (the SDK is genuinely terse), ~1 day for the governance policy layer and tests,
  ~1–2 days for the AgentCore runtime, identity, container plumbing, and pipeline
  registration. Prerequisite: a named use case that MCP clients can't already serve
  (headless flows or the Teams-bot front end). Until then, the current architecture is
  strictly simpler and cheaper. Revisit when `blueprints/course-chatbot/` work begins,
  where Strands is already the planned agent framework.

## Sources

- https://strandsagents.com/ — official site ("open source toolkit for building production agents")
- https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/ — AWS announcement
- https://github.com/strands-agents/sdk-python — SDK repo (Apache-2.0, ~6.8k stars, active)
- https://pypi.org/project/strands-agents/ — v1.50.2, 2026-07-27, Python >=3.10
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html — AgentCore MCP hosting contract (`0.0.0.0:8000/mcp`, `stateless_http=True`, uses official MCP SDK `FastMCP`)
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html — HTTP invocation contract (`/invocations`, `/ping`)
- https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python — `BedrockAgentCoreApp` deployment pattern
- https://strandsagents.com/docs/user-guide/build-with-ai — `MCPClient` (Strands consuming MCP)
- https://strandsagents.com/llms-full.txt — `A2AServer` example; AgentCore protocol overview
- https://github.com/strands-agents/mcp-server — the "Strands MCP server" is a docs-delivery server; archived 2026-07-27 into the harness-sdk monorepo
- https://glama.ai/blog/2025-07-22-understanding-aws-agents-strands-bedrock-agents-and-agent-core-with-mcp — secondary: Strands vs Bedrock Agents vs AgentCore taxonomy
- Internal grounding: `builder-mcp/src/builder_mcp/server.py`, `builder-mcp/SPEC.md` §C3, `builder-mcp/pyproject.toml`, repo `CLAUDE.md`
