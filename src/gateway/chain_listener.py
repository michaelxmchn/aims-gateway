"""Chain event listener — background poller for on-chain settlement events.

Polls the AIMSAgentGateway contract for ``TaskSettled`` and ``TaskRefunded``
events, dispatches them to registered callbacks, and provides a DRM skill
dispatch bridge for closed-loop operation on Base Sepolia testnet.

Two modes:

* **Web3 mode** — polls ``w3.eth.get_logs`` with the event-signature topic
  hash.  Tracks ``last_processed_block`` in Redis to resume from the last
  seen block after restart.

* **InMemory mode** — reads from the contract's ``_event_buffer`` list
  (appended by ``InMemorySettlementContract`` on every settle/refund).

Usage::

    listener = ChainListener(
        contract_client=_contract,
        rpc_url=AIMS_RPC_URL,
        contract_address=AIMS_CONTRACT_ADDRESS,
        on_settlement=broadcast_settlement,
        on_refund=broadcast_settlement,
        storage=storage,
    )
    listener.start()
    # ... later ...
    listener.stop()
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Event signature topic hashes (keccak256 of event definitions) ─────────────

TASK_SETTLED_TOPIC = "0x"
"""keccak256("TaskSettled(bytes32,bytes32,address,address,uint256,uint256,uint256,uint256)")"""

TASK_REFUNDED_TOPIC = "0x"
"""keccak256("TaskRefunded(bytes32,address,uint256,string)")"""


def _compute_topic_hash(event_signature: str) -> str:
    """Compute the Keccak-256 topic hash for an event signature."""
    from eth_utils import keccak
    return "0x" + keccak(text=event_signature).hex()


# Compute topic hashes at module load time
TASK_SETTLED_TOPIC = _compute_topic_hash(
    "TaskSettled(bytes32,bytes32,address,address,uint256,uint256,uint256,uint256)"
)
TASK_REFUNDED_TOPIC = _compute_topic_hash(
    "TaskRefunded(bytes32,address,uint256,string)"
)


# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_POLL_INTERVAL: int = 15
"""Seconds between poll iterations."""

DEFAULT_MAX_BLOCKS: int = 200
"""Maximum number of blocks to scan in a single ``get_logs`` call."""

LAST_BLOCK_KEY = "chain_listener:last_processed_block"
"""Redis key for persisting the last processed block number."""


# ── ChainListener ────────────────────────────────────────────────────────────


class ChainListener:
    """Background thread that polls the settlement contract for events.

    Parameters
    ----------
    contract_client:
        ``SettlementContractClient`` instance (``InMemorySettlementContract``
        or ``Web3SettlementContract``).
    rpc_url:
        JSON-RPC URL for Web3 mode (used only when the contract is not
        InMemory).
    contract_address:
        Deployed contract address (for Web3 ``get_logs`` filtering).
    gateway_private_key:
        Gateway EOA private key (for signing DRM dispatch transactions).
    on_settlement:
        Optional callback invoked for each ``TaskSettled`` event.  Receives
        a dict with the event fields.
    on_refund:
        Optional callback invoked for each ``TaskRefunded`` event.  Receives
        a dict with the event fields.
    storage:
        Optional ``Storage`` instance for persisting ``last_processed_block``
        across restarts (Web3 mode).
    poll_interval:
        Seconds between poll iterations (default 15).
    max_blocks:
        Max block range per ``get_logs`` call (default 200).
    """

    def __init__(
        self,
        contract_client: Any,
        rpc_url: str = "",
        contract_address: str = "",
        gateway_private_key: str = "",
        on_settlement: Optional[Callable[[dict], None]] = None,
        on_refund: Optional[Callable[[dict], None]] = None,
        storage: Any = None,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_blocks: int = DEFAULT_MAX_BLOCKS,
    ) -> None:
        self._contract = contract_client
        self._rpc_url = rpc_url or os.getenv("AIMS_RPC_URL", "")
        self._contract_address = contract_address or os.getenv("AIMS_CONTRACT_ADDRESS", "")
        self._gateway_private_key = gateway_private_key or os.getenv("AIMS_GATEWAY_PRIVATE_KEY", "")
        self._on_settlement = on_settlement
        self._on_refund = on_refund
        self._storage = storage
        self._poll_interval = poll_interval
        self._max_blocks = max_blocks

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # InMemory mode tracking
        self._is_inmemory = not hasattr(contract_client, "_w3") if contract_client else True
        self._last_event_count = 0

        # Web3 mode tracking
        self._last_processed_block = 0
        self._w3 = None
        self._ws = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background polling thread."""
        if self._running:
            logger.warning("ChainListener already running")
            return

        # Initialise Web3 connection if needed
        if not self._is_inmemory:
            self._init_web3()

        # Restore last processed block from storage
        if not self._is_inmemory and self._storage is not None:
            saved = self._storage.get(LAST_BLOCK_KEY)
            if saved is not None:
                self._last_processed_block = int(saved)
                logger.info("ChainListener: restored last_processed_block=%d", self._last_processed_block)

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="chain-listener")
        self._thread.start()
        logger.info(
            "ChainListener started (mode=%s, interval=%ds, max_blocks=%d)",
            "inmemory" if self._is_inmemory else "web3",
            self._poll_interval,
            self._max_blocks,
        )

    def stop(self) -> None:
        """Signal the polling thread to stop."""
        self._running = False
        logger.info("ChainListener stopping...")

    @property
    def is_alive(self) -> bool:
        """``True`` if the background thread is running."""
        return self._thread is not None and self._thread.is_alive()

    # ── Web3 initialisation ───────────────────────────────────────────────

    def _init_web3(self) -> None:
        """Lazy-init the Web3 connection."""
        try:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            self._ws = Web3.to_checksum_address(self._contract_address)
            logger.info(
                "ChainListener: connected to %s (block=%d)",
                self._rpc_url, self._w3.eth.block_number,
            )
        except Exception as exc:
            logger.error("ChainListener: Web3 init failed: %s", exc)
            self._w3 = None

    # ── Poll loop ─────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Main loop — runs in the background thread."""
        while self._running:
            try:
                if self._is_inmemory:
                    self._poll_inmemory()
                else:
                    self._poll_web3()
            except Exception as exc:
                logger.error("ChainListener: poll error: %s", exc)
            time.sleep(self._poll_interval)

    # ── InMemory polling ──────────────────────────────────────────────────

    def _poll_inmemory(self) -> None:
        """Read new events from the InMemorySettlementContract event buffer."""
        if not hasattr(self._contract, "_event_buffer"):
            return  # event buffer not available yet

        buffer = self._contract._event_buffer
        current = len(buffer)
        if current <= self._last_event_count:
            return

        new_events = buffer[self._last_event_count:]
        self._last_event_count = current

        for event in new_events:
            self._dispatch(event)

    # ── Web3 polling ──────────────────────────────────────────────────────

    def _poll_web3(self) -> None:
        """Poll ``w3.eth.get_logs`` for new events since last processed block."""
        if self._w3 is None:
            return

        current_block = self._w3.eth.block_number
        if current_block <= self._last_processed_block:
            return  # no new blocks

        from_block = self._last_processed_block + 1
        to_block = min(current_block, from_block + self._max_blocks)

        try:
            logs = self._w3.eth.get_logs({
                "address": self._ws,
                "fromBlock": from_block,
                "toBlock": to_block,
                "topics": [[TASK_SETTLED_TOPIC, TASK_REFUNDED_TOPIC]],
            })
        except Exception as exc:
            logger.error("ChainListener: get_logs failed: %s", exc)
            return

        for log_entry in logs:
            event = self._decode_log(log_entry)
            if event is not None:
                self._dispatch(event)

        # Advance cursor
        self._last_processed_block = to_block
        if self._storage is not None:
            self._storage.set(LAST_BLOCK_KEY, str(to_block))

        # If we hit the max_blocks ceiling, schedule an immediate re-poll
        if to_block < current_block:
            logger.debug("ChainListener: more blocks to process; re-polling immediately")

    # ── Log decoding ──────────────────────────────────────────────────────

    def _decode_log(self, log_entry: dict) -> Optional[dict]:
        """Decode a ``get_logs`` log entry into a structured event dict.

        Uses the ``AIMS_AGENT_GATEWAY_ABI`` event definitions for indexed/
        non-indexed parameter decoding.
        """
        topic = log_entry.get("topics", [None])[0]
        if topic is None:
            return None

        topic_hex = topic.hex() if isinstance(topic, bytes) else topic

        try:
            if topic_hex == TASK_SETTLED_TOPIC:
                return self._decode_settled(log_entry)
            elif topic_hex == TASK_REFUNDED_TOPIC:
                return self._decode_refunded(log_entry)
        except Exception as exc:
            logger.warning("ChainListener: log decode error: %s", exc)

        return None

    def _decode_settled(self, log_entry: dict) -> dict:
        """Decode a ``TaskSettled`` event from a raw log entry.

        Indexed params are in ``topics[1:]``; non-indexed are in ``data``.
        """
        topics = log_entry.get("topics", [])
        data_hex = log_entry.get("data", "0x")

        from eth_abi import decode
        from eth_utils import to_bytes

        # Indexed: taskId (bytes32), skillIdHash (bytes32), consumer (address)
        task_id_bytes = to_bytes(hexstr=topics[1].hex() if isinstance(topics[1], bytes) else topics[1])
        skill_id_hash = to_bytes(hexstr=topics[2].hex() if isinstance(topics[2], bytes) else topics[2])
        consumer_bytes = to_bytes(hexstr=topics[3].hex() if isinstance(topics[3], bytes) else topics[3])
        consumer = "0x" + consumer_bytes[-20:].hex()

        # Non-indexed: worker (address), totalAmount (uint256), workerShare (uint256),
        #              developerShare (uint256), treasuryShare (uint256)
        data_bytes = to_bytes(hexstr=data_hex)
        decoded = decode(
            ["address", "uint256", "uint256", "uint256", "uint256"],
            data_bytes,
        )

        return {
            "type": "TaskSettled",
            "task_id": task_id_bytes.hex(),
            "skill_id_hash": skill_id_hash.hex(),
            "consumer": consumer,
            "worker": decoded[0],
            "total_amount": decoded[1],
            "worker_share": decoded[2],
            "developer_share": decoded[3],
            "treasury_share": decoded[4],
            "block_number": log_entry.get("blockNumber", 0),
            "tx_hash": log_entry.get("transactionHash", "").hex()
                        if isinstance(log_entry.get("transactionHash"), bytes)
                        else log_entry.get("transactionHash", ""),
            "ts": time.time(),
        }

    def _decode_refunded(self, log_entry: dict) -> dict:
        """Decode a ``TaskRefunded`` event from a raw log entry."""
        topics = log_entry.get("topics", [])
        data_hex = log_entry.get("data", "0x")

        from eth_abi import decode
        from eth_utils import to_bytes

        # Indexed: taskId (bytes32), consumer (address)
        task_id_bytes = to_bytes(hexstr=topics[1].hex() if isinstance(topics[1], bytes) else topics[1])
        consumer_bytes = to_bytes(hexstr=topics[2].hex() if isinstance(topics[2], bytes) else topics[2])
        consumer = "0x" + consumer_bytes[-20:].hex()

        # Non-indexed: amount (uint256), reason (string)
        data_bytes = to_bytes(hexstr=data_hex)
        decoded = decode(["uint256", "string"], data_bytes)

        return {
            "type": "TaskRefunded",
            "task_id": task_id_bytes.hex(),
            "consumer": consumer,
            "amount": decoded[0],
            "reason": decoded[1],
            "block_number": log_entry.get("blockNumber", 0),
            "tx_hash": log_entry.get("transactionHash", "").hex()
                        if isinstance(log_entry.get("transactionHash"), bytes)
                        else log_entry.get("transactionHash", ""),
            "ts": time.time(),
        }

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _dispatch(self, event: dict) -> None:
        """Route a decoded event to the appropriate callback."""
        event_type = event.get("type", "")
        logger.info(
            "ChainEvent: %s task_id=%s block=%s",
            event_type,
            event.get("task_id", "")[:16],
            event.get("block_number", "?"),
        )

        if event_type == "TaskSettled" and self._on_settlement is not None:
            self._on_settlement(event)
        elif event_type == "TaskRefunded" and self._on_refund is not None:
            self._on_refund(event)

    # ── Chain info ────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return listener status for health checks."""
        return {
            "running": self._running,
            "is_alive": self.is_alive,
            "mode": "inmemory" if self._is_inmemory else "web3",
            "last_processed_block": self._last_processed_block,
            "last_event_count": self._last_event_count,
            "poll_interval": self._poll_interval,
        }
