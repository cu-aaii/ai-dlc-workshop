#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp"]
# ///
"""Call one Cornell Builder MCP tool and pretty-print the result. Demo driver only.

`demo/demo.sh` uses this to stand in for the Teams bot: it speaks real MCP over stdio to the
real server, so what the audience sees is the tool surface a builder's client sees, not a
mock. Nothing here reimplements a server behaviour -- a demo that reimplemented the transforms
would drift and start lying about what the pipeline does.

    uv run demo/mcp_call.py blueprint_search '{"query": "..."}'
    uv run demo/mcp_call.py deployment_create '{"blueprint": "knowledgebase", ...}' --keys stack

Exits non-zero if the tool returns an {"error": ...} payload, so the demo stops on a real
failure instead of narrating past it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


async def call(tool: str, arguments: dict) -> dict:
    # The server is launched exactly the way .mcp.json launches it, so the demo exercises the
    # same entrypoint a builder's Claude Code session does.
    params = StdioServerParameters(
        command='uv',
        args=['run', '--directory', str(REPO_ROOT / 'packages' / 'builder-mcp'), 'builder-mcp'],
        env={
            'BUILDER_MCP_TRANSPORT': 'stdio',
            # Pin the catalog to this checkout: without it an off-repo launch fetches the
            # catalog from GitHub, which would demo main rather than the branch under review.
            'BUILDER_MCP_REPO_ROOT': str(REPO_ROOT),
            'PATH': os.environ.get('PATH', ''),
            'HOME': os.environ.get('HOME', ''),
            # Keep the demo's own log noise off the transcript; stderr is inherited.
            'BUILDER_MCP_LOG_LEVEL': os.environ.get('BUILDER_MCP_LOG_LEVEL', 'WARNING'),
        },
    )
    # The server logs one structured line per tool call to stderr, and httpx logs every GitHub
    # request at INFO under its own logger, so BUILDER_MCP_LOG_LEVEL alone does not quiet it.
    # On a projector that noise reads as errors. DEMO_SHOW_SERVER_LOG=1 puts it back when
    # something is actually wrong.
    errlog = sys.stderr if os.environ.get('DEMO_SHOW_SERVER_LOG') else open(os.devnull, 'w')
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            if result.structured_content is not None:
                return result.structured_content
            # A tool with no output schema returns text; surface it rather than guessing.
            return {'text': result.content[0].text if result.content else ''}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool')
    parser.add_argument('arguments', nargs='?', default='{}', help='JSON object of arguments')
    parser.add_argument(
        '--keys',
        nargs='+',
        help='print only these top-level keys (whole payload if omitted)',
    )
    parser.add_argument(
        '--ranked',
        action='store_true',
        help='blueprint_search only: print the ranking as a table instead of every contract',
    )
    args = parser.parse_args()

    payload = asyncio.run(call(args.tool, json.loads(args.arguments)))

    if args.ranked and 'results' in payload:
        # blueprint_search returns each blueprint's whole contract, by design -- the catalog is
        # meant to land in a model's context. On a projector that is a wall of JSON, so the demo
        # shows the ranking and reads one contract in full in the next scene.
        print(f'{"score":>7}  {"blueprint":<16}  summary')
        for item in payload['results']:
            summary = ' '.join(str(item.get('summary', '')).split())
            print(f'{item["match_score"]:>7}  {item["name"]:<16}  {summary[:88]}')
    else:
        shown = payload
        if args.keys:
            shown = {key: payload[key] for key in args.keys if key in payload}
        # ensure_ascii=False: the server's plan strings contain em dashes, and the default
        # escapes them to a \u sequence that reads as a bug on a projector.
        print(json.dumps(shown, indent=2, ensure_ascii=False))

    if 'error' in payload:
        print(f'\n{args.tool} returned an error -- stopping.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
