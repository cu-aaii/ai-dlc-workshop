"""Tests for the Lambda front door: the always-200 contract, grounding, and routing.

Four things this module protects, all stated in ``handler``'s own docstrings:

- **``handler()`` always returns ``{"statusCode": 200}``**, no matter what goes wrong upstream
  of it -- a rejected token, a malformed body, an oversized body, or an outright bug several
  calls deep. A 4xx or 5xx here makes Azure Bot Service retry a request that can never succeed,
  forever (FR-10). This is the single most important property in the module, so it gets the
  widest spread of inputs.
- **Retrieval is best-effort.** ``_retrieve`` must return ``[]`` rather than raise when there is
  no knowledge base configured or when the retrieval call itself fails -- a slow or unreachable
  knowledge base should cost the student a grounded answer, not their answer entirely.
- **``_dispatch`` routes correctly and only where it should**: a human joining gets the greeting,
  the bot greeting itself does not, a real question gets asked and answered, and anything with
  nothing to say (no text, an unknown activity type) is silently ignored.
- **The greeting has a safe fallback.** An unset ``GREETING_TEXT`` must not greet a student with
  an empty string.

No AWS credentials and no network are needed. ``handler`` builds real boto3 clients and a real
``Anthropic`` client at runtime (lazily, inside ``_Runtime`` -- see its docstring on why), so
these tests never let a real ``_Runtime`` get built: ``handler._RUNTIME`` is monkeypatched to a
small stub carrying `.config`, `.teams`, `.model` and `.knowledge` doubles instead. Only
``AWS_REGION``/``AWS_DEFAULT_REGION`` and ``GATEWAY_BASE_URL`` are set, because ``handler``
reads its environment at import time to build the two module-scope boto3 clients (construction
alone needs no credentials, just a region).

Run:
    uv run --quiet --python 3.13 --with 'PyJWT[crypto]>=2.8,<3' --with 'anthropic>=0.92,<2' \
        --with boto3 --with pytest pytest blueprints/teams-bot/tests -q
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# handler.py reads these at import time (module-scope boto3 clients need a region). Set before
# importing it.
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["GATEWAY_BASE_URL"] = "https://gateway.example.edu"

import botframework as bf  # noqa: E402
import handler  # noqa: E402

BOT_APP_ID = "11111111-2222-3333-4444-555555555555"
SERVICE_URL = "https://smba.trafficmanager.net/amer/"


# --- test doubles ----------------------------------------------------------------------------
#
# Lightweight stand-ins for the four things _Runtime carries, so no boto3 call and no Anthropic
# call is ever made.


class _StubConfig:
    def __init__(self, **overrides):
        self.bot_app_id = BOT_APP_ID
        self.bot_tenant_id = "tenant-1"
        self.deployment_id = "dep-1"
        self.gateway_base_url = "https://gateway.example.edu"
        self.knowledge_base_id = "kb-1"
        self.model_id = "claude-haiku-4-5"
        self.max_tokens = handler.DEFAULT_MAX_TOKENS
        self.greeting = "Hi! I'm the assistant for CS 1110. Ask me anything about it."
        self.system_prompt = "You are a teaching assistant for CS 1110."
        for key, value in overrides.items():
            setattr(self, key, value)


class _StubTeams:
    """Records every outbound call instead of speaking HTTP to Microsoft."""

    def __init__(self):
        self.sent: list[tuple[object, str]] = []
        self.replies: list[tuple[object, str]] = []
        self.typing_calls: list[object] = []

    def send(self, activity, text):
        self.sent.append((activity, text))

    def reply(self, activity, text):
        self.replies.append((activity, text))

    def typing(self, activity):
        self.typing_calls.append(activity)


class _StubKnowledge:
    """Stands in for the bedrock-agent-runtime client's ``retrieve`` call."""

    def __init__(self, response=None, exc=None):
        self._response = response if response is not None else {"retrievalResults": []}
        self._exc = exc
        self.calls: list[dict] = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


class _TextBlock:
    def __init__(self, text, type="text"):  # noqa: A002 - mirrors the Anthropic SDK's shape
        self.type = type
        self.text = text


class _StubAnthropicResponse:
    def __init__(self, text, blocks=None):
        # `blocks` overrides `text` entirely, so a test can hand back a response carrying no
        # text block at all -- what the SDK returns when max_tokens is spent while thinking.
        self.content = blocks if blocks is not None else [_TextBlock(text)]


