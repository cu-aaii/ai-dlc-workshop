#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=0.75",
#   "mcp>=1.10",
#   "starlette>=0.40",
#   "uvicorn>=0.30",
# ]
# ///
"""Local browser console for exercising the Cornell Builder MCP server.

A dev harness, not part of the deploy path: no template, no image target, no pipeline
action. It is a PEP 723 inline-script on purpose -- `anthropic` is a dependency of this
console and of nothing else, so keeping it out of packages/builder-mcp/pyproject.toml
keeps it out of uv.lock and out of the AgentCore image the pipeline builds.

It talks to the server the way a real client does -- MCP over streamable HTTP, tool
schemas read from `tools/list`, system prompt taken from the server's own `instructions`
-- so what you see here is what a builder's Claude client sees. Nothing is stubbed.

    uv run --script devtools/console.py        # then open http://127.0.0.1:8765

Requires builder-mcp running (`uv run builder-mcp`) and an Anthropic credential
(ANTHROPIC_API_KEY, or an `ant auth login` profile -- the SDK resolves either).

Governance note: this console cannot deploy anything the server can't. Every mutating
tool defaults to dry_run=true, and with no GITHUB_TOKEN the write tools degrade to plans
(SPEC C5). The MCP server, not this console, is the boundary.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession

# The SDK renamed the streamable-HTTP client transport (1.x streamablehttp_client ->
# 2.x streamable_http_client) and changed its yield from a 3-tuple to a 2-tuple. Support
# both so this script keeps working across the pin builder-mcp floats on.
try:
    from mcp.client.streamable_http import streamable_http_client as _transport
except ImportError:  # pragma: no cover - mcp < 2.0
    from mcp.client.streamable_http import streamablehttp_client as _transport

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

HERE = Path(__file__).resolve().parent

MCP_URL = os.environ.get("BUILDER_MCP_URL", "http://127.0.0.1:8000/mcp")
HOST = os.environ.get("BUILDER_CONSOLE_HOST", "127.0.0.1")
PORT = int(os.environ.get("BUILDER_CONSOLE_PORT", "8765"))
MODEL = os.environ.get("BUILDER_CONSOLE_MODEL", "claude-opus-5")
EFFORT = os.environ.get("BUILDER_CONSOLE_EFFORT", "medium")
MAX_TURNS = int(os.environ.get("BUILDER_CONSOLE_MAX_TURNS", "12"))

# The chat's model selector offers only these two -- deliberately narrower than what
# BUILDER_CONSOLE_MODEL can be set to, so picking a model in the UI can't reach for Opus.
SELECTABLE_MODELS = [
    {"id": "claude-sonnet-5", "label": "Sonnet 5"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5"},
]
SELECTABLE_MODEL_IDS = {m["id"] for m in SELECTABLE_MODELS}
DEFAULT_SELECTABLE_MODEL = MODEL if MODEL in SELECTABLE_MODEL_IDS else SELECTABLE_MODELS[0]["id"]

# One conversation per browser tab. In-memory and unbounded: this is a single-user local
# tool with a Reset button, so a store with eviction would be machinery for nobody.
CONVERSATIONS: dict[str, list[dict[str, Any]]] = {}

FALLBACK_SYSTEM = (
    "You are the Cornell Builder, helping a campus builder deploy governed infrastructure "
    "through the blueprint catalog. Use the tools available to you."
)

CONSOLE_SYSTEM = (
    "\n\nYou are being driven from a local developer console whose purpose is to exercise "
    "these tools. Prefer calling a tool over describing what it would return, and quote the "
    "tool's actual output rather than paraphrasing it -- the developer is checking the tool, "
    "not your prose. Keep replies short."
)


# --- MCP bridge ---------------------------------------------------------------------------
#
# A fresh session per operation. Locally the server runs stateful on 127.0.0.1, so sessions
# are cheap and short-lived; holding one open across requests would mean owning its anyio
# task-group lifetime across the Starlette event loop for no benefit at this scale.


def _describe(error: BaseException) -> str:
    """Flatten an exception into something worth reading.

    The MCP client runs its transport in an anyio task group, so every failure surfaces as
    `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` -- which says
    nothing at all. Recurse into the group and report the leaves.
    """
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(_describe(sub) for sub in error.exceptions) or "unknown error"
    return f"{type(error).__name__}: {error}".strip().rstrip(":")


def _field(obj: Any, *names: str, default: Any = None) -> Any:
    """First attribute that exists, by name.

    The SDK's models moved from camelCase to snake_case in 2.0 (inputSchema ->
    input_schema, isError -> is_error, serverInfo -> server_info), and the aliases are not
    kept. Reading both names is what lets this console span the pin builder-mcp floats on.
    """
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


@contextlib.asynccontextmanager
async def mcp_session() -> AsyncIterator[tuple[ClientSession, Any]]:
    async with _transport(MCP_URL) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            yield session, init


async def fetch_tools() -> dict[str, Any]:
    """Tool schemas plus the server's own instructions, straight from the live server."""
    async with mcp_session() as (session, init):
        listed = await session.list_tools()
        tools = [
            {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "input_schema": _field(
                    tool,
                    "input_schema",
                    "inputSchema",
                    default={"type": "object", "properties": {}},
                ),
            }
            for tool in listed.tools
        ]
        server = _field(init, "server_info", "serverInfo")
        return {
            "tools": tools,
            "instructions": getattr(init, "instructions", None),
            "server_name": getattr(server, "name", None),
            "server_version": getattr(server, "version", None),
        }


