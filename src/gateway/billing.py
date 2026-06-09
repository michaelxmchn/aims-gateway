"""Billing engine for the AIMS Credit & Revenue system (Layer 3.5).

A parallel credit-billing layer alongside the existing USDT escrow system.
Each task costs a constant ``COST_PER_TASK`` (0.05 credits). On SUCCESS,
credits are deducted atomically and split 80/20 between the Worker and
the Gateway Owner.

Reservation pattern
-------------------
1. ``reserve_credits(task_id, user_id)`` — checks balance ≥ COST_PER_TASK
   and stores a reservation ``{"user_id": …, "amount": COST_PER_TASK}``.
   The reservation *includes the user_id* so settlement knows who to deduct.

2. ``settle_task(task_id, worker_id, success)`` — reads the reservation,
   then atomically deducts from the user and splits between worker/owner
   (SUCCESS) or simply releases the hold (FAILED/REFUNDED).

Atomicity
---------
- **Redis mode**: A Lua script (``EVAL``) performs deduct + credit worker +
  credit owner + delete reservation in a single atomic step.
- **In-memory mode**: All operations happen under a single
  ``threading.Lock()`` via ``Storage.pipeline()``.

Usage::

    billing = BillingEngine(storage=storage, owner_id="gateway_owner")
    billing.deposit("alice", 10.0)
    billing.reserve_credits("task-0001", "alice")
    receipt = billing.settle_task("task-0001", "worker-01", success=True)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

# ── Redis namespace constants ──────────────────────────────────────────────────

NS_BALANCE = "billing:balance"      # key = user_id, value = float
NS_RESERVED = "billing:reserved"    # key = task_id, value = {"user_id": …, "amount": …}
KEY_COUNTER = "billing:counter"     # atomic counter for receipts

# ── Lua script for atomic settlement on Redis ─────────────────────────────────

SETTLE_SCRIPT = """
local balance_key = KEYS[1]
local worker_key = KEYS[2]
local owner_key = KEYS[3]
local reserved_key = KEYS[4]
local tx_key = KEYS[5]

local cost = tonumber(ARGV[1])
local worker_share = tonumber(ARGV[2])
local owner_share = tonumber(ARGV[3])
local worker_id = ARGV[4]
local owner_id = ARGV[5]
local user_id = ARGV[6]
local status = ARGV[7]
local timestamp = ARGV[8]

-- Check reservation exists
local reserved = redis.call("GET", reserved_key)
if not reserved then
    return {0, "NO_RESERVATION"}
end

if status == "COMPLETED" then
    local balance = tonumber(redis.call("GET", balance_key) or "0")
    if balance < cost then
        return {0, "INSUFFICIENT_CREDITS"}
    end

    redis.call("SET", balance_key, balance - cost)

    -- Credit worker
    local wb = tonumber(redis.call("GET", worker_key) or "0")
    redis.call("SET", worker_key, wb + worker_share)

    -- Credit owner (skip if owner == worker to avoid double count)
    if owner_id ~= worker_id then
        local ob = tonumber(redis.call("GET", owner_key) or "0")
        redis.call("SET", owner_key, ob + owner_share)
    else
        local wb2 = tonumber(redis.call("GET", worker_key) or "0")
        redis.call("SET", worker_key, wb2 + owner_share)
    end
end

-- Record transaction receipt
local receipt = cjson.encode({
    status = status,
    cost = cost,
    worker_payout = (status == "COMPLETED" and worker_share or 0),
    gateway_payout = (status == "COMPLETED" and owner_share or 0),
    user_id = user_id,
    worker_id = worker_id,
    owner_id = owner_id,
    timestamp = timestamp
})
redis.call("SET", tx_key, receipt)
redis.call("DEL", reserved_key)

