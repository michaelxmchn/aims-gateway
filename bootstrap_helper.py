#!/usr/bin/env python3
"""AIMS Bootstrap Helper — Discovery → Mapping → Execution for AI agents.

Minimal client that any Python-based AI agent (or automation script) can
use to discover and invoke AIMS skills with zero configuration.

Agents no longer need a shared HMAC secret.  Each client auto-generates (or
accepts) an ECDSA wallet and signs every POST with an EIP-191 ``personal_sign``
signature over the raw request body.

Usage:
    from bootstrap_helper import AIMSClient

    client = AIMSClient()
    skills = client.discover()
    result = client.run_skill("amazon_scraper", {"search_term": "RTX 5090"}, user_id="alice")
    print(result)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct


# ── Defaults ─────────────────────────────────────────────────────────────

GATEWAY_URL = "https://aims-gateway.fly.dev"


# ── EIP-191 personal_sign signing ───────────────────────────────────────

def _headers(body: bytes, wallet: Account) -> dict[str, str]:
    """Build EIP-191 personal_sign-signed headers for a POST request.

    The wallet signs the raw request body bytes.  The gateway middleware
    recovers the signer with ``encode_defunct(primitive=body)`` and checks
    it matches ``X-Wallet-Address``.
    """
    ts = str(int(time.time()))
    signable_message = encode_defunct(primitive=body)
    signed = wallet.sign_message(signable_message)
    return {
        "Content-Type": "application/json",
        "X-Wallet-Address": wallet.address,
        "X-Signature": signed.signature.hex(),
        "X-Timestamp": ts,
    }


# ── HTTP helpers ─────────────────────────────────────────────────────────

def _get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, payload: dict, wallet: Account) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(body, wallet), method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


# ── AIMS Client ──────────────────────────────────────────────────────────

class AIMSClient:
    """A self-bootstrapping client for the AIMS DePIN network.

    Every request is signed with an ECDSA wallet (auto-created or injected).
    No shared HMAC secret required.

    Usage:
        client = AIMSClient()
        skills = client.discover()
        # ... pick a skill ...
        result = client.run_skill("amazon_scraper", {...}, user_id="alice")
    """

    def __init__(self, gateway_url: str = GATEWAY_URL, private_key: str | None = None) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.wallet = Account.from_key(private_key) if private_key else Account.create()
        self.user_id = self.wallet.address
        self._skills: list[dict[str, Any]] = []
        self._skill_map: dict[str, dict[str, Any]] = {}

    # ── Discovery ─────────────────────────────────────────────────────────

    def discover(self) -> list[dict[str, Any]]:
        """Call GET /api/discovery and return the skills list.

        Also populates ``self._skill_map`` keyed by ``skill_id``.
        """
        data = _get(f"{self.gateway_url}/api/discovery")
        self._skills = data.get("skills", [])
        self._skill_map = {s["skill_id"]: s for s in self._skills}
        return self._skills

    def list_skills(self) -> list[dict[str, Any]]:
        """Return the last-discovered skills (call ``discover()`` first)."""
        return self._skills

    def find_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Look up a skill by ID from the discovery cache."""
        return self._skill_map.get(skill_id)

    # ── Execution ─────────────────────────────────────────────────────────

    def run_skill(self, skill_id: str, params: dict[str, Any], user_id: str | None = None,
                  compute_tier: int = 1, max_budget: float = 2.0) -> dict[str, Any]:
        """Execute a skill via POST /api/run, poll until completion, return result.

        This is a blocking call — it polls GET /api/tasks/{task_id}/status
        every 2 seconds until the task reaches SUCCESS or FAILED.

        Args:
            skill_id: The skill to invoke (must exist in discovery results).
            params: Parameters matching the skill's input_schema.
            user_id: The end user identifier (defaults to client's wallet address).
            compute_tier: 1=standard, 2=premium, 3=enterprise.
            max_budget: Maximum USDT budget for this task.

        Returns:
            The final task status response with result data on success.

        Raises:
            ValueError: If skill_id is not found in discovery cache.
            RuntimeError: If the task fails or the gateway returns an error.
        """
        uid = user_id or self.user_id

        # Check discovery cache
        if not self._skill_map:
            self.discover()
        if skill_id not in self._skill_map:
            raise ValueError(
                f"Skill '{skill_id}' not found. Available: {list(self._skill_map.keys())}"
            )

        # Validate required params against input_schema
        schema = self._skill_map[skill_id].get("manifest", {}).get("input_schema", {})
        required = schema.get("required", [])
        missing = [f for f in required if f not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")

        # Submit task — wallet signs the request body automatically
        payload = {
            "skill_id": skill_id,
            "params": params,
            "user_id": uid,
            "compute_tier": compute_tier,
            "max_budget": max_budget,
        }
        run_resp = _post(f"{self.gateway_url}/api/run", payload, self.wallet)
        task_id = run_resp.get("task_id")
        if not task_id:
            raise RuntimeError(f"/api/run returned no task_id: {run_resp}")

        # Poll until completion
        status_url = f"{self.gateway_url}/api/tasks/{task_id}/status"
        for _attempt in range(60):  # max 60 × 2s = 120s
            poll = _get(status_url)
            st = poll.get("status")
            if st == "SUCCESS":
                return poll
            if st == "FAILED":
                raise RuntimeError(f"Task {task_id} FAILED: {poll.get('outcome', 'unknown')}")
            time.sleep(2)

        raise TimeoutError(f"Task {task_id} did not complete within 120 seconds")

    # ── Heartbeat ─────────────────────────────────────────────────────────

    def heartbeat(self) -> dict[str, Any]:
        """Send a heartbeat to keep this worker registered as active."""
        return _post(f"{self.gateway_url}/api/workers/heartbeat",
                     {"worker_id": self.user_id}, self.wallet)


# ── CLI entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    client = AIMSClient()

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        skills = client.discover()
        print(f"\nAIMS Gateway: {GATEWAY_URL}")
        print(f"Wallet: {client.wallet.address}")
        print(f"Skills ({len(skills)}):\n")
        for s in skills:
            m = s.get("manifest", {})
            print(f"  {s['skill_id']:<25} {m.get('description', '')[:60]}")
        print()

    elif len(sys.argv) > 2 and sys.argv[1] == "run":
        skill_id = sys.argv[2]
        params = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        user_id = sys.argv[4] if len(sys.argv) > 4 else "cli-user"
        client.discover()
        result = client.run_skill(skill_id, params, user_id=user_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print("Usage:")
        print("  python bootstrap_helper.py list              # List available skills")
        print("  python bootstrap_helper.py run <skill> <json> [user]  # Execute a skill")
        print()
        print("Examples:")
        print("  python bootstrap_helper.py list")
        print('  python bootstrap_helper.py run amazon_scraper \'{"search_term":"RTX 5090"}\' alice')
