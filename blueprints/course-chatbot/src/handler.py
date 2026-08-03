"""Course chatbot: a Lambda behind a Function URL that answers questions with Claude.

Runs as a container image (root Dockerfile target course-chatbot) built by the pipeline's
Build stage and deployed by digest. Design constraints this code is downstream of:

- Stateless. The conversation lives in the client, which passes prior turns back on every
  request. Nothing here reads session state, so the function scales without affinity.
- The caller holds no model credentials. Bedrock is reached with the Lambda execution
  role's own AWS credentials, so there is no API key anywhere in this repo.
- Answers are grounded only in the system prompt. Retrieval over course materials is the
  Knowledge Base work (see the blueprint README); this deliberately has no retrieval, and
  says so rather than inventing course specifics.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

# The Bedrock Messages API client. The SDK renamed it AnthropicBedrock ->
# AnthropicBedrockMantle when the Messages-API endpoint became the recommended path, so
# support both and let the pinned version float.
try:
    from anthropic import AnthropicBedrockMantle as _BedrockClient
except ImportError:  # pragma: no cover
    from anthropic import AnthropicBedrock as _BedrockClient

LOG = logging.getLogger()
LOG.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# AWS_REGION is set by the Lambda runtime and cannot be overridden in the function's
# environment, so a separate variable is what lets the model live in another region.
REGION = os.environ.get("BEDROCK_REGION") or os.environ["AWS_REGION"]
MODEL_ID = os.environ["MODEL_ID"]
COURSE_NAME = os.environ.get("COURSE_NAME", "this course")
TRANSCRIPT_BUCKET = os.environ.get("TRANSCRIPT_BUCKET", "")
DEPLOYMENT_ID = os.environ.get("DEPLOYMENT_ID", "unknown")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4096"))
# Claude 5 models think by default. Effort is the lever for a chat-latency budget --
# lower it rather than disabling thinking, which is the more expensive control in every
# sense and degrades output.
EFFORT = os.environ.get("EFFORT", "low")

# Cap on client-supplied history, so one caller can't drive an arbitrarily large (and
# arbitrarily expensive) request. Turns are user/assistant pairs.
MAX_HISTORY_TURNS = 20
MAX_MESSAGE_CHARS = 8000

SYSTEM_PROMPT = f"""You are a teaching assistant for {COURSE_NAME} at Cornell University.

Answer students' questions about the course clearly and directly, at the level of someone
taking it for the first time. Lead with the answer, then the reasoning.

You do not have access to this course's syllabus, assignments, grades, or any other
course materials. When a question depends on specifics you were not given -- a due date,
what is on an exam, an individual student's standing -- say you don't have that and point
the student at the course staff or the course site. Never guess at a date, a policy, or a
grade.

Keep responses focused and brief. Skip preamble and restating the question. When asked to
explain something, give a high-level summary first and go deeper only if asked.

You cannot change grades, grant extensions, or make policy exceptions. Refer those to the
course staff."""

_bedrock = _BedrockClient(aws_region=REGION)
_s3 = boto3.client("s3")


class BadRequest(Exception):
    """The caller's payload is unusable; surfaced as a 400 rather than a stack trace."""


def _parse_request(event: dict[str, Any]) -> tuple[str, str, list[dict[str, str]]]:
    """Pull message, conversation id and prior turns out of a Function URL event."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise BadRequest(f"body is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BadRequest("body must be a JSON object")

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise BadRequest("'message' is required and must be a non-empty string")
    if len(message) > MAX_MESSAGE_CHARS:
        raise BadRequest(f"'message' exceeds {MAX_MESSAGE_CHARS} characters")

    conversation_id = payload.get("conversation_id") or str(uuid.uuid4())
    if not isinstance(conversation_id, str) or len(conversation_id) > 64:
        raise BadRequest("'conversation_id' must be a string of at most 64 characters")

    history = payload.get("history") or []
    if not isinstance(history, list):
        raise BadRequest("'history' must be a list of {role, content} objects")
    turns: list[dict[str, str]] = []
    for entry in history[-(MAX_HISTORY_TURNS * 2) :]:
        if (
            not isinstance(entry, dict)
            or entry.get("role") not in {"user", "assistant"}
            or not isinstance(entry.get("content"), str)
        ):
            raise BadRequest("each history entry needs role 'user' or 'assistant' and string content")
        turns.append({"role": entry["role"], "content": entry["content"]})

    return message, conversation_id, turns


def _ask(turns: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
    """Send the conversation to Claude and return its reply plus token usage."""
    reply = _bedrock.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=turns,
        # effort rides in extra_body so this works on any SDK version, typed or not.
        # Sampling parameters (temperature, top_p, top_k) are rejected by Claude 5
        # models -- steer with the system prompt instead.
        extra_body={"output_config": {"effort": EFFORT}},
    )
    # Thinking is on by default and its blocks carry no text unless display is set, so
    # take the text blocks and ignore everything else rather than indexing content[0].
    text = "".join(block.text for block in reply.content if block.type == "text").strip()
    usage = {
        "input_tokens": reply.usage.input_tokens,
        "output_tokens": reply.usage.output_tokens,
    }
    return text, usage


def _record(conversation_id: str, question: str, answer: str, usage: dict[str, int]) -> None:
    """Append the exchange to the transcript bucket. Best effort -- never fails a reply."""
    if not TRANSCRIPT_BUCKET:
        return
    now = datetime.now(timezone.utc)
    key = (
        f"conversations/{now:%Y/%m/%d}/{conversation_id}/"
        f"{now:%H%M%S}-{uuid.uuid4().hex[:8]}.json"
    )
    try:
        _s3.put_object(
            Bucket=TRANSCRIPT_BUCKET,
            Key=key,
            ContentType="application/json",
            Body=json.dumps(
                {
                    "deployment_id": DEPLOYMENT_ID,
                    "conversation_id": conversation_id,
                    "asked_at": now.isoformat(),
                    "model_id": MODEL_ID,
                    "question": question,
                    "answer": answer,
                    "usage": usage,
                }
            ).encode("utf-8"),
        )
    except Exception:  # noqa: BLE001 -- a transcript failure must not cost the student a reply
        LOG.exception("could not write transcript to s3://%s/%s", TRANSCRIPT_BUCKET, key)


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Function URL entry point: one question in, one answer out."""
    try:
        message, conversation_id, history = _parse_request(event)
    except BadRequest as exc:
        return _response(400, {"error": str(exc)})

    turns = [*history, {"role": "user", "content": message}]
    try:
        answer, usage = _ask(turns)
    except Exception:  # noqa: BLE001 -- the caller gets a narrative, the log gets the trace
        LOG.exception("model call failed for conversation %s", conversation_id)
        return _response(
            502,
            {
                "error": "the assistant is unavailable right now; please try again shortly",
                "conversation_id": conversation_id,
            },
        )

    _record(conversation_id, message, answer, usage)
    return _response(
        200,
        {
            "conversation_id": conversation_id,
            "answer": answer,
            "model_id": MODEL_ID,
            "usage": usage,
        },
    )