class _StubMessages:
    def __init__(self, reply_text="An answer.", blocks=None):
        self.reply_text = reply_text
        self.blocks = blocks
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubAnthropicResponse(self.reply_text, self.blocks)


class _StubModel:
    def __init__(self, reply_text="An answer.", blocks=None):
        self.messages = _StubMessages(reply_text, blocks)


class _StubRuntime:
    def __init__(self, config=None, teams=None, knowledge=None, model=None):
        self.config = config if config is not None else _StubConfig()
        self.teams = teams if teams is not None else _StubTeams()
        self.knowledge = knowledge if knowledge is not None else _StubKnowledge()
        self.model = model if model is not None else _StubModel()


@pytest.fixture
def stub_runtime(monkeypatch):
    """Install a stub in place of the real, lazily-built ``_Runtime``.

    ``handler._runtime()`` only builds a real ``_Runtime`` when ``handler._RUNTIME`` is still
    ``None``, so pre-setting it here means the real one -- with its live boto3 and Anthropic
    clients -- is never constructed.
    """
    rt = _StubRuntime()
    monkeypatch.setattr(handler, "_RUNTIME", rt)
    return rt


# --- handler(): always 200, no matter what -----------------------------------------------


def test_handler_returns_200_when_the_activity_is_rejected(stub_runtime):
    """No Authorization header is the simplest rejection -- and needs no JWKS/network to prove."""
    event = {
        "body": json.dumps(
            {"id": "a1", "type": "message", "text": "hi", "serviceUrl": SERVICE_URL}
        )
    }
    assert handler.handler(event, None) == {"statusCode": 200}
    assert stub_runtime.teams.replies == []


def test_handler_returns_200_for_a_malformed_json_body(stub_runtime):
    assert handler.handler({"body": "{not valid json"}, None) == {"statusCode": 200}


def test_handler_returns_200_for_a_completely_empty_event(stub_runtime):
    assert handler.handler({}, None) == {"statusCode": 200}


def test_handler_returns_200_for_a_body_over_the_size_limit(stub_runtime):
    event = {"body": "x" * (handler.MAX_BODY_BYTES + 1)}
    assert handler.handler(event, None) == {"statusCode": 200}


def test_handler_returns_200_when_something_deeper_raises_unexpectedly(stub_runtime, monkeypatch):
    """The outer try/except is the actual safety net -- prove it catches a bug, not just the
    rejection paths that are handled explicitly."""
    monkeypatch.setattr(bf, "validate_activity", lambda *a, **k: None)

    def _boom(rt, activity):
        raise RuntimeError("something deeper broke")

    monkeypatch.setattr(handler, "_dispatch", _boom)
    event = {
        "body": json.dumps(
            {"id": "a1", "type": "message", "text": "hi", "serviceUrl": SERVICE_URL}
        )
    }
    assert handler.handler(event, None) == {"statusCode": 200}


# --- _body() ---------------------------------------------------------------------------------


def test_body_decodes_base64_encoded_content():
    raw = json.dumps({"type": "message"})
    event = {"body": base64.b64encode(raw.encode("utf-8")).decode("ascii"), "isBase64Encoded": True}
    assert handler._body(event) == {"type": "message"}


def test_body_rejects_a_payload_over_the_size_limit():
    event = {"body": "x" * (handler.MAX_BODY_BYTES + 1)}
    with pytest.raises(ValueError):
        handler._body(event)


def test_body_rejects_non_object_json():
    with pytest.raises(ValueError):
        handler._body({"body": "[1, 2, 3]"})


# --- _retrieve() -------------------------------------------------------------------------------


def test_retrieve_returns_nothing_when_no_knowledge_base_is_configured():
    rt = _StubRuntime(config=_StubConfig(knowledge_base_id=""))
    assert handler._retrieve(rt, "when is the midterm?") == []


def test_retrieve_returns_nothing_and_does_not_raise_when_the_call_fails():
    rt = _StubRuntime(knowledge=_StubKnowledge(exc=RuntimeError("knowledge base unreachable")))
    assert handler._retrieve(rt, "when is the midterm?") == []


def test_retrieve_returns_passage_text_on_success():
    response = {"retrievalResults": [{"content": {"text": "The midterm is on Friday."}}]}
    rt = _StubRuntime(knowledge=_StubKnowledge(response=response))
    assert handler._retrieve(rt, "when is the midterm?") == ["The midterm is on Friday."]


