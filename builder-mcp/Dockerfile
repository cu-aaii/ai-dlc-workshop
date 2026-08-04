# Container image for builder-mcp, built by the pipeline's ARM CodeBuild project
# (pipeline/codebuild.yml): docker build <this directory> --target builder-mcp. The Build
# stage action sets CONTAINER_CONTEXT=builder-mcp, so the build context is this directory
# and COPY paths are relative to it. Keep the named target: CONTAINER_TARGET selects it.

# --- builder-mcp: Cornell Builder MCP server on Bedrock AgentCore ------------------------
# AgentCore Runtime contract: linux/arm64, MCP over streamable HTTP on 0.0.0.0:8000/mcp,
# stateless. Built by the ARM CodeBuild project; deployed by digest.
# Base image pinned by digest (SECURITY-10): this is the multi-arch index digest of
# ghcr.io/astral-sh/uv:python3.13-bookworm-slim as of 2026-08-03, obtained via
# `docker buildx imagetools inspect`. Bump deliberately; a mutable tag could change
# the production image between builds with no diff in this repo.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder-mcp

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

# Non-root runtime (SECURITY-09 hardening): the server needs no root capability. The
# venv stays root-owned and world-readable; `uv run --no-sync` never writes to it.
RUN useradd --create-home --shell /usr/sbin/nologin app
USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "builder-mcp"]
