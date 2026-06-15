"""Circuit Breaker — 3-state intelligent fault isolation for AIMS Gateway.

Implements a finite-state machine with three states:

  CLOSED    — Normal operation. All requests pass through.
  HALF-OPEN — Degraded mode. Heuristic fallback activated after N consecutive
              failures (LLM timeout, RPC error). SSE yellow alert broadcast.
  OPEN      — Catastrophic isolation. All new tasks rejected, escrow funds
              frozen. SSE red alert broadcast. Requires admin reset.

State transition matrix::

                  ┌──────────────────────────────────────────────────┐
                  │                  FAILURE_COUNT ≥ threshold       │
                  │    ┌─────────────────────────────────┐           │
                  │    │                                  ▼           │
                  │  ┌─────────┐   consecutive_fails    ┌──────────┐ │
                  │  │ CLOSED  │ ──────────────────────► │HALF-OPEN │ │
                  │  └─────────┘                         └──────────┘ │
                  │        ▲                                  │       │
                  │        │                           fail    │       │
                  │        │◄──── reset()              count   │       │
                  │        │                          ≥ max    ▼       │
                  │        │                          ┌──────────┐     │
                  │        │◄──── admin_reset() ──────│   OPEN   │     │
                  │        │                          └──────────┘     │
                  │        │                               │           │
                  │        │                    admin       │           │
                  │        │◄──── admin_force_open() ◄──────┘           │
                  └──────────────────────────────────────────────────────┘

Usage:
    breaker = CircuitBreaker(storage, on_state_change=on_alert)

    # Wrap a call
    async with breaker.guard("llm_judge"):
        result = await llm_score(...)

    # Or check manually
    if not breaker.can_pass("api_run"):
        raise HTTPException(503, "Gateway is in OPEN state — accepting no new tasks")
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Callable, Optional

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

# ── Storage namespaces ─────────────────────────────────────────────────────────

CB_NS = "circuit_breaker:state"
CB_FAIL_NS = "circuit_breaker:fails"
CB_TIMESTAMP = "circuit_breaker:last_state_change"

# ── Default thresholds ─────────────────────────────────────────────────────────

DEFAULT_CONSECUTIVE_THRESHOLD = 3
"""Number of consecutive failures before CLOSED → HALF-OPEN."""
MAX_DEGRADED_THRESHOLD = 6
"""Total failures in HALF-OPEN before OPEN (cumulative since last CLOSED)."""
OPEN_COOLDOWN_SECONDS = 120.0
"""Minimum seconds before OPEN can be admin-reset back to CLOSED."""


class BreakerState(str, enum.Enum):
    CLOSED = "CLOSED"
    HALF_OPEN = "HALF_OPEN"
    OPEN = "OPEN"


class CircuitBreaker:
    """Three-state circuit breaker with persistent failure counting and SSE alerts."""

    def __init__(
        self,
        storage: Storage,
        on_state_change: Callable[[str, str], None] | None = None,
        consecutive_threshold: int = DEFAULT_CONSECUTIVE_THRESHOLD,
        max_degraded_threshold: int = MAX_DEGRADED_THRESHOLD,
        open_cooldown: float = OPEN_COOLDOWN_SECONDS,
    ) -> None:
        self._storage = storage
        self._on_state_change = on_state_change
        self._consecutive_threshold = consecutive_threshold
        self._max_degraded_threshold = max_degraded_threshold
        self._open_cooldown = open_cooldown

        # In-memory counters (fast path, avoid redis for every failure tick)
        self._consecutive_fails: int = 0
        self._degraded_fails: int = 0

        # Restore persisted state
        self._state = BreakerState(self._storage.get(CB_NS, "CLOSED") or "CLOSED")
        raw = self._storage.get(CB_FAIL_NS, 0) or 0
        self._consecutive_fails = int(raw)
        self._last_state_change = float(self._storage.get(CB_TIMESTAMP, 0.0) or 0.0)

        logger.info(
            "CircuitBreaker init — state=%s consecutive_fails=%d",
            self._state.value, self._consecutive_fails,
        )

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def consecutive_fails(self) -> int:
        return self._consecutive_fails

    @property
    def degraded_fails(self) -> int:
        return self._degraded_fails

    @property
    def is_closed(self) -> bool:
        return self._state == BreakerState.CLOSED

    @property
    def is_degraded(self) -> bool:
        return self._state == BreakerState.HALF_OPEN

    @property
    def is_open(self) -> bool:
        return self._state == BreakerState.OPEN

    # ── State machine ──────────────────────────────────────────────────────────

    def _transition(self, new_state: BreakerState) -> None:
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        self._last_state_change = time.time()
        self._storage.set(CB_NS, new_state.value)
        self._storage.set(CB_TIMESTAMP, str(self._last_state_change))
        logger.warning(
            "🔁 CIRCUIT BREAKER %s → %s (consecutive=%d degraded=%d)",
            old_state.value, new_state.value,
            self._consecutive_fails, self._degraded_fails,
        )
        if self._on_state_change:
            self._on_state_change(old_state.value, new_state.value)

    # ── Public API ─────────────────────────────────────────────────────────────

    def record_failure(self, reason: str = "") -> None:
        """Record a failure and potentially advance the state machine.

        Called when an upstream dependency fails (LLM timeout, RPC error, etc.).
        """
        self._consecutive_fails += 1
        self._storage.incr(CB_FAIL_NS)

        if self._state == BreakerState.CLOSED:
            if self._consecutive_fails >= self._consecutive_threshold:
                logger.warning(
                    "⚠️ DEGRADED — %d consecutive failures (threshold=%d). "
                    "Reason: %s",
                    self._consecutive_fails, self._consecutive_threshold, reason,
                )
                self._degraded_fails = 0
                self._transition(BreakerState.HALF_OPEN)

        elif self._state == BreakerState.HALF_OPEN:
            self._degraded_fails += 1
            if self._degraded_fails >= self._max_degraded_threshold:
                logger.critical(
                    "🚨 OPEN — %d failures while degraded (max=%d). "
                    "Reason: %s",
                    self._degraded_fails, self._max_degraded_threshold, reason,
                )
                self._transition(BreakerState.OPEN)

    def record_success(self) -> None:
        """Record a successful call.  Resets the consecutive-failure counter.

        If the breaker is in HALF-OPEN, a single success resets to CLOSED
        (self-healing).
        """
        self._consecutive_fails = 0
        self._degraded_fails = 0
        self._storage.set(CB_FAIL_NS, "0")

        if self._state == BreakerState.HALF_OPEN:
            logger.info("✅ Self-healing — HALF_OPEN → CLOSED (success)")
            self._transition(BreakerState.CLOSED)

    def can_pass(self, context: str = "") -> bool:
        """Check whether a request can proceed.

        In OPEN state, returns ``False`` — the caller should reject the request.
        In CLOSED or HALF-OPEN, returns ``True``.
        """
        if self._state == BreakerState.OPEN:
            elapsed = time.time() - self._last_state_change
            if elapsed >= self._open_cooldown:
                logger.info(
                    "⏱️  OPEN cooldown elapsed (%.1fs ≥ %.1fs) — "
                    "auto-transition to CLOSED for next attempt",
                    elapsed, self._open_cooldown,
                )
                self._transition(BreakerState.CLOSED)
                return True
            logger.warning(
                "🚫 REJECTED — circuit OPEN (context=%s, elapsed=%.1fs)",
                context, elapsed,
            )
            return False
        return True

    # ── Admin controls ─────────────────────────────────────────────────────────

    def admin_reset(self) -> BreakerState:
        """Admin-triggered full reset: OPEN → CLOSED, clears all counters."""
        self._consecutive_fails = 0
        self._degraded_fails = 0
        self._storage.set(CB_FAIL_NS, "0")
        self._transition(BreakerState.CLOSED)
        logger.info("🔧 Admin reset — forced CLOSED")
        return self._state

    def admin_force_open(self) -> BreakerState:
        """Admin-triggered emergency isolation: any state → OPEN."""
        self._transition(BreakerState.OPEN)
        logger.critical("🔴 Admin force OPEN — emergency isolation")
        return self._state

    def status(self) -> dict:
        """Return a snapshot for health / admin endpoints."""
        return {
            "state": self._state.value,
            "consecutive_fails": self._consecutive_fails,
            "degraded_fails": self._degraded_fails,
            "consecutive_threshold": self._consecutive_threshold,
            "max_degraded_threshold": self._max_degraded_threshold,
            "open_cooldown_seconds": self._open_cooldown,
            "last_state_change": self._last_state_change,
            "elapsed_since_change": time.time() - self._last_state_change,
        }