def test_retrieve_filters_out_blank_and_whitespace_only_passages():
    response = {
        "retrievalResults": [
            {"content": {"text": "A real passage."}},
            {"content": {"text": "   "}},
            {"content": {"text": ""}},
            {"content": {}},
        ]
    }
    rt = _StubRuntime(knowledge=_StubKnowledge(response=response))
    assert handler._retrieve(rt, "question") == ["A real passage."]


def test_retrieve_truncates_the_query_to_max_query_chars():
    knowledge = _StubKnowledge()
    rt = _StubRuntime(knowledge=knowledge)
    question = "a" * (handler.MAX_QUERY_CHARS + 500)

    handler._retrieve(rt, question)

    sent_query = knowledge.calls[0]["retrievalQuery"]["text"]
    assert sent_query == question[: handler.MAX_QUERY_CHARS]
    assert len(sent_query) == handler.MAX_QUERY_CHARS


# --- _dispatch() -------------------------------------------------------------------------------


def test_conversation_update_with_a_human_member_sends_the_greeting():
    rt = _StubRuntime()
    activity = bf.parse_activity(
        {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "29:a-person"}],
            "conversation": {"id": "conv-1"},
            "serviceUrl": SERVICE_URL,
        }
    )
    handler._dispatch(rt, activity)
    assert rt.teams.sent == [(activity, rt.config.greeting)]


def test_conversation_update_with_only_the_bot_joining_sends_nothing():
    rt = _StubRuntime()
    activity = bf.parse_activity(
        {"type": "conversationUpdate", "membersAdded": [{"id": "28:the-bot"}]}
    )
    handler._dispatch(rt, activity)
    assert rt.teams.sent == []


def test_message_with_text_asks_the_model_and_replies_with_its_answer():
    rt = _StubRuntime(model=_StubModel(reply_text="The midterm is on Friday."))
    activity = bf.parse_activity(
        {
            "id": "a1",
            "type": "message",
            "text": "When is the midterm?",
            "conversation": {"id": "conv-1"},
            "serviceUrl": SERVICE_URL,
        }
    )
    handler._dispatch(rt, activity)
    assert rt.teams.replies == [(activity, "The midterm is on Friday.")]


def test_message_with_no_text_does_nothing():
    rt = _StubRuntime()
    activity = bf.parse_activity({"id": "a1", "type": "message"})
    handler._dispatch(rt, activity)
    assert rt.teams.replies == []
    assert rt.teams.typing_calls == []


def test_unknown_activity_type_does_nothing():
    rt = _StubRuntime()
    activity = bf.parse_activity({"id": "a1", "type": "reactionAdded"})
    handler._dispatch(rt, activity)
    assert rt.teams.sent == []
    assert rt.teams.replies == []


# --- _Config greeting fallback -----------------------------------------------------------------


