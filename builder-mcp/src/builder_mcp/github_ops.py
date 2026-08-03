"""GitHub operations, all through the server's credential -- never the builder's.

Today the credential is a token in GITHUB_TOKEN (the presenter's, workshop expedient).
The P1 target is a GitHub App installation, which is the only version where "no direct
write access" is fully true (proposal D3). The call surface below is already App-shaped:
nothing here merges a PR, pushes to a tracked branch, or touches main -- merge stays a
human act at the review gate (D4).

With no token configured, every write operation returns a dry-run plan instead of failing,
so the tool surface is demonstrable on a clean machine (NFR7).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from .config import Settings

API = "https://api.github.com"

logger = logging.getLogger(__name__)


class GitHubOps:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = httpx.Client(base_url=API, headers=headers, timeout=30)

    def close(self) -> None:
        """Release the underlying httpx connection pool. GitHubOps instances are
        per-tool-call in a long-lived container; leaking them leaks sockets."""
        self.client.close()

    def __enter__(self) -> "GitHubOps":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def can_write(self) -> bool:
        return self.settings.github_token is not None

    # -- reads ---------------------------------------------------------------

    def get_file(self, repo_full: str, path: str, ref: str | None = None) -> tuple[str, str]:
        """Return (content, blob_sha) for a file."""
        params = {"ref": ref} if ref else {}
        response = self.client.get(f"/repos/{repo_full}/contents/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8")
        return content, payload["sha"]

    def default_branch(self, repo_full: str) -> str:
        response = self.client.get(f"/repos/{repo_full}")
        response.raise_for_status()
        return response.json()["default_branch"]

    def branch_head_sha(self, repo_full: str, branch: str) -> str:
        response = self.client.get(f"/repos/{repo_full}/git/ref/heads/{branch}")
        response.raise_for_status()
        return response.json()["object"]["sha"]

    def list_dir(self, repo_full: str, path: str, ref: str | None = None) -> list[tuple[str, str]]:
        """Return [(path, blob_sha)] for the files directly under a directory; [] when
        the directory does not exist (contents API 404s on a missing path)."""
        params = {"ref": ref} if ref else {}
        response = self.client.get(f"/repos/{repo_full}/contents/{path}", params=params)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):  # a file, not a directory
            return [(payload["path"], payload["sha"])]
        return [(item["path"], item["sha"]) for item in payload if item["type"] == "file"]

    def open_prs(self, repo_full: str, head_contains: str | None = None) -> list[dict[str, Any]]:
        response = self.client.get(f"/repos/{repo_full}/pulls", params={"state": "open"})
        response.raise_for_status()
        prs = response.json()
        if head_contains:
            prs = [pr for pr in prs if head_contains in pr["head"]["ref"]]
        return [
            {"number": pr["number"], "title": pr["title"], "url": pr["html_url"], "branch": pr["head"]["ref"]}
            for pr in prs
        ]

    # -- writes (dry-run without a token) ------------------------------------

    def create_org_repo(self, name: str, description: str) -> dict[str, Any]:
        if not self.can_write:
            return {"dry_run": True, "would": f"create repo {self.settings.github_org}/{name}: {description}"}
        response = self.client.post(
            f"/orgs/{self.settings.github_org}/repos",
            json={"name": name, "description": description, "visibility": "private", "auto_init": True},
        )
        response.raise_for_status()
        return {"repo": response.json()["full_name"], "url": response.json()["html_url"]}

    def create_branch(self, repo_full: str, branch: str, from_branch: str | None = None) -> dict[str, Any]:
        if not self.can_write:
            return {"dry_run": True, "would": f"create branch {branch} on {repo_full}"}
        base = from_branch or self.default_branch(repo_full)
        sha = self.branch_head_sha(repo_full, base)
        response = self.client.post(
            f"/repos/{repo_full}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}
        )
        response.raise_for_status()
        return {"branch": branch, "base": base, "sha": sha}

    def put_file(
        self, repo_full: str, path: str, content: str, message: str, branch: str, sha: str | None = None
    ) -> dict[str, Any]:
        if not self.can_write:
            return {"dry_run": True, "would": f"write {path} on {repo_full}@{branch}"}
        logger.debug("put_file repo=%s path=%s branch=%s bytes=%d", repo_full, path, branch, len(content))
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        response = self.client.put(f"/repos/{repo_full}/contents/{path}", json=body)
        response.raise_for_status()
        return {"path": path, "branch": branch, "commit": response.json()["commit"]["sha"]}

    def delete_file(
        self, repo_full: str, path: str, message: str, branch: str, sha: str | None = None
    ) -> dict[str, Any]:
        """Mirror of put_file for the contents DELETE API: removes one file on a branch.
        Dry-run aware; fetches the blob sha itself when the caller does not have it."""
        if not self.can_write:
            return {"dry_run": True, "would": f"delete {path} on {repo_full}@{branch}"}
        if sha is None:
            _, sha = self.get_file(repo_full, path, ref=branch)
        logger.debug("delete_file repo=%s path=%s branch=%s", repo_full, path, branch)
        response = self.client.request(
            "DELETE",
            f"/repos/{repo_full}/contents/{path}",
            json={"message": message, "sha": sha, "branch": branch},
        )
        response.raise_for_status()
        return {"path": path, "branch": branch, "commit": response.json()["commit"]["sha"]}

    def create_pull(self, repo_full: str, head: str, title: str, body: str, base: str | None = None) -> dict[str, Any]:
        if not self.can_write:
            return {"dry_run": True, "would": f"open PR on {repo_full}: {title}"}
        base = base or self.default_branch(repo_full)
        response = self.client.post(
            f"/repos/{repo_full}/pulls", json={"title": title, "body": body, "head": head, "base": base}
        )
        response.raise_for_status()
        return {"number": response.json()["number"], "url": response.json()["html_url"]}
