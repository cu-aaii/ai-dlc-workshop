# Container image for Bedrock AgentCore Runtime (linux/arm64 required).
# Contract: MCP over streamable HTTP on 0.0.0.0:8000 at /mcp, stateless.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Dependency layer first so code edits don't re-resolve the environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# Stateless + all-interfaces is the AgentCore contract; locally you'd run without these.
ENV BUILDER_MCP_HOST=0.0.0.0 \
    BUILDER_MCP_STATELESS=1 \
    BUILDER_MCP_PORT=8000

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "builder-mcp"]
