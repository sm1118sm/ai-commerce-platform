"""Short-lived, signed browser sessions for Streamlit authentication."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import time


@dataclass(frozen=True)
class SessionClaims:
    user_id: int
    expires_at: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(
    user_id: int,
    secret: str,
    *,
    now: int | None = None,
    ttl_seconds: int = 7_200,
) -> tuple[str, SessionClaims]:
    """Create an HMAC-signed user token with an absolute expiration time."""
    issued_at = int(time.time() if now is None else now)
    claims = SessionClaims(
        user_id=int(user_id),
        expires_at=issued_at + int(ttl_seconds),
    )
    payload = json.dumps(
        {
            "exp": claims.expires_at,
            "sub": claims.user_id,
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _encode(payload)
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}", claims


def verify_session_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> SessionClaims | None:
    """Return valid claims, rejecting malformed, altered, or expired tokens."""
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None
        payload = json.loads(_decode(encoded_payload))
        if not isinstance(payload, dict):
            return None
        if payload.get("v") != 1:
            return None
        user_id = int(payload["sub"])
        expires_at = int(payload["exp"])
        current_time = int(time.time() if now is None else now)
        if user_id <= 0 or expires_at <= current_time:
            return None
        return SessionClaims(user_id=user_id, expires_at=expires_at)
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
