"""HMAC-SHA256 request signing — mirrors the Gateway Server's ``compute_signature``.

Every request to the AIMS Gateway must carry three headers:

  - ``X-Signature`` — hex-encoded HMAC-SHA256
  - ``X-Timestamp`` — UNIX epoch seconds as string
  - ``X-User-ID``   — the worker identifier

Usage::

    from src.worker.utils.signer import sign_headers

    body_bytes = json.dumps({"worker_id": "w1"}).encode()
    headers = sign_headers(body_bytes, "w1")
    # → {"Content-Type": "application/json", "X-Signature": "...",
    #    "X-Timestamp": "...", "X-User-ID": "w1"}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any


def _get_secret() -> bytes:
    """Load the shared signing secret.

    Precedence:
      1. ``AIMS_SIGNING_SECRET`` env var (production — set via Fly.io secrets)
      2. Hard-coded fallback (local development only)
    """
    return os.getenv("AIMS_SIGNING_SECRET", "AIMS_MOCK_SECRET_2026").encode()


def compute_signature(body: bytes, timestamp: str, worker_id: str) -> str:
    """HMAC-SHA256 of ``body + b'|' + timestamp + b'|' + worker_id``.

    Must produce **identical** output to ``src.gateway.server.compute_signature``.
    """
    secret = _get_secret()
    msg = body + b"|" + timestamp.encode() + b"|" + worker_id.encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def sign_headers(
    body: dict[str, Any] | None,
    worker_id: str,
) -> dict[str, str]:
    """Build a complete headers dict with HMAC-SHA256 signature.

    Args:
        body: JSON-serialisable request body (``None`` for GET requests).
        worker_id: Worker identifier sent as ``X-User-ID``.

    Returns:
        Headers dict ready to pass to ``requests`` / ``httpx``.
    """
    ts = str(int(time.time()))
    body_bytes = json.dumps(body).encode() if body else b""
    sig = compute_signature(body_bytes, ts, worker_id)

    return {
        "Content-Type": "application/json",
        "X-Signature": sig,
        "X-Timestamp": ts,
        "X-User-ID": worker_id,
    }
