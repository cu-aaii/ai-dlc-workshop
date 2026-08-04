"""Environment-driven settings.

Everything configurable lives here so the same code runs three ways: on a laptop against
the local checkout, on a laptop against GitHub only, and stateless on Bedrock AgentCore.
The server holds the credentials (GitHub token, AWS role); the builder's client holds
neither -- that boundary is the point of the design (proposal D3).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


def find_repo_root() -> Path | None:
    """Walk up from this file looking for the workshop checkout (pipeline/stacks.yml).

    Present when running from the repo; absent on AgentCore, where the catalog and
    pipeline definition are fetched from GitHub instead.

    Public because the tests need it too: this package sits at packages/builder-mcp/, so
    counting parents to reach the repo root couples every caller to the directory depth
    and breaks silently the next time something moves. Sentinel-based, so it doesn't.
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
    # Where deployment_create puts the deployment shell:
    #   'folder' (testing-phase default) -> outputs/<name>/ in the workshop repo, on the
    #             same branch as the registration PR -- one PR, no repo creation. Used
    #             while the team's GitHub credential cannot create org repos.
    #   'repo'   -> a new cu-aaii/deploy-<name> repo (the D1/D5 target state), stashed
    #             behind this switch and reactivated by BUILDER_MCP_DEPLOYMENT_MODE=repo.
    deployment_mode: str = "folder"

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
        region = os.environ.get("AWS_REGION", "us-east-1")
        return cls(
            github_org=os.environ.get("BUILDER_MCP_GITHUB_ORG", "cu-aaii"),
            workshop_repo=os.environ.get("BUILDER_MCP_WORKSHOP_REPO", "ai-dlc-workshop"),
            application=os.environ.get("BUILDER_MCP_APPLICATION", "aidlc"),
            environment=os.environ.get("BUILDER_MCP_ENVIRONMENT", "main"),
            aws_region=region,
            github_token=_resolve_github_token(region),
            repo_root=Path(root) if root else find_repo_root(),
            deployment_mode=_resolve_deployment_mode(),
        )


def _resolve_deployment_mode() -> str:
    """'folder' | 'repo' from BUILDER_MCP_DEPLOYMENT_MODE; anything else degrades to
    'folder' with a warning rather than crashing (NFR7 -- a bare start must succeed)."""
    mode = os.environ.get("BUILDER_MCP_DEPLOYMENT_MODE", "folder").strip().lower()
    if mode not in ("folder", "repo"):
        logger.warning(
            "BUILDER_MCP_DEPLOYMENT_MODE %r is not 'folder' or 'repo'; using 'folder'",
            mode,
        )
        return "folder"
    return mode


def _resolve_github_token(region: str) -> str | None:
    """GITHUB_TOKEN env var locally; a Secrets Manager secret on AgentCore.

    The secret path keeps the token out of the runtime's environment-variable
    configuration, which is visible in the console and in templates. Failure to fetch
    degrades to read-only rather than crashing the server (NFR7).
    """
    direct = os.environ.get("GITHUB_TOKEN")
    if direct:
        return direct
    secret_name = os.environ.get("BUILDER_MCP_GITHUB_TOKEN_SECRET")
    if not secret_name:
        return None
    try:
        import boto3

        response = boto3.client("secretsmanager", region_name=region).get_secret_value(
            SecretId=secret_name
        )
        return response.get("SecretString") or None
    except Exception as error:
        # Degrade to read-only rather than crash (NFR7) — but never silently
        # (SECURITY-03): the operator must be able to see why writes became dry-runs.
        logger.warning(
            "could not fetch GitHub token secret %r (%s); GitHub writes degrade to "
            "dry-run plans",
            secret_name,
            error.__class__.__name__,
        )
        return None
