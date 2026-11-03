"""Signed browser ticket for keeping the hub login across browser tabs.

The ticket contains no password. It is signed with a key stored under CENTRAL_DATA and
expires after 30 days. It is safe to pass between the hub's own pages and embedded tools.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

TTL_SECONDS = 30 * 24 * 60 * 60


def _key(root) -> bytes:
    path = Path(root) / "hub_session.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            with path.open("xb") as f:
                f.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
    return path.read_bytes()


def issue(root, username: str, role: str, *, now: int | None = None) -> str:
    payload = {"u": str(username), "r": str(role), "exp": int(now or time.time()) + TTL_SECONDS}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(_key(root), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def validate(root, ticket: str, *, now: int | None = None) -> dict | None:
    try:
        body, signature = str(ticket or "").split(".", 1)
        expected = hmac.new(_key(root), body.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
        if not payload.get("u") or int(payload.get("exp", 0)) <= int(now or time.time()):
            return None
        return {"username": str(payload["u"]), "role": str(payload.get("r", "viewer"))}
    except Exception:
        return None
