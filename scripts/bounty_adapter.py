#!/usr/bin/env python3
"""
Bountycaster Adapter — Bountycaster API → Gitcoin-compatible HTTP proxy.
Serves Bountycaster bounty data in the format GitcoinPoller expects.

Usage:
  python3 scripts/bounty_adapter.py                # HTTP server on :9812
  python3 scripts/bounty_adapter.py --once         # fetch once, print JSON, exit
  python3 scripts/bounty_adapter.py --mock         # serve historical mock data
"""

import json, os, re, sys, time, uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

import requests

BOUNTYCASTER_API = os.getenv("BOUNTYCASTER_API", "https://www.bountycaster.xyz")
ADAPTER_PORT = int(os.getenv("BOUNTY_ADAPTER_PORT", "9812"))
CACHE_TTL = int(os.getenv("BOUNTY_CACHE_TTL", "60"))

# ── Real historical Bountycaster bounty data for dry-run / mock mode ──
# These are genuine completed bounties fetched from the Bountycaster API.
HISTORICAL_BOUNTIES = [
    {
        "title": "Create v2 frame using NextJS, Tailwind, react-icons, supabase for $NATIVE",
        "description": (
            "$250 USDC to create v2 frame using NextJS, Tailwind, react-icons, supabase for $NATIVE"
            "\n\n- should enable in-frame token buy"
            "\n- welcome noti upon install"
            "\n- thank you noti upon swap"
            "\n- new announcement noti"
            "\n- load announcements from DB"
            "\n\nI will open source for others to use with full credit to initial author."
        ),
        "github_url": "https://github.com/nonomnouns/native-frame",
        "url": "https://github.com/nonomnouns/native-frame",
        "repo_url": "https://github.com/nonomnouns/native-frame",
        "status": "OPEN",
        "value_in_usdt": "250",
    },
    {
        "title": "Create a TypeScript script for Legacy Payment Flows Migration",
        "description": (
            "8000 degen tip for someone to create a ts script that for a given list of addresses"
            " (across base and optimism), returns a list of tokens and total balance!"
            "\n\nInput (json file): [{ 'address': '0x', 'network': 8453 | 10 }]"
            "\nOutput: [{ 'address': '0x', 'network': 8453 | 10, 'tokens': string[], totalBalanceUSD: number }]"
            "\n\nScript should be committed to Github and access granted if private or link to public!"
        ),
        "github_url": "https://github.com/jhonceth/balanceUSDToken",
        "url": "https://github.com/jhonceth/balanceUSDToken",
        "repo_url": "https://github.com/jhonceth/balanceUSDToken",
        "status": "OPEN",
        "value_in_usdt": "84",
    },
    {
        "title": "Moon energy degen mode social bounty",
        "description": (
            "Going full degen mode today, wish me luck - need that moon energy."
            "\n\nAmount: 1 USDC | Deadline: 2025-09-27"
            "\n\nThis is a social engagement bounty, not a coding task."
        ),
        "github_url": "",
        "url": "",
        "repo_url": "",
        "status": "OPEN",
        "value_in_usdt": "1",
    },
]

# Assign stable IDs
for i, b in enumerate(HISTORICAL_BOUNTIES, 1):
    b["id"] = f"bc-mock-{i:03d}"
    b["source"] = "bountycaster"


