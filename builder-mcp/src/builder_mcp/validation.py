"""Input validation and safe error rendering, shared by every tool.

Security Baseline remediation home (see aidlc-docs/construction/security-compliance.md):

- F1 / SECURITY-08: the file-path denylist. `deployment_update` and `deployment_create`
  push files to a branch with the server's credential; a file landing under
  `.github/workflows/` executes in GitHub Actions on push — *before* any human reviews
  the PR — so "merge is the only deploy trigger" would not hold. Every path a tool
  writes goes through `file_path_problem` first.
- SECURITY-05: caller-supplied strings (owner_netid, title, description, files) are
  bounded and pattern-checked here.
- SECURITY-09: `safe_error` renders any exception as a one-line narrative — class name
  plus a truncated, redacted summary. Never a traceback, never a URL query string,
  never anything that smells like a token, ARN, or account id.
"""

from __future__ import annotations

import re
from typing import Any

# Cornell NetIDs: 2-4 lowercase letters followed by 1-5 digits (e.g. tmf77).
NETID_PATTERN = re.compile(r"^[a-z]{2,4}[0-9]{1,5}$")

MAX_TITLE_LEN = 200
MAX_DESCRIPTION_LEN = 10_000
MAX_FILE_COUNT = 50
MAX_FILES_TOTAL_BYTES = 512 * 1024  # 512 KB across all files in one call

# Conservative allowlist for repo-relative paths; notably excludes '\\', '%', and
# whitespace, so encoded traversal ('%2e%2e') and header-ish tricks never parse as valid.
_PATH_CHARS = re.compile(r"^[A-Za-z0-9._/-]+$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def file_path_problem(path: Any) -> str | None:
    """Return an error narrative if `path` may not be written by a tool, else None.

    The denylist, not a style check: `.github/` (workflow injection = pre-review code
    execution), traversal (`..`), and absolute paths are refused outright.
    """
    if not isinstance(path, str) or not path:
        return f"file path {path!r} is not a non-empty string"
    if path.startswith("/") or path.startswith("\\") or _WINDOWS_DRIVE.match(path):
        return f"file path {path!r} is absolute; only repo-relative paths are allowed"
    if ".." in path:
        return f"file path {path!r} contains '..'; path traversal is not allowed"
    if path == ".github" or path.startswith(".github/"):
        return (
            f"file path {path!r} targets .github/ — workflow files execute in GitHub "
            "Actions on push, before any human reviews the PR, so this server refuses "
            "to write there (review-gate bypass)"
        )
    if not _PATH_CHARS.match(path):
        return (
            f"file path {path!r} contains characters outside the allowed set "
            "[A-Za-z0-9._/-]"
        )
    return None


def files_problem(files: Any) -> str | None:
    """Validate a {path: content} map: every path clean, bounded count and total size."""
    if not isinstance(files, dict) or not files:
        return "files must be a non-empty map of repo-relative path -> full new content"
    if len(files) > MAX_FILE_COUNT:
        return f"files has {len(files)} entries; the cap is {MAX_FILE_COUNT} per call"
    total = 0
    for path, content in files.items():
        problem = file_path_problem(path)
        if problem:
            return problem
        if not isinstance(content, str):
            return f"content for {path!r} is not a string"
        total += len(content.encode("utf-8"))
    if total > MAX_FILES_TOTAL_BYTES:
        return (
            f"files total {total} bytes of content; the cap is "
            f"{MAX_FILES_TOTAL_BYTES} bytes per call"
        )
    return None


def owner_netid_problem(owner_netid: Any) -> str | None:
    if not isinstance(owner_netid, str) or not NETID_PATTERN.match(owner_netid):
        return (
            f"owner_netid {owner_netid!r} does not look like a Cornell NetID "
            "(2-4 lowercase letters then 1-5 digits, e.g. 'tmf77')"
        )
    return None


def title_description_problem(title: Any, description: Any) -> str | None:
    if not isinstance(title, str) or not title.strip():
        return "title must be a non-empty string"
    if len(title) > MAX_TITLE_LEN:
        return f"title is {len(title)} characters; the cap is {MAX_TITLE_LEN}"
    if not isinstance(description, str):
        return "description must be a string"
    if len(description) > MAX_DESCRIPTION_LEN:
        return f"description is {len(description)} characters; the cap is {MAX_DESCRIPTION_LEN}"
    return None


# -- safe error rendering (SECURITY-09) --------------------------------------------------

_REDACTIONS = (
    re.compile(r"(?i)\b(?:bearer|token|authorization|secret|password)\b[=:\s]+\S+"),
    re.compile(r"\barn:[^\s'\"]+"),        # AWS ARNs embed the account id
    re.compile(r"\b[0-9]{12}\b"),          # bare AWS account ids
    re.compile(r"\?[^\s'\"]+"),            # URL query strings (may carry credentials)
)


def safe_error(error: BaseException, doing: str) -> dict[str, Any]:
    """One-line, redacted error narrative: exception class + safe summary, never a
    traceback. The full detail belongs in the server-side DEBUG log, not the caller."""
    text = str(error) or ""
    summary = text.splitlines()[0] if text else ""
    for pattern in _REDACTIONS:
        summary = pattern.sub("[redacted]", summary)
    summary = summary[:200]
    message = f"{doing} failed ({error.__class__.__name__})"
    if summary:
        message = f"{message}: {summary}"
    return {"error": message}
