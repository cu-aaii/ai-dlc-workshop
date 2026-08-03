# Container images for this repo, one named target per component, built by the pipeline's
# CodeBuild project (pipeline/codebuild.yml): docker build <repo root> --target <name>.
# Context is the repo root, so COPY paths start from it. Keep targets self-contained.

# --- builder-mcp: Cornell Builder MCP server on Bedrock AgentCore ------------------------
# AgentCore Runtime contract: linux/arm64, MCP over streamable HTTP on 0.0.0.0:8000/mcp,
# stateless. Built by the ARM CodeBuild project; deployed by digest.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder-mcp

WORKDIR /app

# Dependency layer first so code edits don't re-resolve the environment.
COPY packages/builder-mcp/pyproject.toml packages/builder-mcp/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY packages/builder-mcp/src ./src
COPY packages/builder-mcp/README.md ./
RUN uv sync --frozen --no-dev

# Stateless + all-interfaces is the AgentCore contract; locally you'd run without these.
ENV BUILDER_MCP_HOST=0.0.0.0 \
    BUILDER_MCP_STATELESS=1 \
    BUILDER_MCP_PORT=8000

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "builder-mcp"]