def _flatten(result: Any) -> dict[str, Any]:
    """MCP content blocks -> one text payload for the model and the UI.

    builder-mcp returns dicts, which the server JSON-serializes into a text block, so the
    common case is a single block of JSON. Anything else is labelled rather than dropped.
    """
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(f"[non-text content block: {getattr(block, 'type', type(block).__name__)}]")
    return {
        "text": "\n".join(parts) if parts else "(no content)",
        "is_error": bool(_field(result, "is_error", "isError", default=False)),
    }


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke one tool. Never raises: a failure has to come back as a tool_result.

    Every tool_use block needs a matching tool_result or the next request is rejected, so a
    transport failure becomes an is_error result rather than an exception that strands the
    turn mid-loop.
    """
    try:
        async with mcp_session() as (session, _):
            return _flatten(await session.call_tool(name, arguments))
    except BaseException as error:  # includes ExceptionGroup from the transport task group
        return {"text": _describe(error), "is_error": True}


# --- Claude turn --------------------------------------------------------------------------


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _credential_hint(message: str) -> str:
    """Say what to do about it. Bare `APIConnectionError: Connection error.` doesn't."""
    lowered = message.lower()
    if "authentication" in lowered or "api_key" in lowered or "401" in lowered:
        return (
            f"{message}\n\nNo usable Anthropic credential. Export ANTHROPIC_API_KEY, or run "
            "`ant auth login` -- the SDK picks up either. The tool panel on the left works "
            "without one."
        )
    if "connection" in lowered or "timeout" in lowered:
        return (
            f"{message}\n\nCouldn't reach api.anthropic.com. Check network egress and that a "
            "credential is set (ANTHROPIC_API_KEY or `ant auth login`). Invoking tools from "
            "the left panel needs neither."
        )
    return message


async def run_turn(
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    model: str,
) -> AsyncIterator[dict[str, Any]]:
    """Drive the tool-use loop, emitting one event per thing the UI should show.

    A manual loop rather than the SDK tool runner: the whole point of this console is to
    show each tool call and its raw result as they happen, and the loop is where those
    events come from. The runner would hide exactly what we're here to watch.
    """
    from anthropic import AsyncAnthropic

    try:
        client = AsyncAnthropic()
    except BaseException as error:
        yield {"type": "error", "message": _credential_hint(_describe(error))}
        return

    for _ in range(MAX_TURNS):
        try:
            async with client.messages.stream(
                model=model,
                max_tokens=16000,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT},
                system=system,
                tools=tools,
                messages=history,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield {"type": "text", "text": delta.text}
                        elif delta.type == "thinking_delta":
                            yield {"type": "thinking", "text": delta.thinking}
                    elif event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            yield {"type": "tool_pending", "name": event.content_block.name}
                message = await stream.get_final_message()
        except BaseException as error:
            yield {"type": "error", "message": _credential_hint(_describe(error))}
            return

        # response.content verbatim -- thinking blocks must go back unedited.
        history.append({"role": "assistant", "content": message.content})
        yield {
            "type": "usage",
            "model": message.model,
            "stop_reason": message.stop_reason,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "cache_read": getattr(message.usage, "cache_read_input_tokens", None),
        }

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            yield {
                "type": "error",
                "message": "Claude declined this request"
                + (f" ({details.category})" if details and getattr(details, "category", None) else "")
                + ".",
            }
            return

        if message.stop_reason == "pause_turn":
            continue  # server-side tool paused mid-turn; re-send to resume

        if message.stop_reason != "tool_use":
            yield {"type": "done"}
            return

        results = []
        for block in message.content:
            if block.type != "tool_use":
                continue
            arguments = block.input if isinstance(block.input, dict) else {}
            yield {"type": "tool_use", "id": block.id, "name": block.name, "input": arguments}
            started = time.perf_counter()
            outcome = await call_tool(block.name, arguments)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            yield {
                "type": "tool_result",
                "id": block.id,
                "name": block.name,
                "ms": elapsed_ms,
                **outcome,
            }
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": outcome["text"],
                    "is_error": outcome["is_error"],
                }
            )
        # All results in one user message -- splitting them teaches Claude to stop
        # requesting tools in parallel.
        history.append({"role": "user", "content": results})

    yield {"type": "error", "message": f"stopped after {MAX_TURNS} tool-use rounds"}


