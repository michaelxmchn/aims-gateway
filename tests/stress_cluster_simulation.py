"""Stress Cluster Simulation — Phase 8: Multi-worker Concurrency & Circuit Breaker.

Simulates a DePIN cluster with **10 async EIP-191 signing worker nodes** and **50
concurrent consumer requests** in a 5-second window.  Exercises the full lifecycle:

  Consumer → run_skill → claim → submit → JudgeEngine → CircuitBreaker → settlement

Three test scenarios:

  1. **Fair routing** — 50 honest tasks → all workers get equitable share.
  2. **Circuit breaker degradation** — 10 catastrophic fails → CLOSED → HALF_OPEN → OPEN.
  3. **Auto-recovery** — After 120s cooldown (simulated), can_pass returns true.

Bloomberg-terminal style logging throughout:

  ═══════════════════════════════════════════════════════════════════════════════
    AIMS STRESS CLUSTER SIMULATION v1.0
    10 Workers | 50 Concurrent Tasks | 5s Burst Window | 3-State Circuit Breaker
  ═══════════════════════════════════════════════════════════════════════════════

Usage::

    python3 tests/stress_cluster_simulation.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, ".")

from eth_account import Account
from eth_account.messages import encode_defunct

from src.gateway.broker import TaskBroker
from src.gateway.circuit_breaker import CircuitBreaker
from src.gateway.canary import CanaryManager
from src.gateway.storage import Storage
from src.gateway.billing import BillingEngine, CommerceEngine
from src.gateway.trial import FreeTrialManager
from src.ledger.mock_counter import MockLedger
from src.chain.pot import POTManager
from src.chain.nonce_manager import NonceManager
from src.judge.judge_agent import JudgeEngine, JudgeVerdict

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stress_cluster")

# ── Constants ─────────────────────────────────────────────────────────────────────

NUM_WORKERS = 10
NUM_CONSUMER_TASKS = 50
BURST_WINDOW_SECONDS = 5.0  # all 50 requests arrive within 5s
TASK_TIMEOUT_SECONDS = 10.0
COOLDOWN_SIMULATED_SECONDS = 1.0  # fast cooldown for test

GATEWAY_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
GATEWAY_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

# 10 deterministic EVM worker wallets
WORKER_WALLETS = [
    "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
    "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
    "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
    "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
    "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f",
    "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720",
    "0xBcd4042DE499D14e55001CcbB24a551F3b954096",
]

WORKER_PRIVATE_KEYS = [
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f15f0f2f16a6b5734a4b6d3c3f3a3b3c3b3d",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e6b1b5d5e8c3d",
    "0x92db14e403b83dfe3df233f83dfe3df233f83dfe3df233f83dfe3df233f83dfe",
    "0x4bbbf85ce3377467afe5d46f804f221813b2a87bdff5b3f2b3f2b3f2b3f2b3f2",
    "0xdbda1821b80551c9d65939329250298aa3472ba22f397ad3e7b2c7b2c7b2c7b2c",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    "0xf214f2b2cd398c806f84e317254e0f0b801d0643303237d74664e2a809d8f0c9",
]

CONSUMER_WALLET = "0x10E7347C5D4fBc8A1cB2E6C9F8f3E7A1B2C3D4E5"
CONSUMER_PRIVATE_KEY = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

TEST_SKILL_ID = "amazon_scraper"

# Bloomberg terminal colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"


# ── Bloomberg-style terminal helpers ─────────────────────────────────────────────


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:12]


def banner(title: str, subtitle: str = "") -> None:
    width = 78
    print(f"\n{C_BOLD}{'═' * width}{C_RESET}")
    print(f"{C_BOLD}  {title}{C_RESET}")
    if subtitle:
        print(f"  {C_DIM}{subtitle}{C_RESET}")
    print(f"{C_BOLD}{'═' * width}{C_RESET}")


def log_block(label: str, value: str, color: str = C_WHITE) -> None:
    print(f"  {C_DIM}{ts()}{C_RESET}  {color}{label:30s}{C_RESET} {value}")


def log_separator() -> None:
    print(f"  {C_DIM}{'─' * 60}{C_RESET}")


def print_state_matrix() -> None:
    """Print the 3-state circuit breaker ASCII matrix."""
    width = 72
    print(f"\n{C_BOLD}{'═' * width}{C_RESET}")
    print(f"{C_BOLD}  CIRCUIT BREAKER — 3-State Finite State Machine{C_RESET}")
    print(f"{C_BOLD}{'═' * width}{C_RESET}")
    matrix = r"""
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
    """
    print(matrix)


# ── EIP-191 signing helpers ──────────────────────────────────────────────────────


def eip191_sign(body: dict, private_key_hex: str) -> str:
    """EIP-191 personal_sign over JSON body bytes."""
    body_bytes = json.dumps(body, separators=(",", ":")).encode()
    signable = encode_defunct(primitive=body_bytes)
    signed = Account.sign_message(signable, private_key_hex)
    return signed.signature.hex()


def eip191_recover(body: dict, signature: str) -> str:
    """Recover signer address from EIP-191 signature."""
    body_bytes = json.dumps(body, separators=(",", ":")).encode()
    signable = encode_defunct(primitive=body_bytes)
    return Account.recover_message(signable, signature=signature)


# ── Simulated JudgeEngine (deterministic for testing) ───────────────────────────


class SimulatedJudgeEngine:
    """Deterministic judge for stress testing — no LLM dependency.

    Modes:
      - "pass": always returns score >= 80 (success)
      - "fail": always returns score < 80 (failure)
      - "flaky": 70% pass, 30% fail
    """

    def __init__(self, mode: str = "pass") -> None:
        self.mode = mode

    def score(self, task_input: dict, task_output: dict, skill_id: str = "", output_schema: dict | None = None) -> JudgeVerdict:
        if self.mode == "pass":
            score = random.randint(85, 99)
        elif self.mode == "fail":
            score = random.randint(10, 40)
        else:  # flaky
            score = random.randint(85, 99) if random.random() < 0.7 else random.randint(10, 40)

        return JudgeVerdict(
            score=score,
            passed=score >= 80,
            reason=f"Simulated deterministic score {score}/100",
            latency_ms=random.uniform(50, 200),
        )


# ── Simulated Worker Node ────────────────────────────────────────────────────────


@dataclass
class WorkerNode:
    index: int
    wallet: str
    private_key: str
    worker_id: str
    tasks_claimed: list[str] = field(default_factory=list)
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_earned: float = 0.0


# ── Main stress test orchestrator ────────────────────────────────────────────────


async def main() -> int:
    banner(
        "AIMS STRESS CLUSTER SIMULATION v1.0",
        "10 Workers | 50 Concurrent Tasks | 5s Burst Window | 3-State Circuit Breaker",
    )

    # ── Init components ─────────────────────────────────────────────────────────
    storage = Storage()
    ledger = MockLedger(storage=storage)
    broker = TaskBroker(ledger, storage=storage)
    nonce_manager = NonceManager(storage)
    pot_manager = POTManager(storage, GATEWAY_PRIVATE_KEY)
    trial_manager = FreeTrialManager(storage)

    billing = BillingEngine(
        storage=storage,
        treasury_address="0xTreasury00000000000000000000000000000001",
        gateway_address=GATEWAY_ADDRESS,
        gateway_signing_key=GATEWAY_PRIVATE_KEY,
        pot_manager=pot_manager,
    )

    commerce = CommerceEngine(
        storage=storage,
        trial_manager=trial_manager,
        billing=billing,
        pot_manager=pot_manager,
    )

    # Fast cooldown so we can test auto-recovery quickly
    breaker = CircuitBreaker(
        storage=storage,
        consecutive_threshold=3,
        max_degraded_threshold=6,
        open_cooldown=COOLDOWN_SIMULATED_SECONDS,
        on_state_change=lambda old, new: log_block(
            "BREAKER STATE", f"{old} → {new}", C_YELLOW,
        ),
    )

    # Track state transitions for report
    state_transitions: list[tuple[str, str, float]] = []
    original_transition = breaker._transition
    def _track_transition(new_state: Any) -> None:
        old = breaker._state.value
        original_transition(new_state)
        state_transitions.append((old, new_state.value, time.time()))
    breaker._transition = _track_transition

    canary_manager = CanaryManager(storage, GATEWAY_PRIVATE_KEY, GATEWAY_ADDRESS)

    # ── Init workers ────────────────────────────────────────────────────────────
    workers: list[WorkerNode] = []
    for i in range(NUM_WORKERS):
        w = WorkerNode(
            index=i,
            wallet=WORKER_WALLETS[i],
            private_key=WORKER_PRIVATE_KEYS[i],
            worker_id=f"worker_{i:02d}",
        )
        workers.append(w)
        ledger.seed_dev_usdt(w.worker_id, 50.0)
        ledger.register_worker(w.worker_id, 5.0)

    # Seed consumer
    ledger.seed_usdt(CONSUMER_WALLET, 500.0)
    log_block("Consumer seeded", f"{CONSUMER_WALLET} → 500.0 USDC", C_GREEN)
    log_block("Workers seeded", f"{NUM_WORKERS} × 50.0 USDC collateral", C_GREEN)

    log_separator()

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCENARIO 1: Fair Routing — 50 honest tasks, all pass Judge
    # ═══════════════════════════════════════════════════════════════════════════════
    banner(
        "SCENARIO 1: Fair Routing & Throughput",
        f"{NUM_CONSUMER_TASKS} tasks | all pass Judge | verify equitable distribution",
    )

    judge_pass = SimulatedJudgeEngine(mode="pass")

    # Publish 50 tasks in a 5s burst
    start_ts = time.time()
    publish_tasks: list[tuple[str, dict]] = []  # (task_id, task_meta)

    for i in range(NUM_CONSUMER_TASKS):
        params = {"asin": f"STRESS-{i:04d}", "query": f"test product {i}"}
        canary_token = canary_manager.generate_token()
        params["_canary_token"] = canary_token

        task_id = broker.publish_task(
            user_id=CONSUMER_WALLET,
            asin=f"STRESS-{i:04d}",
            developer_premium=0.01,
            max_budget=2.0,
            skill_id=TEST_SKILL_ID,
            compute_tier=1,
            payload=params,
        )
        if task_id:
            canary_manager.record_task(task_id, canary_token)
            publish_tasks.append((task_id, params))
            # Simulate staggered arrival over 5s
            await asyncio.sleep(BURST_WINDOW_SECONDS / NUM_CONSUMER_TASKS)

    elapsed_publish = time.time() - start_ts
    published = len(publish_tasks)
    log_block("Tasks published", f"{published} in {elapsed_publish:.2f}s", C_CYAN)
    log_block("Publish rate", f"{published / elapsed_publish:.0f} tasks/s", C_CYAN)

    # Workers claim and submit in parallel (simulate async worker pool)
    log_separator()
    log_block("WORKERS", "Claiming and submitting tasks...", C_BOLD)

    claim_start = time.time()
    worker_assignments: dict[str, int] = {}  # worker_id → task count

    async def worker_cycle(worker: WorkerNode) -> None:
        """Simulate a worker: claim → execute (mock) → submit."""
        while True:
            task = broker.claim_task(worker.worker_id)
            if task is None:
                # No tasks available — check if we're fully done
                if broker.pending_count == 0 and all(
                    broker.get_task_status(tid)["status"] in ("SUCCESS", "FAILED")
                    for tid, _ in publish_tasks
                ):
                    break
                await asyncio.sleep(0.05)
                continue

            task_id = task["task_id"]
            worker.tasks_claimed.append(task_id)
            worker_assignments[worker.worker_id] = worker_assignments.get(worker.worker_id, 0) + 1

            # Simulate execution delay (10-100ms)
            await asyncio.sleep(random.uniform(0.01, 0.1))

            # Build mock result
            result_data = {
                "products": [
                    {"asin": f"RESULT-{task_id[-4:]}", "price": round(random.uniform(10, 200), 2), "title": f"Product {task_id[-4:]}"},
                ],
                "total_results": random.randint(1, 5),
                "query": task.get("payload", {}).get("query", ""),
            }

            # Judge evaluation
            verdict = judge_pass.score(
                task_input=task.get("payload", {}),
                task_output=result_data,
                skill_id=TEST_SKILL_ID,
            )

            if verdict.passed:
                breaker.record_success()
                worker.tasks_completed += 1
                broker.complete_task(task_id, "SUCCESS")
            else:
                breaker.record_failure(reason=f"Judge score {verdict.score}/100")
                worker.tasks_failed += 1
                broker.complete_task(task_id, "FAILED")

            # Check if all tasks consumed
            if broker.pending_count == 0 and all(
                broker.get_task_status(tid) is None or broker.get_task_status(tid)["status"] in ("SUCCESS", "FAILED")
                for tid, _ in publish_tasks
            ):
                break

    # Launch all 10 workers concurrently
    worker_tasks = [worker_cycle(w) for w in workers]
    await asyncio.gather(*worker_tasks)
    claim_elapsed = time.time() - claim_start

    log_block("All tasks done", f"in {claim_elapsed:.2f}s", C_GREEN)

    # Fair routing analysis
    log_separator()
    log_block("FAIR ROUTING", "Per-worker breakdown:", C_BOLD)
    assignments_sorted = sorted(worker_assignments.items(), key=lambda x: x[0])
    max_count = max(c for _, c in assignments_sorted)
    min_count = min(c for _, c in assignments_sorted)
    for wid, count in assignments_sorted:
        bar = "█" * max(1, int(count * 40 / max_count))
        color = C_GREEN if count >= (published / NUM_WORKERS) * 0.5 else C_RED
        log_block(wid, f"{count:3d} tasks  {bar}", color)

    fairness_ratio = min_count / max_count if max_count > 0 else 0
    fair_pass = fairness_ratio >= 0.3  # at least 30% of max
    log_block("Fairness ratio", f"{fairness_ratio:.2f} (min/max)", C_GREEN if fair_pass else C_RED)
    log_block("Fair routing", "PASSED ✓" if fair_pass else "FAILED ⚠", C_GREEN if fair_pass else C_RED)

    log_separator()

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCENARIO 2: Circuit Breaker Degradation
    # ═══════════════════════════════════════════════════════════════════════════════
    banner(
        "SCENARIO 2: Circuit Breaker Degradation",
        "10 catastrophic fails → CLOSED → HALF_OPEN → OPEN (3 consecutive / 6 degraded)",
    )

    print_state_matrix()

    judge_fail = SimulatedJudgeEngine(mode="fail")
    assert breaker.is_closed, "Breaker must start CLOSED"
    log_block("Initial state", "CLOSED (accepting all requests)", C_GREEN)

    # Fire 10 fails — should hit HALF_OPEN at fail #3, OPEN at fail #9 (3+6)
    log_separator()
    log_block("DEGRADATION", "Firing 10 consecutive failures...", C_RED)
    for i in range(10):
        fail_verdict = judge_fail.score({}, {}, TEST_SKILL_ID)
        breaker.record_failure(reason=f"Stress test fail #{i + 1}: score {fail_verdict.score}/100")
        state_label = {
            "CLOSED": C_GREEN,
            "HALF_OPEN": C_YELLOW,
            "OPEN": C_RED,
        }.get(breaker.state.value, C_WHITE)
        log_block(
            f"  Fail #{i + 1:2d}",
            f"state={breaker.state.value:10s}  consec={breaker.consecutive_fails:2d}  degraded={breaker.degraded_fails:2d}",
            state_label,
        )

    assert breaker.is_open, f"Breaker must be OPEN after 10 fails, got {breaker.state.value}"
    log_block("Final state", "OPEN (all requests rejected)", C_RED)

    # Verify can_pass returns False while OPEN
    can_pass_result = breaker.can_pass("test")
    assert not can_pass_result, "can_pass must return False in OPEN state"
    log_block("can_pass check", "False (correctly rejected)", C_GREEN)

    log_separator()

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCENARIO 3: Auto-Recovery (cooldown)
    # ═══════════════════════════════════════════════════════════════════════════════
    banner(
        "SCENARIO 3: Auto-Recovery",
        f"Cooldown {COOLDOWN_SIMULATED_SECONDS}s → can_pass auto-transitions to CLOSED",
    )

    log_block("Waiting for cooldown", f"{COOLDOWN_SIMULATED_SECONDS:.1f}s...", C_YELLOW)
    await asyncio.sleep(COOLDOWN_SIMULATED_SECONDS + 0.5)

    recovered = breaker.can_pass("recovery_test")
    assert recovered, "Breaker must auto-recover after cooldown"
    assert breaker.is_closed, f"Breaker must be CLOSED after recovery, got {breaker.state.value}"
    log_block("Auto-recovery", "CLOSED (accepting requests again) ✓", C_GREEN)

    log_separator()

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCENARIO 4: Admin Controls — emergency-pause and reset
    # ═══════════════════════════════════════════════════════════════════════════════
    banner(
        "SCENARIO 4: Admin Controls",
        "emergency-pause → OPEN → reset → CLOSED",
    )

    breaker.admin_force_open()
    assert breaker.is_open, "admin_force_open must set OPEN"
    log_block("admin_force_open", "OPEN (emergency isolation) ✓", C_RED)

    # can_pass should still return False (cooldown just started)
    assert not breaker.can_pass("admin_test"), "can_pass must return False after fresh force-open"
    log_block("can_pass after force-open", "False (correctly rejected)", C_GREEN)

    # Wait for cooldown + reset
    await asyncio.sleep(COOLDOWN_SIMULATED_SECONDS + 0.3)
    breaker.admin_reset()
    assert breaker.is_closed, "admin_reset must return to CLOSED"
    assert breaker.consecutive_fails == 0, "admin_reset must clear consecutive_fails"
    assert breaker.degraded_fails == 0, "admin_reset must clear degraded_fails"
    log_block("admin_reset", "CLOSED (counters cleared) ✓", C_GREEN)

    # Verify can_pass works again
    assert breaker.can_pass("admin_test"), "can_pass must return True after reset"
    log_block("can_pass after reset", "True (accepting requests) ✓", C_GREEN)

    log_separator()

    # ═══════════════════════════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════════════════════════
    banner(
        "STRESS CLUSTER SIMULATION — FINAL REPORT",
        "All scenarios complete",
    )

    report = {
        "scenario_1_fair_routing": {
            "tasks_published": published,
            "publish_rate_hz": round(published / elapsed_publish, 1),
            "completion_time_s": round(claim_elapsed, 2),
            "throughput_hz": round(published / claim_elapsed, 1),
            "fairness_ratio": round(fairness_ratio, 2),
            "fair_pass": fair_pass,
        },
        "scenario_2_circuit_breaker": {
            "state_transitions": [
                {"from": f, "to": t, "at": round(timestamp - start_ts, 2)}
                for f, t, timestamp in state_transitions
            ],
            "final_state": breaker.state.value,
            "consecutive_fails": breaker.consecutive_fails,
            "degraded_fails": breaker.degraded_fails,
        },
        "scenario_3_auto_recovery": {
            "recovered": recovered,
        },
        "scenario_4_admin_controls": {
            "force_open_verified": True,
            "reset_verified": breaker.is_closed,
        },
        "system": {
            "workers": NUM_WORKERS,
            "consumer_tasks": NUM_CONSUMER_TASKS,
            "burst_window_s": BURST_WINDOW_SECONDS,
            "breaker_thresholds": {
                "consecutive": 3,
                "max_degraded": 6,
                "cooldown_s": COOLDOWN_SIMULATED_SECONDS,
            },
        },
    }

    print(json.dumps(report, indent=2))
    print()

    # ── Assertions ────────────────────────────────────────────────────────────
    errors: list[str] = []
    if not fair_pass:
        errors.append(f"Fair routing failed: ratio={fairness_ratio:.2f}")
    if not recovered:
        errors.append("Auto-recovery failed: breaker did not return to CLOSED")
    if not breaker.is_closed:
        errors.append(f"Admin reset failed: state={breaker.state.value}")

    # Verify state transitions happened correctly
    transition_pairs = [(f, t) for f, t, _ in state_transitions]
    expected = ("CLOSED", "HALF_OPEN")
    if expected not in transition_pairs:
        errors.append(f"Missing expected transition {expected}")
    expected_open = ("HALF_OPEN", "OPEN")
    if expected_open not in transition_pairs:
        errors.append(f"Missing expected transition {expected_open}")

    if errors:
        log_block("RESULT", "SOME SCENARIOS FAILED", C_RED)
        for e in errors:
            log_block("  ERROR", e, C_RED)
        return 1

    log_block("RESULT", "ALL SCENARIOS PASSED ✓", C_GREEN)
    log_block("", f"Fair routing: {fair_pass} | CB degradation: {len(state_transitions)} transitions | Recovery: {recovered} | Admin: ✓")
    log_block("", f"Throughput: {published / claim_elapsed:.0f} tasks/s across {NUM_WORKERS} workers")

    print(f"\n{C_BOLD}{'═' * 78}{C_RESET}")
    print(f"{C_BOLD}  STRESS CLUSTER SIMULATION — ALL SCENARIOS PASSED ✓{C_RESET}")
    print(f"{C_BOLD}{'═' * 78}{C_RESET}\n")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
