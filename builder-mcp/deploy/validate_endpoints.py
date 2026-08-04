"""Endpoint validation harness: iterative calls against every builder-mcp tool.

Runs N sequential calls per tool (default 10) against a running server -- local
(`uv run builder-mcp`) or the deployed AgentCore runtime -- and reports success,
degradation, and wall-clock latency per tool. This produces the project's first latency
numbers; **no performance targets exist yet**, so the harness measures and never asserts
thresholds (BACKLOG "Verification & performance" speed-check item).

    uv run python deploy/validate_endpoints.py                       # local server
    uv run python deploy/validate_endpoints.py --iterations 3 --tools blueprint_search
    BUILDER_MCP_TOKEN=... uv run python deploy/validate_endpoints.py \
        --url https://.../invocations?qualifier=DEFAULT --bearer-env BUILDER_MCP_TOKEN

Outcome taxonomy, per call:

- ok:       the MCP call returned and the payload parsed as JSON with no "error" key.
- degraded: returned + parsed, but the payload carries "error" -- expected for the AWS
  read tools on a machine without AWS credentials, so degraded is NOT a failure.
- failed:   transport error, timeout (30s), or a payload that is not JSON.

Exit code 0 iff every exercised tool had zero failed calls. Mutating tools are only ever
called with dry_run=true; the harness cannot create repos, branches, or PRs.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

CALL_TIMEOUT_S = 30.0

# Known-good, side-effect-free arguments for all eight tools. Mutating tools use
# dry_run=true (the server's confirm-before-doing contract) so nothing is created.
# deployment_update targets deploy-hello-world, which passes the server's repo
# allowlist (workshop repo or <org>/deploy-*).
TOOL_CALLS: dict[str, dict[str, Any]] = {
    "blueprint_search": {"query": "smoke test the deploy path"},
    "deployment_read": {"deployment_name": "hello-world"},
    "deployment_health": {"deployment_name": "hello-world"},
    "spec_export": {
        "deployment_name": "hello-world",
        "blueprint": "hello-world",
        "audience": "coder",
    },
    "deployment_create": {
        "blueprint": "hello-world",
        "deployment_name": "hello-world",
        "owner_netid": "tmf77",
        "dry_run": True,
    },
    "deployment_update": {
        "repo": "deploy-hello-world",
        "title": "Validation harness probe (dry run, never executed)",
        "description": "Opened by deploy/validate_endpoints.py with dry_run=true.",
        "files": {"README.md": "# probe\n"},
        "dry_run": True,
    },
    "deployment_restart": {"deployment_name": "hello-world", "dry_run": True},
    "deployment_delete": {"deployment_name": "hello-world", "dry_run": True},
}


@dataclass
class ToolResult:
    tool: str
    ok: int = 0
    degraded: int = 0
    failed: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return self.ok + self.degraded + self.failed

    def stats(self) -> dict[str, float]:
        if not self.latencies_ms:
            return {"min": float("nan"), "median": float("nan"),
                    "p95": float("nan"), "max": float("nan")}
        ordered = sorted(self.latencies_ms)
        p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
        return {
            "min": ordered[0],
            "median": statistics.median(ordered),
            "p95": ordered[p95_index],
            "max": ordered[-1],
        }


def classify(result: Any) -> tuple[str, str]:
    """(outcome, note) for a completed call_tool result; JSON-parse is the success bar."""
    try:
        text = result.content[0].text
        payload = json.loads(text)
    except Exception as error:  # noqa: BLE001 - any parse trouble is one outcome
        return "failed", f"payload not JSON ({error.__class__.__name__})"
    if isinstance(payload, dict) and "error" in payload:
        return "degraded", str(payload["error"])[:120]
    return "ok", ""


async def exercise_tool(
    url: str, headers: dict[str, str], tool: str, arguments: dict[str, Any], iterations: int
) -> ToolResult:
    """One MCP session per tool, so a mid-run transport failure stays contained."""
    result = ToolResult(tool=tool)
    try:
        # This SDK's streamable_http_client takes no headers kwarg; auth headers ride
        # on an httpx AsyncClient built by the SDK's own helper.
        async with create_mcp_http_client(headers=headers or None) as http_client, \
                streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CALL_TIMEOUT_S)
                for _ in range(iterations):
                    started = time.perf_counter()
                    try:
                        call = await asyncio.wait_for(
                            session.call_tool(tool, arguments), timeout=CALL_TIMEOUT_S
                        )
                    except Exception as error:  # noqa: BLE001
                        result.failed += 1
                        result.notes.append(f"call error: {error.__class__.__name__}")
                        continue
                    result.latencies_ms.append((time.perf_counter() - started) * 1000)
                    outcome, note = classify(call)
                    if outcome == "ok":
                        result.ok += 1
                    elif outcome == "degraded":
                        result.degraded += 1
                        if note and note not in result.notes:
                            result.notes.append(note)
                    else:
                        result.failed += 1
                        result.notes.append(note)
    except Exception as error:  # noqa: BLE001 - session-level failure fails remaining calls
        remaining = iterations - result.calls
        result.failed += max(remaining, 0)
        result.notes.append(f"session error: {error.__class__.__name__}: {str(error)[:120]}")
    return result


def fmt_ms(value: float) -> str:
    return "-" if math.isnan(value) else f"{value:.0f}"


HEADERS = ["tool", "calls", "ok", "degraded", "failed", "min ms", "median ms", "p95 ms", "max ms"]


def result_row(r: ToolResult) -> list[str]:
    s = r.stats()
    return [r.tool, str(r.calls), str(r.ok), str(r.degraded), str(r.failed),
            fmt_ms(s["min"]), fmt_ms(s["median"]), fmt_ms(s["p95"]), fmt_ms(s["max"])]


def console_table(results: list[ToolResult]) -> str:
    rows = [HEADERS] + [result_row(r) for r in results]
    widths = [max(len(row[i]) for row in rows) for i in range(len(HEADERS))]
    lines = []
    for n, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def markdown_report(results: list[ToolResult], url: str, iterations: int) -> str:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# builder-mcp endpoint validation",
        "",
        f"- URL: `{url}`",
        f"- Iterations per tool: {iterations}",
        f"- Timestamp: {timestamp}",
        "- No performance targets exist yet -- this is a first measurement, not a pass/fail"
        " threshold (degraded = payload carried an `error`, expected without AWS credentials).",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "|" + "|".join("---" for _ in HEADERS) + "|",
    ]
    lines += ["| " + " | ".join(result_row(r)) + " |" for r in results]
    noted = [r for r in results if r.notes]
    if noted:
        lines += ["", "## Notes", ""]
        for r in noted:
            for note in r.notes[:3]:
                lines.append(f"- `{r.tool}`: {note}")
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> int:
    headers: dict[str, str] = {}
    if args.bearer_env:
        token = os.environ.get(args.bearer_env)
        if not token:
            print(f"env var {args.bearer_env!r} is empty or unset", file=sys.stderr)
            return 1
        headers["Authorization"] = f"Bearer {token}"

    if args.tools:
        wanted = [t.strip() for t in args.tools.split(",") if t.strip()]
        unknown = sorted(set(wanted) - set(TOOL_CALLS))
        if unknown:
            print(f"unknown tools {unknown}; harness knows {sorted(TOOL_CALLS)}",
                  file=sys.stderr)
            return 1
        tools = [t for t in TOOL_CALLS if t in wanted]
    else:
        tools = list(TOOL_CALLS)

    print(f"validating {len(tools)} tool(s) at {args.url}, "
          f"{args.iterations} sequential call(s) each\n")
    results: list[ToolResult] = []
    for tool in tools:  # sequential on purpose: per-tool sessions, uncontended latency
        results.append(
            await exercise_tool(args.url, headers, tool, TOOL_CALLS[tool], args.iterations)
        )
        r = results[-1]
        print(f"  {tool}: ok={r.ok} degraded={r.degraded} failed={r.failed}")
        for note in r.notes[:3]:
            print(f"    note: {note}")

    print()
    print(console_table(results))
    print("\nNo performance targets exist yet -- these numbers are the first measurement.")

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown_report(results, args.url, args.iterations))
        print(f"markdown report written to {args.markdown}")

    total_failed = sum(r.failed for r in results)
    if total_failed:
        print(f"\nFAILED: {total_failed} call(s) failed across "
              f"{sum(1 for r in results if r.failed)} tool(s)", file=sys.stderr)
        return 1
    print("\nOK: zero failed calls" + (
        " (some degraded -- expected without AWS credentials)"
        if any(r.degraded for r in results) else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp",
                        help="MCP endpoint (default: local server)")
    parser.add_argument("--iterations", type=int, default=10,
                        help="sequential calls per tool (default 10)")
    parser.add_argument("--bearer-env", default=None, metavar="VAR",
                        help="env var holding a bearer token, for deployed runs")
    parser.add_argument("--markdown", default=None, metavar="PATH",
                        help="also write the report as markdown to PATH")
    parser.add_argument("--tools", default=None, metavar="a,b,c",
                        help="comma-separated subset of tools (default: all eight)")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