# --- HTTP surface -------------------------------------------------------------------------


async def index(_request):
    # Read per request so editing index.html needs a refresh, not a restart.
    return HTMLResponse((HERE / "index.html").read_text(encoding="utf-8"))


async def status(_request):
    payload: dict[str, Any] = {
        "mcp_url": MCP_URL,
        "model": MODEL,
        "selectable_models": SELECTABLE_MODELS,
        "default_model": DEFAULT_SELECTABLE_MODEL,
        "effort": EFFORT,
        "anthropic_env_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "github_token": bool(os.environ.get("GITHUB_TOKEN")),
    }
    try:
        payload.update(await fetch_tools())
        payload["connected"] = True
    except BaseException as error:
        payload["connected"] = False
        payload["tools"] = []
        payload["error"] = _describe(error)
    return JSONResponse(payload)


async def invoke(request):
    """Call one tool directly, outside the conversation. A probe, not a chat turn."""
    body = await request.json()
    name = body.get("name")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    arguments = body.get("arguments") or {}
    if not isinstance(arguments, dict):
        return JSONResponse({"error": "arguments must be an object"}, status_code=400)
    started = time.perf_counter()
    outcome = await call_tool(name, arguments)
    return JSONResponse({**outcome, "ms": int((time.perf_counter() - started) * 1000)})


async def chat(request):
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)
    session_id = body.get("session") or "default"
    requested_model = body.get("model")
    if requested_model is not None and requested_model not in SELECTABLE_MODEL_IDS:
        return JSONResponse({"error": f"model must be one of {sorted(SELECTABLE_MODEL_IDS)}"}, status_code=400)
    model = requested_model or DEFAULT_SELECTABLE_MODEL

    try:
        discovered = await fetch_tools()
    except BaseException as error:
        return JSONResponse(
            {"error": f"cannot reach the MCP server at {MCP_URL} — {_describe(error)}"},
            status_code=502,
        )

    system = (discovered.get("instructions") or FALLBACK_SYSTEM) + CONSOLE_SYSTEM
    history = CONVERSATIONS.setdefault(session_id, [])
    history.append({"role": "user", "content": message})

    async def body_stream() -> AsyncIterator[str]:
        async for event in run_turn(history, discovered["tools"], system, model):
            yield _sse(event)

    return StreamingResponse(
        body_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def reset(request):
    body = await request.json() if await request.body() else {}
    CONVERSATIONS.pop(body.get("session") or "default", None)
    return JSONResponse({"ok": True})


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/status", status),
        Route("/api/tool", invoke, methods=["POST"]),
        Route("/api/chat", chat, methods=["POST"]),
        Route("/api/reset", reset, methods=["POST"]),
    ]
)


def main() -> None:
    import uvicorn

    print(f"builder-mcp console  ->  http://{HOST}:{PORT}")
    print(f"  MCP server: {MCP_URL}")
    print(f"  model:      {MODEL} (effort {EFFORT})")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  note: ANTHROPIC_API_KEY is unset; the SDK will use an `ant auth login` profile.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
