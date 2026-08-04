"""Inbound-trust tests for the Bot Framework front door.

The `serviceurl` cases are **required** (FR-8a), not optional coverage. In the n8n prototype
this check was present and non-functional: the code read `payload.serviceUrl` (camelCase)
against a claim actually named `serviceurl`, so the comparison was always against `None` and a
truthiness guard turned it into a silent skip. Every test below that asserts a *rejection*
would have passed against that broken implementation too -- except the two that matter, which
is the point of writing them.

`botframework` imports only PyJWT and the standard library, so these run with no AWS and no
Bot Framework fixtures. That isolation is deliberate.

Run:
    uv run --python 3.13 --with 'PyJWT[crypto]>=2.8,<3' --with pytest \
        pytest blueprints/teams-bot/tests -q
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import botframework as bf  # noqa: E402

BOT_APP_ID = "11111111-2222-3333-4444-555555555555"
SERVICE_URL = "https://smba.trafficmanager.net/amer/"
ACTIVITY = {"id": "act-1", "type": "message", "serviceUrl": SERVICE_URL}

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch):
    """Serve our own public key instead of fetching the real Bot Framework JWKS."""

    class _Signing:
        key = _KEY.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Signing()

    monkeypatch.setattr(bf, "_jwks_client", _Client())


def _token(**overrides) -> str:
    claims = {
        "iss": bf.EXPECTED_ISSUER,
        "aud": BOT_APP_ID,
        "serviceurl": SERVICE_URL,
        "exp": int(time.time()) + 600,
        "nbf": int(time.time()) - 10,
    }
    claims.update(overrides)
    for key in [k for k, v in claims.items() if v is None]:
        del claims[key]
    return jwt.encode(claims, _KEY, algorithm="RS256")


def _validate(token: str, activity=None) -> None:
    bf.validate_activity(f"Bearer {token}", activity or ACTIVITY, BOT_APP_ID)


# --- the happy path, so the rejections below mean something --------------------------------


def test_genuine_activity_is_accepted():
    _validate(_token())


def test_trailing_slash_difference_is_tolerated():
    """The claim and the body may disagree on a trailing slash; normalisation happens once."""
    _validate(_token(serviceurl="https://smba.trafficmanager.net/amer"))


# --- FR-8a: the two that the prototype's bug would have let through ------------------------


def test_absent_serviceurl_claim_is_a_failure():
    """Absence must FAIL, not pass. This is the exact bug shape from the prototype."""
    with pytest.raises(bf.ValidationError, match="no serviceurl claim"):
        _validate(_token(serviceurl=None))


def test_mismatched_serviceurl_is_rejected():
    """An attacker with a valid token must not be able to redirect our replies."""
    with pytest.raises(bf.ValidationError, match="does not match"):
        _validate(_token(serviceurl="https://evil.example.com"))


# --- the rest of FR-8 ---------------------------------------------------------------------


def test_wrong_audience_is_rejected():
    with pytest.raises(bf.ValidationError):
        _validate(_token(aud="some-other-app"))


def test_wrong_issuer_is_rejected():
    with pytest.raises(bf.ValidationError):
        _validate(_token(iss="https://login.example.com"))


def test_expired_token_is_rejected():
    with pytest.raises(bf.ValidationError):
        _validate(_token(exp=int(time.time()) - bf.LEEWAY_SECONDS - 60))


def test_expiry_within_skew_is_accepted():
    _validate(_token(exp=int(time.time()) - 60))


def test_unsigned_token_is_rejected():
    """alg is pinned to RS256, so a 'none'-algorithm token cannot walk in."""
    forged = jwt.encode(
        {"iss": bf.EXPECTED_ISSUER, "aud": BOT_APP_ID, "serviceurl": SERVICE_URL,
         "exp": int(time.time()) + 600},
        key="",
        algorithm="none",
    )
    with pytest.raises(bf.ValidationError):
        _validate(forged)


def test_missing_authorization_header_is_rejected():
    with pytest.raises(bf.ValidationError, match="Authorization"):
        bf.validate_activity(None, ACTIVITY, BOT_APP_ID)


def test_non_bearer_authorization_is_rejected():
    with pytest.raises(bf.ValidationError, match="Authorization"):
        bf.validate_activity("Basic abc123", ACTIVITY, BOT_APP_ID)


def test_unconfigured_bot_app_id_refuses_everything():
    """A misconfigured deployment must fail closed, not become an open relay."""
    with pytest.raises(bf.ValidationError, match="BOT_APP_ID"):
        bf.validate_activity(f"Bearer {_token()}", ACTIVITY, "")


# --- activity parsing ---------------------------------------------------------------------


def test_bot_only_membership_event_does_not_greet():
    """Without the 28: filter the bot greets itself on install."""
    activity = bf.parse_activity(
        {"type": "conversationUpdate", "membersAdded": [{"id": "28:the-bot"}]}
    )
    assert activity.human_joined is False


def test_human_membership_event_greets():
    activity = bf.parse_activity(
        {"type": "conversationUpdate", "membersAdded": [{"id": "29:a-person"}]}
    )
    assert activity.human_joined is True


def test_activity_without_text_parses():
    """FR-12: activities with no text field must be tolerated, not crash."""
    activity = bf.parse_activity({"id": "a", "type": "message"})
    assert activity.text == ""


def test_channel_conversation_id_format_is_preserved():
    activity = bf.parse_activity(
        {"type": "message", "conversation": {"id": "19:abc@thread.tacv2",
                                            "conversationType": "channel"}}
    )
    assert activity.conversation_id == "19:abc@thread.tacv2"
    assert activity.conversation_type == "channel"


# --- log-id bounding: the activity id is attacker-controlled BEFORE auth ------------------
#
# Found by a reviewer reading handler.py rather than by design: the rejection log line carries
# the inbound activity id, and that line is emitted before authentication has passed. So an
# unauthenticated caller chooses a string that lands in our log stream.


def test_newlines_cannot_forge_a_log_line():
    """An embedded newline plus a plausible prefix is a forged log event."""
    forged = "1\nrejected activity: correlation=innocent type=message reason=fine"
    assert "\n" not in bf.safe_log_id(forged)


def test_log_id_is_length_bounded():
    assert len(bf.safe_log_id("a" * 5000)) == bf.MAX_LOG_ID_CHARS


def test_log_id_never_empty():
    """An empty id must not produce an empty field in a log line."""
    assert bf.safe_log_id("") == "no-id"


def test_log_id_preserves_real_bot_framework_ids():
    """Real ids contain ':', '|' and '='. Mangling them would make logs untraceable."""
    for real in ("1754321234567", "f:1234567890|0000", "a1b2-c3d4.e5", "id=abc:1"):
        assert bf.safe_log_id(real) == real


def test_activity_id_is_left_raw_for_the_api():
    """The URL-bound id must NOT be sanitised -- '|' is legal and replies would 404."""
    a = bf.parse_activity({"id": "f:123|0000", "type": "message"})
    assert a.activity_id == "f:123|0000"
    assert a.log_id == "f:123|0000"


def test_unsafe_id_is_sanitised_for_logs_but_kept_raw_for_the_api():
    a = bf.parse_activity({"id": "x\ny\rz", "type": "message"})
    assert a.activity_id == "x\ny\rz"
    assert "\n" not in a.log_id and "\r" not in a.log_id