class BountycasterClient:
    """Low-level client for the Bountycaster API."""

    def __init__(self, base_url: str = BOUNTYCASTER_API):
        self.base_url = base_url
        self._session = requests.Session()
        self._cache: dict[str, dict] = {}
        self._cache_ts: dict[str, float] = {}

    def list_open(self) -> list[dict]:
        """Fetch open bounties — returns list of raw bounty objects."""
        resp = self._session.get(
            f"{self.base_url}/api/v1/bounties/open",
            timeout=15,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("bounties", [])

    def get_bounty(self, hash_id: str) -> Optional[dict]:
        """Fetch individual bounty details by hash."""
        now = time.time()
        if hash_id in self._cache and now - self._cache_ts.get(hash_id, 0) < CACHE_TTL:
            return self._cache[hash_id]

        try:
            resp = self._session.get(
                f"{self.base_url}/api/v1/bounty/{hash_id}",
                timeout=15,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._cache[hash_id] = data
            self._cache_ts[hash_id] = now
            return data
        except requests.RequestException as e:
            print(f"[BCAdapter] Failed to fetch bounty {hash_id}: {e}", flush=True)
            return None

    @staticmethod
    def convert(raw: dict) -> Optional[dict]:
        """Convert a Bountycaster bounty dict → Gitcoin-compatible format."""
        if not raw or not raw.get("title"):
            return None

        platform = raw.get("platform") or {}
        hash_id = (platform.get("farcaster") or {}).get("hash", "")
        if not hash_id:
            return None

        title = raw.get("title", "Untitled Bounty")
        summary = raw.get("summary_text", "")

        # Reward
        reward = raw.get("reward_summary") or {}
        usd_value = reward.get("usd_value", "0")
        unit_amount = str(reward.get("unit_amount", "0")).replace(",", "")
        symbol = reward.get("symbol", "USD")

        # Extract GitHub URL from summary text or feed entries
        github_url = _extract_github(summary, raw.get("feed", []))

        # Tags
        tags = raw.get("tag_slugs", [])

        return {
            "id": f"bc:{hash_id[:12]}",
            "title": title,
            "description": summary or title,
            "github_url": github_url,
            "url": github_url or f"{BOUNTYCASTER_API}/bounty/{hash_id}",
            "repo_url": github_url,
            "status": "OPEN",
            "value_in_usdt": usd_value or unit_amount,
            "source": "bountycaster",
            "bounty_hash": hash_id,
            "metadata": {
                "reward": reward,
                "tags": tags,
                "symbol": symbol,
                "created_at": raw.get("created_at"),
                "poster": (raw.get("poster") or {}).get("short_name", ""),
            },
        }


def _extract_github(summary: str, feed: list) -> str:
    """Find first GitHub URL in summary text or feed."""
    pattern = r"https?://github\.com/[^\s\r\n,;)\'\"\]>]+"
    for text in [summary] + [f.get("text", "") for f in (feed or [])]:
        m = re.search(pattern, text)
        if m:
            return m.group(0).rstrip("/")
    return ""


def fetch_and_convert() -> list[dict]:
    """Fetch open bounties from Bountycaster and convert to Gitcoin format."""
    client = BountycasterClient()
    results = []

    # Step 1: get the open listing
    raw_list = client.list_open()
    if not raw_list:
        print("[BCAdapter] No open bounties found via API (empty listing)", flush=True)
        return []

    # Step 2: enrich each bounty with details
    for item in raw_list:
        # Try to extract hash
        if isinstance(item, dict):
            platform = item.get("platform") or {}
            hash_id = (platform.get("farcaster") or {}).get("hash", "")
            if not hash_id:
                hash_id = item.get("uid", "")
        else:
            continue

        if not hash_id:
            continue

        detail = client.get_bounty(hash_id)
        if detail:
            converted = client.convert(detail)
            if converted:
                results.append(converted)
                print(f"[BCAdapter] Converted bounty: {converted['title'][:60]}...", flush=True)

    return results


# ── HTTP Server ──

class AdapterHandler(BaseHTTPRequestHandler):
    """Serves Bountycaster bounties as Gitcoin-compatible JSON."""

    def _respond(self, data: list[dict], status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        if self.path == "/health":
            self._respond([{"status": "ok"}])
            return

        if self.path == "/mock":
            self._respond(HISTORICAL_BOUNTIES)
            return

        # Check if server has mock mode forced
        if getattr(self.server, "mock_mode", False):
            self._respond(HISTORICAL_BOUNTIES)
            return

        # Live fetch from Bountycaster
        try:
            results = fetch_and_convert()
            self._respond(results)
        except Exception as e:
            self._respond(
                [{"error": str(e), "message": "Falling back to historical data"}],
                status=503,
            )

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[BCAdapter] {args[0]} {args[1]} {args[2]}\n")


def run_server(mock_mode: bool = False):
    """Start the adapter HTTP server."""
    server = HTTPServer(("0.0.0.0", ADAPTER_PORT), AdapterHandler)
    server.mock_mode = mock_mode
    mode = "MOCK" if mock_mode else "LIVE"
    print(f"[BCAdapter] Serving Bountycaster data ({mode}) on :{ADAPTER_PORT}", flush=True)
    print(f"[BCAdapter] Point GITCOIN_API=http://localhost:{ADAPTER_PORT} at the sniper", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[BCAdapter] Shutting down.", flush=True)
        server.server_close()


# ── CLI ──

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Bountycaster → Gitcoin Adapter — feeds Bountycaster bounties to the sniper"
    )
    parser.add_argument("--once", action="store_true", help="Fetch once, print JSON, exit")
    parser.add_argument("--mock", action="store_true", help="Serve historical mock data instead of live")
    parser.add_argument("--source", action="store_true", help="Print bounties as Python list (for import)")
    args = parser.parse_args()

    if args.once or args.source:
        if args.once:
            try:
                data = fetch_and_convert()
                if not data:
                    data = HISTORICAL_BOUNTIES
            except Exception as e:
                print(f"[BCAdapter] Live fetch failed: {e}", file=sys.stderr)
                data = HISTORICAL_BOUNTIES
        else:
            data = HISTORICAL_BOUNTIES

        if args.source:
            # Print as Python repr for direct import
            print(f"BOUNTYCASTER_BOUNTIES = {json.dumps(data, indent=2)}")
        else:
            print(json.dumps(data, indent=2))
        return

    run_server(mock_mode=args.mock)


if __name__ == "__main__":
    main()
