"""Task Broker — DePIN Centralized Task Queue (Layer 3.5).

Maintains a thread-safe FIFO task queue that Worker Nodes poll for
work. Each task carries a pre-funded escrow hold so workers can execute
and claim gas fees without touching user balances directly.

Lifecycle:
  1. publish_task() — create escrow hold from user, enqueue task
  2. poll_task()   — worker pops next available task (blocking with timeout)
  3. record_result — worker reports settlement outcome back to broker
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from src.ledger.mock_counter import DynamicSettlementDetail, EscrowHold, MockLedger

logger = logging.getLogger(__name__)


@dataclass
class BrokerTask:
    """A scraping task waiting for an available worker node."""

    task_id: str
    user_id: str
    asin: str
    developer_premium: float
    max_budget: float
    escrow_hold: EscrowHold


class TaskBroker:
    """Centralised thread-safe FIFO task queue for DePIN workload distribution."""

    def __init__(self, ledger: MockLedger) -> None:
        self._ledger = ledger
        self._queue: queue.Queue[BrokerTask] = queue.Queue()
        self._task_counter = 0
        self._lock = threading.Lock()
        self._assignments: Dict[str, str] = {}
        self._results: Dict[str, DynamicSettlementDetail] = {}

    def publish_task(
        self,
        user_id: str,
        asin: str,
        developer_premium: float,
        max_budget: float,
    ) -> Optional[str]:
        """Create an escrow hold and enqueue a micro-task.

        Returns the ``task_id`` string, or ``None`` if the user has
        insufficient balance for the escrow hold.
        """
        hold = self._ledger.create_escrow_hold(user_id, max_budget)
        if hold is None:
            return None

        with self._lock:
            self._task_counter += 1
            task_id = f"task-{self._task_counter:04d}"

        task = BrokerTask(
            task_id=task_id,
            user_id=user_id,
            asin=asin,
            developer_premium=developer_premium,
            max_budget=max_budget,
            escrow_hold=hold,
        )
        self._queue.put(task)
        logger.info(
            "PUBLISH %s → queue (asin=%s  premium=$%.2f  budget=$%.2f)",
            task_id, asin, developer_premium, max_budget,
        )
        return task_id

    def poll_task(self, worker_id: str, timeout: float = 2.0) -> Optional[BrokerTask]:
        """Non-blocking poll for the next available task.

        Blocks up to *timeout* seconds. Returns ``None`` if the queue
        is still empty after the timeout.
        """
        try:
            task = self._queue.get(timeout=timeout)
            with self._lock:
                self._assignments[task.task_id] = worker_id
            logger.info(
                "ASSIGN %s → worker '%s'", task.task_id, worker_id,
            )
            return task
        except queue.Empty:
            return None

    def record_result(self, task_id: str, detail: DynamicSettlementDetail) -> None:
        """Store the settlement result for a completed task."""
        with self._lock:
            self._results[task_id] = detail

    # ── status helpers ─────────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._results)

    def worker_summary(self) -> Dict[str, int]:
        """Return {worker_id: completed_task_count}."""
        with self._lock:
            summary: Dict[str, int] = {}
            for tid, wid in self._assignments.items():
                if tid in self._results:
                    summary[wid] = summary.get(wid, 0) + 1
            return summary
