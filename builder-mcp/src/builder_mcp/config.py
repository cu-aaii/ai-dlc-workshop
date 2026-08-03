"""Environment-driven settings.

Everything configurable lives here so the same code runs three ways: on a laptop against
the local checkout, on a laptop against GitHub only, and stateless on Bedrock AgentCore.
The server holds the credentials (GitHub token, AWS role); the builder's client holds
neither -- that boundary is the point of the design (proposal D3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _find_repo_root() -> Path | None:
    """Walk up from this file looking for the workshop checkout (pipeline/stacks.yml).

    Present when running from the repo; absent on AgentCore, where the catalog and
    pipeline definition are fetched from GitHub instead.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pipeline" / "stacks.yml").is_file():
            return candidate
    return None


@dataclass(frozen=True)
class Settings:
    github_org: str
    workshop_repo: str        # org/name of the repo the pipeline tracks
    application: str          # 'aidlc' -- stack name prefix, [a-z0-9-]{1,10}
    environment: str          # branch the pipeline tracks, [a-z0-9]{1,4}
    aws_region: str
    github_token: str | None  # absent -> GitHub write operations return dry-run plans
    repo_root: Path | None    # absent -> read catalog/pipeline from GitHub

    @property
    def pipeline_name(self) -> str:
        return f"{self.application}-{self.environment}"

    @property
    def workshop_repo_full(self) -> str:
        return f"{self.github_org}/{self.workshop_repo}"

    def stack_name(self, deployment_name: str) -> str:
        return f"{self.application}-{self.environment}-{deployment_name}"

    @classmethod
    def from_env(cls) -> "Settings":
        root = os.environ.get("BUILDER_MCP_REPO_ROOT")
        return cls(
            github_org=os.environ.get("BUILDER_MCP_GITHUB_ORG", "cu-aaii"),
            workshop_repo=os.environ.get("BUILDER_MCP_WORKSHOP_REPO", "ai-dlc-workshop"),
            application=os.environ.get("BUILDER_MCP_APPLICATION", "aidlc"),
            environment=os.environ.get("BUILDER_MCP_ENVIRONMENT", "main"),
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            github_token=os.environ.get("GITHUB_TOKEN") or None,
            repo_root=Path(root) if root else _find_repo_root(),
        )