return {1, status}
"""  # nosec B605 — internal atomicity helper, not user-supplied


class BillingEngine:
    """Parallel credit-billing layer alongside USDT escrow.

    Manages four balance namespaces:
    - User credit balances  (``billing:balance:{user_id}``)
    - Worker credit earnings (same namespace, separate IDs)
    - Owner platform fees   (same namespace, ``owner_id`` key)
    - Task reservations     (``billing:reserved:{task_id}``)
    """

    COST_PER_TASK: float = 0.05
    WORKER_SHARE: float = 0.80
    OWNER_SHARE: float = 0.20
    NS_BALANCE: str = NS_BALANCE
    NS_RESERVED: str = NS_RESERVED
    KEY_COUNTER: str = KEY_COUNTER

    def __init__(self, storage: Storage, owner_id: str = "gateway_owner") -> None:
        self._storage = storage
        self._owner_id = owner_id

    # ── Balance API ──────────────────────────────────────────────────────────

    def deposit(self, user_id: str, amount: float) -> float:
        """Add *amount* credits to *user_id*'s wallet. Returns new balance."""
        current = self.get_balance(user_id)
        new_balance = round(current + amount, 4)
        self._storage.dict_set(NS_BALANCE, user_id, new_balance)
        return new_balance

    def get_balance(self, user_id: str) -> float:
        """Return current credit balance (``0.0`` if unknown)."""
        val = self._storage.dict_get(NS_BALANCE, user_id, 0.0)
        return float(val)

    def get_worker_balance(self, worker_id: str) -> float:
        """Return total credits earned by *worker_id*."""
        return self.get_balance(worker_id)

    def get_owner_balance(self) -> float:
        """Return total platform fee credits collected."""
        return self.get_balance(self._owner_id)

    # ── Reservation API ─────────────────────────────────────────────────────

    def reserve_credits(self, task_id: str, user_id: str) -> bool:
        """Pre-authorise ``COST_PER_TASK`` credits for *task_id*.

        Stores a reservation dict including the user_id so settlement
        knows which wallet to deduct from.

        Returns ``True`` if sufficient balance, ``False`` otherwise.
        """
        balance = self.get_balance(user_id)
        if balance < self.COST_PER_TASK:
            return False
        reservation = {
            "user_id": user_id,
            "amount": self.COST_PER_TASK,
            "timestamp": time.time(),
        }
        self._storage.dict_set(NS_RESERVED, task_id, reservation)
        return True

    def get_reservation(self, task_id: str) -> dict[str, Any] | None:
        """Return the reservation metadata for *task_id*, or ``None``."""
        return self._storage.dict_get(NS_RESERVED, task_id)

    # ── Settlement API ──────────────────────────────────────────────────────

    def settle_task(
        self,
        task_id: str,
        worker_id: str,
        success: bool,
    ) -> dict[str, Any] | None:
        """Atomically settle credits for a completed task.

        **SUCCESS** (``success=True``):
        Deduct ``COST_PER_TASK`` from the user's balance, credit 80% to
        the worker and 20% to the gateway owner.

        **FAILED/REFUNDED** (``success=False``):
        Release the reservation — no deduction.

        Returns a receipt dict, or ``None`` if no reservation exists
        (idempotent: a second call returns the stored receipt).
        """
        reservation = self._storage.dict_get(NS_RESERVED, task_id)
        if reservation is None:
            return self._get_receipt(task_id)

        user_id = reservation.get("user_id", "")
        if not user_id:
            logger.warning("settle_task %s: reservation missing user_id", task_id)
            self._storage.dict_delete(NS_RESERVED, task_id)
            return None

        if self._storage.is_persistent:
            return self._settle_via_redis(task_id, user_id, worker_id, success)

        return self._settle_in_memory(task_id, user_id, worker_id, success)

    # ── Internal: Redis path ────────────────────────────────────────────────

    def _settle_via_redis(
        self,
        task_id: str,
        user_id: str,
        worker_id: str,
        success: bool,
    ) -> dict[str, Any] | None:
        """Execute settlement atomically via a Redis Lua script."""
        redis_client = self._storage._redis
        if not redis_client:
            return self._settle_in_memory(task_id, user_id, worker_id, success)

        cost = self.COST_PER_TASK
        worker_share = round(cost * self.WORKER_SHARE, 4)
        owner_share = round(cost * self.OWNER_SHARE, 4)
        ts = str(time.time())
        status = "COMPLETED" if success else "REFUNDED"

        keys = [
            self._storage._ns(NS_BALANCE, user_id),           # KEYS[1]
            self._storage._ns(NS_BALANCE, worker_id),          # KEYS[2]
            self._storage._ns(NS_BALANCE, self._owner_id),     # KEYS[3]
            self._storage._ns(NS_RESERVED, task_id),           # KEYS[4]
            self._storage._ns(NS_RESERVED, f"receipt:{task_id}"),  # KEYS[5]
        ]
        args = [
            str(cost), str(worker_share), str(owner_share),
            worker_id, self._owner_id, user_id, status, ts,
        ]

        try:
            result = redis_client.eval(SETTLE_SCRIPT, len(keys), *(keys + args))
        except Exception as exc:
            logger.error("Redis settle_task failed for %s: %s", task_id, exc)
            return None

        if result and isinstance(result, (list, tuple)) and result[0] == 1:
            return {
                "task_id": task_id,
                "status": status,
                "cost": cost,
                "worker_payout": worker_share if success else 0.0,
                "gateway_payout": owner_share if success else 0.0,
                "user_id": user_id,
                "worker_id": worker_id,
            }
        return None

    # ── Internal: In-memory path ────────────────────────────────────────────

    def _settle_in_memory(
        self,
        task_id: str,
        user_id: str,
        worker_id: str,
        success: bool,
    ) -> dict[str, Any]:
        """Execute settlement under a single pipeline lock (in-memory)."""
        cost = self.COST_PER_TASK
        worker_share = round(cost * self.WORKER_SHARE, 4)
        owner_share = round(cost * self.OWNER_SHARE, 4)

        with self._storage.pipeline() as pipe:
            # Delete reservation first (marks as "in-flight")
            self._storage.dict_delete(NS_RESERVED, task_id)

            if success:
                # Deduct from user
                user_bal = self.get_balance(user_id)
                pipe.set(
                    self._storage._ns(NS_BALANCE, user_id),
                    max(round(user_bal - cost, 4), 0.0),
                )

                # Credit worker
                worker_bal = self.get_balance(worker_id)
                pipe.set(
                    self._storage._ns(NS_BALANCE, worker_id),
                    round(worker_bal + worker_share, 4),
                )

                # Credit owner (or worker if same entity)
                if worker_id != self._owner_id:
                    owner_bal = self.get_balance(self._owner_id)
                    pipe.set(
                        self._storage._ns(NS_BALANCE, self._owner_id),
                        round(owner_bal + owner_share, 4),
                    )
                else:
                    # Both shares go to worker in one set (matches Lua script)
                    pipe.set(
                        self._storage._ns(NS_BALANCE, worker_id),
                        round(worker_bal + worker_share + owner_share, 4),
                    )

            pipe.execute()

        receipt: dict[str, Any] = {
            "task_id": task_id,
            "status": "COMPLETED" if success else "REFUNDED",
            "cost": cost if success else 0.0,
            "worker_payout": (worker_share if success else 0.0),
            "gateway_payout": (owner_share if success else 0.0),
            "user_id": user_id,
            "worker_id": worker_id,
        }
        self._storage.dict_set(NS_RESERVED, f"receipt:{task_id}", receipt)
        return receipt

    # ── Receipt helpers ─────────────────────────────────────────────────────

    def _get_receipt(self, task_id: str) -> dict[str, Any] | None:
        """Return existing receipt for *task_id* (idempotent lookup)."""
        return self._storage.dict_get(NS_RESERVED, f"receipt:{task_id}")
