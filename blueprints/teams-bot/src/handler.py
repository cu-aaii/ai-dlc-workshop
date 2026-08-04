"""Teams bot: a Bot Framework front door for Microsoft Teams.

Runs as a container image (``blueprints/teams-bot/Dockerfile``, target
``teams-bot``, arm64) built by the pipeline's Build stage and deployed by digest.

Shape of a request: Azure Bot Service POSTs an activity to this function's URL. We prove the
activity is genuine, ask the model, post the answer back to Teams through the Bot Framework
API, and return 200. Synchronously, in one function.

Design constraints this code is downstream of:

- **All model traffic goes through Cornell's LiteLLM gateway.** Never Bedrock directly. That
  routing is what makes medium-risk data permissible, and it is a hard constraint, not a
  preference. The gateway is Anthropic-compatible, so this is a ``base_url`` on the ordinary
  Anthropic client -- ``messages.create()`` is unchanged.
- **Always return 200, including on a rejected token.** A 4xx makes Azure Bot Service retry a
  request that can never succeed, forever.
- **Retrieval is OPTIONAL.** With a ``KnowledgeBaseId`` configured, answers are grounded in
  passages retrieved from it; with none, the bot answers from its system prompt and says so.
  Retrieval uses ``Retrieve`` and nothing else -- the alternatives invoke a Bedrock model
  internally, which would move generation off the gateway. When nothing is retrieved the model is
  told so and refuses rather than inventing an answer.
- **Conversation history is not carried.** Teams hands over one activity and no history, so
  there is nothing to thread. Multi-turn arrives with AgentCore -- see below.

**Where AgentCore goes**, when step 2 lands: it replaces ``_ask()``. The model call moves out
of this Lambda into an AgentCore Runtime container and ``_ask()`` becomes an
``invoke_agent_runtime`` call, keyed on a session id derived from the conversation. That seam
is the only structural change -- no worker Lambda, no SSE, no queue. ``SYSTEM_PROMPT``,
``MODEL_ID`` and the gateway key move into the agent with it, and this function's role loses
its Secrets Manager grant in exchange for ``bedrock-agentcore:InvokeAgentRuntime``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import boto3
from anthropic import Anthropic

import botframework as bf

logging.basicConfig()
LOG = logging.getLogger("teams-bot")
LOG.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))
# Claude 5 models think by default. Effort is the lever for a chat-latency budget -- lower it
# rather than disabling thinking, which is more expensive in every sense and degrades output.
# Teams gives us 10-15 seconds before showing the user 504:GatewayTimeout, so this matters.
EFFORT = os.environ.get("EFFORT", "low")

# Bounds an inbound message, so one caller cannot drive an arbitrarily large or arbitrarily
# expensive request (SECURITY-05).
MAX_MESSAGE_CHARS = 4000
MAX_BODY_BYTES = 256 * 1024

# Bedrock caps a retrieval query at 10,000 characters and rejects longer ones outright.
MAX_QUERY_CHARS = 10_000
RETRIEVAL_RESULTS = 5

GENERIC_FAILURE = (
    "Sorry, something went wrong answering that. If you report it, quote this reference: {ref}"
)

_ssm = boto3.client("ssm")
_secrets = boto3.client("secretsmanager")


def _param(name: str, default: str = "") -> str:
    """Read one SSM parameter at cold start.

    Configuration is routed through SSM rather than read straight from an environment variable
    because deployment_create drops a manifest's `inputs` on the floor (#15 finding 2), so SSM
    is the only surface a builder-supplied value can reach. Note this does NOT make the value
    safely editable out of band: the parameter's Value comes from a stack parameter, so a deploy
    touching that resource reasserts it. A real change is a PR.
    """
    if not name:
        return default
    try:
        return _ssm.get_parameter(Name=name)["Parameter"]["Value"]
    except Exception as exc:
        LOG.warning("could not read %s, using default: %s", name, exc)
        return default


def _secret(arn: str) -> str:
    if not arn:
        return ""
    return _secrets.get_secret_value(SecretId=arn)["SecretString"]


class _Config:
    """Resolved once per cold start. Fails loudly on anything genuinely required."""

    def __init__(self) -> None:
        self.bot_app_id = os.environ.get("BOT_APP_ID", "")
        self.bot_tenant_id = os.environ.get("BOT_TENANT_ID", "")
        self.deployment_id = os.environ.get("DEPLOYMENT_ID", "unknown")
        self.gateway_base_url = os.environ.get("GATEWAY_BASE_URL", "")
        self.knowledge_base_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
        self.model_id = _param(os.environ.get("MODEL_ID_PARAM", ""), "claude-haiku-4-5")
        # `or`, not a .get default: the stack passes GREETING_TEXT through unconditionally, so
        # an unset parameter arrives as an empty string rather than as a missing key -- and a
        # .get default would then be skipped, greeting people with nothing.
        self.greeting = os.environ.get("GREETING_TEXT") or (
            "Hi! Ask me a question and I'll do my best to answer it."
        )
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """An S3-hosted prompt wins when configured, because a syllabus does not fit in a
        4096-character CloudFormation parameter (FR-3a)."""
        bucket = os.environ.get("SYSTEM_PROMPT_S3_BUCKET", "")
        key = os.environ.get("SYSTEM_PROMPT_S3_KEY", "")
        if bucket and key:
            try:
                body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
                return body.decode("utf-8")
            except Exception as exc:
                # Falling back is right: a missing prompt object should degrade the bot's
                # knowledge, not take it off the air mid-demo.
                LOG.error("could not load system prompt from s3://%s/%s: %s", bucket, key, exc)
        return DEFAULT_SYSTEM_PROMPT


DEFAULT_SYSTEM_PROMPT = """You are an assistant answering questions in Microsoft Teams for a \
Cornell University unit.

