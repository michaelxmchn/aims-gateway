"""Worker configuration — single source of truth for all worker settings."""

from __future__ import annotations

import os

GATEWAY_URL: str = os.getenv(
    "AIMS_GATEWAY_URL",
    "https://aims-gateway.fly.dev",
)
"""Production gateway endpoint.  Override via ``AIMS_GATEWAY_URL`` for local dev."""

WORKER_ID: str = os.getenv("AIMS_WORKER_ID", "worker-001")
"""Unique worker identifier.  Each deployed worker should have its own ID."""

CLAIM_TIMEOUT: float = float(os.getenv("AIMS_CLAIM_TIMEOUT", "30"))
"""HTTP request timeout in seconds for claim/submit calls."""

HEARTBEAT_INTERVAL: float = float(os.getenv("AIMS_HEARTBEAT_INTERVAL", "15"))
"""Seconds between heartbeat pings."""

POLL_INTERVAL: float = float(os.getenv("AIMS_POLL_INTERVAL", "1.0"))
"""Seconds to wait between claim attempts when the queue is empty."""

MAX_RETRIES: int = int(os.getenv("AIMS_MAX_RETRIES", "3"))
"""Number of retries on transient HTTP errors before giving up."""

# ── Claim / submit endpoints ──────────────────────────────────────────────

CLAIM_ENDPOINT: str = f"{GATEWAY_URL}/api/tasks/claim"
SUBMIT_ENDPOINT: str = f"{GATEWAY_URL}/api/tasks/submit"
HEARTBEAT_ENDPOINT: str = f"{GATEWAY_URL}/api/workers/heartbeat"
LOGIC_ENDPOINT: str = f"{GATEWAY_URL}/api/skills/{{skill_id}}/logic"
