"""EIP-191 request signing — mirrors the Gateway Server's middleware auth.

Workers sign every POST with their EIP-191 wallet key (``AIMS_WORKER_KEY``).
The gateway middleware verifies the signature via ``Account.recover_message``.

Every request carries three headers:

  - ``X-Wallet-Address`` — the worker's EVM wallet (``AIMS_WORKER_WALLET``)
  - ``X-Signature``      — EIP-191 ``personal_sign`` hex signature
  - ``X-Timestamp``      — UNIX epoch seconds as string

Usage::

    from src.worker.utils.signer import sign_headers

    headers = sign_headers({"worker_id": "w1"}, "w1")
    # → {"Content-Type": "application/json", "X-Wallet-Address": "0x...",
    #    "X-Signature": "0x...", "X-Timestamp": "..."}
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import eth_account only when EIP-191 key is available
_worker_key: str | None = None
_worker_wallet: str | None = None


def _load_eip191_key() -> bool:
    """Load the worker's EIP-191 wallet key from environment.

    Returns ``True`` if a key+wallet pair is available.
    """
    global _worker_key, _worker_wallet
    if _worker_key is not None:
        return True

    key = os.getenv("AIMS_WORKER_KEY", "").strip()
    wallet = os.getenv("AIMS_WORKER_WALLET", "").strip()
    if key and wallet and wallet.startswith("0x"):
        _worker_key = key
        _worker_wallet = wallet
        return True
    return False


def _eip191_sign(body_bytes: bytes) -> tuple[str, str, str]:
    """Sign *body_bytes* with the worker's EIP-191 wallet key.

    Returns ``(wallet_address, signature_hex, timestamp_str)``.
    """
    from eth_account import Account
    from eth_account.messages import encode_defunct

    ts = str(int(time.time()))
    signable = encode_defunct(primitive=body_bytes)
    signed = Account.from_key(_worker_key).sign_message(signable)
    return _worker_wallet, signed.signature.hex(), ts


def sign_headers(
    body: dict[str, Any] | None,
    worker_id: str,
) -> dict[str, str]:
    """Build EIP-191 signed headers for any request to the gateway.

    Uses the worker's EIP-191 wallet key (``AIMS_WORKER_KEY``) when
    available.  Falls back to HMAC-SHA256 for backward compatibility.

    Args:
        body: JSON-serialisable request body (``None`` for bodies that are
            not signed, e.g. GET requests).
        worker_id: Worker identifier (used by HMAC fallback only).

    Returns:
        Headers dict ready to pass to ``requests``.
    """
    ts = str(int(time.time()))
    body_bytes = json.dumps(body).encode() if body is not None else b""

    # ── EIP-191 primary path ───────────────────────────────────────────────
    if _load_eip191_key():
        wallet, sig, sig_ts = _eip191_sign(body_bytes)
        return {
            "Content-Type": "application/json",
            "X-Wallet-Address": wallet,
            "X-Signature": sig,
            "X-Timestamp": sig_ts,
        }

    # ── HMAC fallback (legacy — will likely 403 without EIP-191) ───────────
    logger.warning(
        "No AIMS_WORKER_KEY/AIMS_WORKER_WALLET set — falling back to HMAC. "
        "Gateway will reject with 403 if EIP-191 middleware is enforced."
    )
    import hashlib
    import hmac

    secret = os.getenv("AIMS_SIGNING_SECRET", "AIMS_MOCK_SECRET_2026").encode()
    msg = body_bytes + b"|" + ts.encode() + b"|" + worker_id.encode()
    sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "X-Signature": sig,
        "X-Timestamp": ts,
        "X-User-ID": worker_id,
    }