Answer clearly and directly, at the level of someone encountering the topic for the first time.
Lead with the answer, then the reasoning.

Reference material is supplied with each question when it is available. Answer from that material,
and quote a specific figure, date or policy only when the material states it. When the material does
not cover what was asked, say so and point the person at a human who would know. Never guess: a
confident wrong answer about a real Cornell process is worse than no answer.

Keep responses short. You are answering in a Teams chat, not writing a document. Skip preamble and
do not restate the question.

You cannot approve exceptions, change records, or commit anyone to anything. Refer those onward."""

# This default is deliberately GENERIC. The blueprint is a template, not a bot (FR-1): what any
# given deployment does is set by the SystemPrompt parameter, which the Builder writes into a
# deployment repo as a reviewable file. A course assistant, an IT helpdesk and an HR FAQ bot are
# the same blueprint with different prompts -- so nothing course-specific belongs in here.


class _Runtime:
    """Config, secrets and clients, resolved on first invocation rather than at import.

    **Deliberately lazy.** Anything that runs at module scope runs during Lambda INIT, and an
    exception there fails the invocation *before* `handler` is reached -- so the function
    returns a 5xx no matter what `handler` promises, and Azure Bot Service retries a request
    that can never succeed, forever (FR-10). Building here instead puts every failure mode
    inside the handler's own try/except, where it becomes a logged 200.
    """

    def __init__(self) -> None:
        self.config = _Config()
        self.teams = bf.BotFrameworkClient(
            bf.TokenProvider(
                tenant_id=self.config.bot_tenant_id,
                client_id=self.config.bot_app_id,
                client_secret=_secret(os.environ.get("BOT_CLIENT_SECRET_ARN", "")),
            )
        )
        # Retrieval only -- this client never generates. See _retrieve.
        self.knowledge = boto3.client("bedrock-agent-runtime")
        # The gateway, not Bedrock. Anthropic-compatible, so only the construction differs.
        self.model = Anthropic(
            base_url=self.config.gateway_base_url,
            api_key=_secret(os.environ.get("GATEWAY_API_KEY_ARN", "")) or "unset",
        )


_RUNTIME: _Runtime | None = None


def _runtime() -> _Runtime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = _Runtime()
    return _RUNTIME


def _retrieve(rt: _Runtime, question: str) -> list[str]:
    """Fetch reference passages relevant to the question, if a knowledge base is configured.

    **`Retrieve`, never `RetrieveAndGenerate` or `AgenticRetrieveStream.`** Those two invoke a
    Bedrock foundation model internally, which would put generation outside Cornell's LiteLLM
    gateway and break the routing mandate. `Retrieve` makes no model call: it returns passages,
    and every generated token still comes from the gateway.

    Best effort by design. A knowledge base that is slow or unreachable should cost the asker a
    grounded answer, not their answer -- the model is told when it has no passages and refuses on
    that basis rather than inventing one.
    """
    if not rt.config.knowledge_base_id:
        return []
    try:
        response = rt.knowledge.retrieve(
            knowledgeBaseId=rt.config.knowledge_base_id,
            # Hard service cap is 10,000 characters. Truncating deliberately here beats a
            # ValidationException on a long question.
            retrievalQuery={"text": question[:MAX_QUERY_CHARS]},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": RETRIEVAL_RESULTS}
            },
        )
    except Exception as exc:
        LOG.error("retrieval failed, answering ungrounded: %s", exc)
        return []
    passages = [
        text
        for result in response.get("retrievalResults", [])
        if (text := (result.get("content") or {}).get("text", "").strip())
    ]
    LOG.info("retrieved %d passage(s)", len(passages))
    return passages


def _ask(rt: _Runtime, question: str) -> str:
    """Answer one question, grounded in retrieved material when any is available.

    **This is the seam AgentCore replaces** -- see the module docstring. Retrieval lives inside
    it rather than in the caller on purpose: an agent should own its own grounding, so when this
    becomes an `invoke_agent_runtime` call both the retrieval and the model call move into the
    agent together and the front door stays a front door.
    """
    passages = _retrieve(rt, question)
    if passages:
        context = "\n\n".join(
            f"<passage {i}>\n{text}\n</passage {i}>" for i, text in enumerate(passages, 1)
        )
        grounding = (
            "Reference material relevant to this question is below. Answer using ONLY these "
            "passages. If they do not contain the answer, say so and point the person at someone "
            f"who would know -- do not fall back on general knowledge.\n\n{context}"
        )
    else:
        grounding = (
            "No reference material was retrieved for this question. Say you don't have that "
            "information and point the person at someone who would know. Do not guess."
        )

    reply = rt.model.messages.create(
        model=rt.config.model_id,
        max_tokens=MAX_TOKENS,
        system=f"{rt.config.system_prompt}\n\n{grounding}",
        messages=[{"role": "user", "content": question}],
        # effort rides in extra_body so this works on any SDK version, typed or not. Sampling
        # parameters (temperature, top_p, top_k) are rejected by Claude 5 models -- steer with
        # the system prompt instead.
        extra_body={"output_config": {"effort": EFFORT}},
    )
    return "".join(b.text for b in reply.content if b.type == "text").strip()


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("request body too large")
    payload = json.loads(raw) if raw else {}
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    return payload


def _headers(event: dict[str, Any]) -> dict[str, str]:
    """Function URL headers arrive lowercased, but do not rely on it."""
    return {k.lower(): v for k, v in (event.get("headers") or {}).items()}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Always returns 200. See the module docstring for why that is not laziness."""
    correlation = "unknown"
    try:
        rt = _runtime()
        activity_json = _body(event)
        activity = bf.parse_activity(activity_json)
        # The activity id is the correlation id: it already exists, is stable across retries,
        # and is what the user is shown on failure -- so a quoted reference leads straight to
        # every log line for that request.
        correlation = activity.log_id

        try:
            bf.validate_activity(
                _headers(event).get("authorization"), activity_json, rt.config.bot_app_id
            )
        except bf.ValidationError as exc:
            # The reason is logged and never returned. This is the SECURITY-02 compensating
            # control -- a Function URL has no access log of its own.
            LOG.warning(
                "rejected activity: correlation=%s type=%s reason=%s",
                correlation,
                activity.activity_type,
                exc,
            )
            return {"statusCode": 200}

        LOG.info(
            "accepted activity: correlation=%s type=%s conversation=%s",
            correlation,
            activity.activity_type,
            activity.conversation_type,
        )
        _dispatch(rt, activity)
        return {"statusCode": 200}

    except Exception as exc:
        LOG.exception("unhandled failure: correlation=%s error=%s", correlation, exc)
        return {"statusCode": 200}


def _dispatch(rt: _Runtime, activity: bf.Activity) -> None:
    """Route on activity type. Unknown types are accepted and ignored (FR-12)."""
    if activity.activity_type == "conversationUpdate":
        # Filtered on the 28: bot prefix inside parse_activity, or the bot greets itself when
        # it is the member being added.
        if activity.human_joined:
            rt.teams.send(activity, rt.config.greeting)
        return

    if activity.activity_type != "message":
        return

    if not activity.text:
        # An attachment, a reaction, or a card action. Nothing to answer.
        return

    question = activity.text[:MAX_MESSAGE_CHARS]
    rt.teams.typing(activity)
    try:
        rt.teams.reply(activity, _ask(rt, question))
    except Exception as exc:
        LOG.exception("answer failed: correlation=%s error=%s", activity.log_id, exc)
        # Best effort: if this fails too, the outer handler logs it and still returns 200.
        rt.teams.reply(activity, GENERIC_FAILURE.format(ref=activity.log_id))
