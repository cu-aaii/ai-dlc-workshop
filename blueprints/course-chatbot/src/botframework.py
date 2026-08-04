"""Bot Framework plumbing: inbound trust, outbound tokens, and replies.

Kept separate from ``handler`` and free of any course-chatbot import, so extracting it for a
future Slack or web front end is a file move rather than a refactor. Security-critical logic
is isolated here rather than scattered through the handler (SECURITY-11).

Three things in this module have already been got wrong once, in the n8n prototype, and are
the reason it exists as its own file:

1. The emitter's claim is ``serviceurl`` -- all lowercase. The prototype read
   ``payload.serviceUrl`` (camelCase), which is always ``None``, and a truthiness guard
   turned the check into a silent skip. **An absent claim is a FAILURE, not a pass.** It is
   the control that stops an attacker holding a valid token from redirecting our replies.
2. ``serviceUrl`` is normalised exactly once, here, and the same value feeds both the claim
   comparison and reply-URL construction -- so the two cannot disagree. The prototype relied
   on an undocumented trailing slash.
3. The signing algorithm is pinned. ``header.alg`` is attacker-controlled and never read.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

LOG = logging.getLogger(__name__)

# The Bot Framework's public key set, and the only issuer we accept.
JWKS_URL = "https://login.botframework.com/v1/.well-known/keys"
EXPECTED_ISSUER = "https://api.botframework.com"
BOT_SCOPE = "https://api.botframework.com/.default"

# Clock skew tolerated on exp/nbf, in seconds (FR-8).
LEEWAY_SECONDS = 300

# Bot identities are prefixed 28: in Bot Framework. Used to tell our own membership events
# apart from a human's -- without this filter the bot greets itself on install.
BOT_ID_PREFIX = "28:"

_HTTP_TIMEOUT = 10

# PyJWKClient caches the key set and re-fetches on a `kid` it has not seen, which is the
# refresh-on-miss behaviour FR-15 asks for. Constructed once per cold start.
_jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)


class ValidationError(Exception):
    """The request is not a genuine Bot Framework activity. Reason is logged, never returned."""


def normalize_service_url(service_url: str) -> str:
    """Strip trailing slashes. Call once; reuse the result everywhere."""
    return (service_url or "").rstrip("/")


def validate_activity(auth_header: str | None, activity: dict[str, Any], bot_app_id: str) -> None:
    """Prove the activity came from Azure Bot Service. Raises ValidationError if not.

    Fails closed: every unexpected condition raises, including a missing claim.
    """
    if not bot_app_id:
        # No configured audience means nothing can be verified against anything. Refusing is
        # the only safe reading -- treating it as "validation disabled" would turn a
        # misconfigured deployment into an open relay.
        raise ValidationError("BOT_APP_ID is not configured; refusing all requests")

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise ValidationError("missing or malformed Authorization header")
    token = auth_header.split(" ", 1)[1].strip()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
    except Exception as exc:  # PyJWKClient raises several distinct types
        raise ValidationError(f"no usable signing key: {exc}") from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            # Pinned. Never derived from the token's own header.
            algorithms=["RS256"],
            audience=bot_app_id,
            issuer=EXPECTED_ISSUER,
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError as exc:
        raise ValidationError(f"token rejected: {exc}") from exc

    # The serviceurl correlation. Lowercase 'u' -- see this module's docstring.
    claimed = claims.get("serviceurl")
    if claimed is None:
        raise ValidationError("token carries no serviceurl claim")
    if normalize_service_url(str(claimed)) != normalize_service_url(activity.get("serviceUrl", "")):
        raise ValidationError("serviceurl claim does not match the activity's serviceUrl")


@dataclass
class Activity:
    """The bits of a Bot Framework activity anything downstream is allowed to know about."""

    activity_id: str
    activity_type: str
    conversation_id: str
    conversation_type: str
    service_url: str
    text: str
    user_id: str
    user_name: str
    # True when a human (not the bot) joined -- the greeting trigger.
    human_joined: bool


def parse_activity(activity: dict[str, Any]) -> Activity:
    """Normalise the wire format. Tolerates a missing `text` (FR-12)."""
    conversation = activity.get("conversation") or {}
    sender = activity.get("from") or {}
    members_added = activity.get("membersAdded") or []
    return Activity(
        activity_id=str(activity.get("id") or ""),
        activity_type=str(activity.get("type") or ""),
        conversation_id=str(conversation.get("id") or ""),
        # Absent in some personal-chat activities; personal is the safe default because it
        # is the only scope that would ever get streaming, and defaulting the other way
        # would silently enable it where Teams forbids it.
        conversation_type=str(conversation.get("conversationType") or "personal"),
        service_url=normalize_service_url(str(activity.get("serviceUrl") or "")),
        text=str(activity.get("text") or "").strip(),
        user_id=str(sender.get("id") or ""),
        user_name=str(sender.get("name") or "there"),
        human_joined=any(
            not str(m.get("id", "")).startswith(BOT_ID_PREFIX) for m in members_added
        ),
    )


def _post_json(url: str, body: dict[str, Any], token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
        raw = response.read().decode("utf-8") or "{}"
    return json.loads(raw)


class TokenProvider:
    """Outbound Bot Framework tokens via client_credentials. Caches until near expiry."""

    # Refresh this many seconds before the token actually expires, so an in-flight reply
    # cannot be the thing that discovers it has gone stale.
    _SKEW = 60

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = ""
        self._expires_at = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - self._SKEW:
            return self._token
        form = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": BOT_SCOPE,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._token = payload["access_token"]
        self._expires_at = time.time() + float(payload.get("expires_in", 3600))
        return self._token


class BotFrameworkClient:
    """The only thing here that speaks HTTP to Microsoft."""

    def __init__(self, tokens: TokenProvider) -> None:
        self._tokens = tokens

    def reply(self, activity: Activity, text: str) -> None:
        """Reply in-thread to the activity that prompted us."""
        url = (
            f"{activity.service_url}/v3/conversations/"
            f"{activity.conversation_id}/activities/{activity.activity_id}"
        )
        self._send(url, {"type": "message", "text": text})

    def send(self, activity: Activity, text: str) -> None:
        """Post a new activity to the conversation, not a reply to a specific one."""
        url = f"{activity.service_url}/v3/conversations/{activity.conversation_id}/activities"
        self._send(url, {"type": "message", "text": text})

    def typing(self, activity: Activity) -> None:
        """Best effort. A failed typing indicator must never cost the user their answer."""
        url = f"{activity.service_url}/v3/conversations/{activity.conversation_id}/activities"
        try:
            self._send(url, {"type": "typing"})
        except Exception as exc:
            LOG.warning("typing indicator failed, continuing: %s", exc)

    def _send(self, url: str, payload: dict[str, Any]) -> None:
        try:
            _post_json(url, payload, self._tokens.get_token())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            # Surfaced rather than swallowed: a 401 here means the client secret is wrong or
            # expired, and a 429 means we are over a Teams rate limit. Both need to reach the
            # logs as themselves.
            raise RuntimeError(f"Bot Framework {exc.code} for {url}: {detail}") from exc