def _clear_ssm_and_s3_backed_env(monkeypatch):
    """These would trigger a real SSM/S3 call if set, and the fallback tests care only about
    GREETING_TEXT -- keep the rest of _Config's inputs at their no-network defaults."""
    for name in ("MODEL_ID_PARAM", "SYSTEM_PROMPT_S3_BUCKET", "SYSTEM_PROMPT_S3_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_empty_greeting_env_falls_back_to_a_generic_greeting(monkeypatch):
    _clear_ssm_and_s3_backed_env(monkeypatch)
    monkeypatch.setenv("GREETING_TEXT", "")

    config = handler._Config()

    # Generic on purpose: this blueprint is not course-specific (FR-1).
    assert config.greeting == "Hi! Ask me a question and I'll do my best to answer it."
    assert "course" not in config.greeting.lower()


def test_nonempty_greeting_env_is_used_verbatim(monkeypatch):
    _clear_ssm_and_s3_backed_env(monkeypatch)
    monkeypatch.setenv("GREETING_TEXT", "Welcome! Ask me anything about the course.")

    config = handler._Config()

    assert config.greeting == "Welcome! Ask me anything about the course."


# --- the model call is bounded by the Teams ack budget -----------------------------------------
#
# The gateway call is the highest-latency thing in a request, and the SDK's own default timeout
# is ten minutes with its own retries on top. Left at that default, a slow gateway means the
# caller sees 504:GatewayTimeout while this Lambda keeps running, keeps billing, and then posts
# a reply to a request the caller already abandoned. These two tests are what keep the bound
# explicit rather than inherited.


def _runtime_with_no_aws_calls(monkeypatch):
    """A real ``_Runtime``, built without touching SSM, S3 or Secrets Manager.

    Every unset ARN short-circuits inside ``_secret``, and ``TokenProvider``/``Anthropic``/the
    boto3 clients are all network-free to construct -- so this exercises the real constructor,
    not a double of it. That matters here: the point is what the production code passes to
    ``Anthropic()``.
    """
    _clear_ssm_and_s3_backed_env(monkeypatch)
    for name in ("BOT_CLIENT_SECRET_ARN", "GATEWAY_API_KEY_ARN"):
        monkeypatch.delenv(name, raising=False)
    return handler._Runtime()


def test_the_model_client_is_given_an_explicit_timeout(monkeypatch):
    rt = _runtime_with_no_aws_calls(monkeypatch)

    assert rt.model.timeout == handler.MODEL_TIMEOUT_SECONDS
    # Teams shows the user 504:GatewayTimeout at 10-15s. A bound outside that window is not a
    # bound -- it just moves the failure somewhere the user cannot be told about it.
    assert handler.MODEL_TIMEOUT_SECONDS <= 15


def test_the_model_client_does_not_retry(monkeypatch):
    """Two attempts cannot both fit the ack budget, so a retry guarantees the 504 it is meant to
    avoid. One attempt that fails inside budget becomes a reply the user can actually read."""
    rt = _runtime_with_no_aws_calls(monkeypatch)

    assert rt.model.max_retries == 0


# --- max_tokens is parsed lazily, never at import ----------------------------------------------


def test_a_bad_max_tokens_value_does_not_break_import():
    """The regression this guards is specific: an ``int()`` at module scope runs during Lambda
    INIT, and an exception there fails the invocation *before* ``handler`` is reached -- so the
    function returns 5xx whatever ``handler`` promises, and Azure Bot Service retries a request
    that can never succeed, forever (FR-10). ``_Runtime`` is lazy for exactly this reason; the
    parse has to be too.
    """
    os.environ["MAX_TOKENS"] = "twelve"
    try:
        importlib.reload(handler)
    finally:
        # Restore before monkeypatch-free teardown, so the module other tests hold is clean.
        del os.environ["MAX_TOKENS"]
        importlib.reload(handler)


def test_a_bad_max_tokens_value_falls_back_to_the_default(monkeypatch):
    _clear_ssm_and_s3_backed_env(monkeypatch)
    monkeypatch.setenv("MAX_TOKENS", "twelve")

    assert handler._Config().max_tokens == handler.DEFAULT_MAX_TOKENS


def test_a_valid_max_tokens_value_is_used(monkeypatch):
    _clear_ssm_and_s3_backed_env(monkeypatch)
    monkeypatch.setenv("MAX_TOKENS", "2048")

    assert handler._Config().max_tokens == 2048


# --- an answer with no text is a failure, not a blank message -----------------------------------


def test_an_empty_answer_replies_with_the_generic_failure():
    """A blank Teams bubble surfaces nothing to the user and nothing to CloudWatch. Route it
    through the same reply an exception gets, so the failure is both visible and quotable."""
    rt = _StubRuntime(model=_StubModel(reply_text="   "))
    activity = bf.parse_activity(
        {
            "id": "a1",
            "type": "message",
            "text": "When is the midterm?",
            "conversation": {"id": "conv-1"},
            "serviceUrl": SERVICE_URL,
        }
    )

    handler._dispatch(rt, activity)

    assert rt.teams.replies == [
        (activity, handler.GENERIC_FAILURE.format(ref=activity.log_id))
    ]


def test_a_response_carrying_no_text_block_replies_with_the_generic_failure():
    """What the SDK returns when max_tokens is spent while thinking: content, but no text in it."""
    rt = _StubRuntime(model=_StubModel(blocks=[_TextBlock("", type="thinking")]))
    activity = bf.parse_activity(
        {
            "id": "a1",
            "type": "message",
            "text": "When is the midterm?",
            "conversation": {"id": "conv-1"},
            "serviceUrl": SERVICE_URL,
        }
    )

    handler._dispatch(rt, activity)

    assert rt.teams.replies == [
        (activity, handler.GENERIC_FAILURE.format(ref=activity.log_id))
    ]
