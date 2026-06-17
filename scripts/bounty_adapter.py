#!/usr/bin/env python3
"""
Multi-Source Bounty Aggregation Gateway
========================================
Unifies Bountycaster + GitHub-funded issues into one live API endpoint.
Serves normalized JSON that gitcoin_sniper.py consumes via GITCOIN_API.

Sources:
  A: Bountycaster — polls www.bountycaster.xyz/api/v1/bounties/open
  B: GitHub Bounties — GitHub Issues Search API for open issues with bounty amounts

Usage:
  python3 scripts/bounty_adapter.py                  # HTTP server on :9812
  python3 scripts/bounty_adapter.py --once            # fetch once, print JSON, exit
  python3 scripts/bounty_adapter.py --mock            # serve historical mock data only
  python3 scripts/bounty_adapter.py --sources         # print per-source breakdown
"""

import json, os, re, sys, time, uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

import requests

# ── Config ──
BOUNTYCASTER_API = os.getenv("BOUNTYCASTER_API", "https://www.bountycaster.xyz")
ADAPTER_PORT = int(os.getenv("BOUNTY_ADAPTER_PORT", "9812"))
CACHE_TTL = int(os.getenv("BOUNTY_CACHE_TTL", "60"))
MIN_BOUNTY_USD = float(os.getenv("MIN_BOUNTY_USD", "10"))
# GitHub: unauthenticated = 60 req/hr; set GITHUB_TOKEN for 5000 req/hr
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_SEARCH_URL = "https://api.github.com/search/issues"

# ── Mock Data ──

HISTORICAL_BOUNTIES = [
    # ── Bountycaster (3 historical) ──
    {
        "id": "bc-mock-001",
        "title": "Create v2 frame using NextJS, Tailwind, react-icons, supabase for $NATIVE",
        "description": (
            "$250 USDC to create v2 frame using NextJS, Tailwind, react-icons, supabase for $NATIVE"
            "\n\n- enable in-frame token buy\n- welcome noti upon install"
            "\n- thank you noti upon swap\n- new announcement noti"
            "\n- load announcements from DB"
        ),
        "github_url": "https://github.com/nonomnouns/native-frame",
        "url": "https://github.com/nonomnouns/native-frame",
        "repo_url": "https://github.com/nonomnouns/native-frame",
        "status": "OPEN",
        "value_in_usdt": "250",
        "source": "bountycaster",
    },
    {
        "id": "bc-mock-002",
        "title": "Create a TypeScript script for Legacy Payment Flows Migration",
        "description": (
            "8000 degen tip for a ts script that for a given list of addresses"
            " (base and optimism), returns tokens and total balance."
            "\n\nInput: [{ 'address': '0x', 'network': 8453 | 10 }]"
            "\nOutput: [{ 'address': '0x', 'network': 8453 | 10, "
            "'tokens': string[], totalBalanceUSD: number }]"
        ),
        "github_url": "https://github.com/jhonceth/balanceUSDToken",
        "url": "https://github.com/jhonceth/balanceUSDToken",
        "repo_url": "https://github.com/jhonceth/balanceUSDToken",
        "status": "OPEN",
        "value_in_usdt": "84",
        "source": "bountycaster",
    },
    {
        "id": "bc-mock-003",
        "title": "Moon energy degen mode social bounty",
        "description": "Going full degen mode today — social engagement bounty, 1 USDC.",
        "github_url": "",
        "url": "",
        "repo_url": "",
        "status": "OPEN",
        "value_in_usdt": "1",
        "source": "bountycaster",
    },
    # ── GitHub Bounties (3 simulated) ──
    {
        "id": "gh-mock-001",
        "title": "Implement ERC-4626 vault with fee-on-transfer support",
        "description": (
            "$500 USDC bounty for implementing a ERC-4626 compliant vault contract "
            "that handles fee-on-transfer tokens correctly. Must include Foundry tests "
            "demonstrating the edge cases."
        ),
        "github_url": "https://github.com/defi-project/yield-vault/issues/42",
        "url": "https://github.com/defi-project/yield-vault/issues/42",
        "repo_url": "https://github.com/defi-project/yield-vault",
        "status": "OPEN",
        "value_in_usdt": "500",
        "source": "github_bounty",
    },
    {
        "id": "gh-mock-002",
        "title": "Add Rate limiting middleware for Express API gateway",
        "description": (
            "$75 reward: implement a configurable rate-limiting middleware for our "
            "Express-based API gateway. Use redis for distributed state. Must include tests."
        ),
        "github_url": "https://github.com/web-infra/api-gateway/issues/128",
        "url": "https://github.com/web-infra/api-gateway/issues/128",
        "repo_url": "https://github.com/web-infra/api-gateway",
        "status": "OPEN",
        "value_in_usdt": "75",
        "source": "github_bounty",
    },
    {
        "id": "gh-mock-003",
        "title": "Build CLI tool for database migration across MySQL and PostgreSQL",
        "description": (
            "$200 USDC reward for a Python CLI that can migrate schema and data "
            "between MySQL and PostgreSQL with type mapping and dry-run mode."
        ),
        "github_url": "https://github.com/data-tools/db-sync/issues/7",
        "url": "https://github.com/data-tools/db-sync/issues/7",
        "repo_url": "https://github.com/data-tools/db-sync",
        "status": "OPEN",
        "value_in_usdt": "200",
        "source": "github_bounty",
    },
]


class DedupEngine:
    """Deduplicate bounties by their source URL (github_url)."""

    def __init__(self):
        self._seen_urls: set[str] = set()

    def filter(self, bounties: list[dict]) -> list[dict]:
        """Return only bounties whose github_url hasn't been seen before."""
        result = []
        for b in bounties:
            url = (b.get("github_url") or "").strip()
            if url and url in self._seen_urls:
                continue
            if url:
                self._seen_urls.add(url)
            result.append(b)
        self._seen_urls.clear()
        return result


def is_valid_bounty(raw: dict) -> bool:
    """Check bounty passes MIN_BOUNTY_USD threshold and has a GitHub URL."""
    try:
        val = float(raw.get("value_in_usdt") or 0)
    except (ValueError, TypeError):
        val = 0.0
    if val < MIN_BOUNTY_USD:
        return False
    gh = (raw.get("github_url") or "").strip()
    if not gh:
        return False
    return True


# ══════════════════════════════════════════════════════════════
# SOURCE A: Bountycaster
# ══════════════════════════════════════════════════════════════

class BountycasterClient:
    """Low-level Bountycaster API client."""

    def __init__(self, base_url: str = BOUNTYCASTER_API):
        self.base_url = base_url
        self._session = requests.Session()
        self._cache: dict[str, dict] = {}
        self._cache_ts: dict[str, float] = {}

    def fetch_and_convert(self) -> list[dict]:
        """Fetch open bounties, return normalized list."""
        hashes = self._list_open_hashes()
        if not hashes:
            return []
        results = []
        for h in hashes:
            detail = self._get_bounty(h)
            if detail:
                converted = self._convert(detail)
                if converted:
                    results.append(converted)
        return results

    def _list_open_hashes(self) -> list[str]:
        try:
            resp = self._session.get(
                f"{self.base_url}/api/v1/bounties/open",
                timeout=15, headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            hashes = []
            for item in data.get("bounties", []):
                if isinstance(item, dict):
                    h = (item.get("platform") or {}).get("farcaster", {}).get("hash", "")
                    if h:
                        hashes.append(h)
            return hashes
        except requests.RequestException as e:
            print(f"[Bountycaster] List error: {e}", flush=True)
            return []

    def _get_bounty(self, hash_id: str) -> Optional[dict]:
        now = time.time()
        if hash_id in self._cache and now - self._cache_ts.get(hash_id, 0) < CACHE_TTL:
            return self._cache[hash_id]
        try:
            resp = self._session.get(
                f"{self.base_url}/api/v1/bounty/{hash_id}",
                timeout=15, headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._cache[hash_id] = data
            self._cache_ts[hash_id] = now
            return data
        except requests.RequestException as e:
            print(f"[Bountycaster] Detail error {hash_id}: {e}", flush=True)
            return None

    def _convert(self, raw: dict) -> Optional[dict]:
        if not raw or not raw.get("title"):
            return None
        platform = raw.get("platform") or {}
        hash_id = (platform.get("farcaster") or {}).get("hash", "")
        if not hash_id:
            return None
        summary = raw.get("summary_text", "")
        reward = raw.get("reward_summary") or {}
        usd_value = reward.get("usd_value", "0")
        unit_amount = str(reward.get("unit_amount", "0")).replace(",", "")
        symbol = reward.get("symbol", "USD")
        github_url = _extract_github(summary, raw.get("feed", []))
        return {
            "id": f"bc:{hash_id[:12]}",
            "title": raw.get("title", "Untitled"),
            "description": summary or raw.get("title", ""),
            "github_url": github_url,
            "url": github_url or f"{self.base_url}/bounty/{hash_id}",
            "repo_url": github_url,
            "status": "OPEN",
            "value_in_usdt": usd_value if usd_value and float(usd_value) > 0 else unit_amount,
            "source": "bountycaster",
            "bounty_hash": hash_id,
            "metadata": {"reward": reward, "tags": raw.get("tag_slugs", []), "symbol": symbol},
        }

    @staticmethod
    def mock_bounties() -> list[dict]:
        return [b for b in HISTORICAL_BOUNTIES if b["source"] == "bountycaster"]


# ══════════════════════════════════════════════════════════════
# SOURCE B: GitHub Bounties (issues with dollar amounts)
# ══════════════════════════════════════════════════════════════

class GitHubBountyClient:
    """Fetch open GitHub issues with explicit bounty/reward amounts in their title.

    Uses GitHub's public Issues Search API. Without GITHUB_TOKEN, limited to
    60 requests/hour. With a token, 5000 requests/hour.
    """

    # Search for open issues with dollar amounts + bounty keywords in title
    SEARCH_QUERY = '(bounty OR reward OR "$" OR USDC OR USDT) is:issue is:open'

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AIMS-BountyAdapter/2.0",
        })
        if GITHUB_TOKEN:
            self._session.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    def fetch(self) -> list[dict]:
        """Search GitHub for open issues with bounty amounts, return normalized list."""
        all_issues: list[dict] = []
        page = 1

        try:
            while page <= 3:  # max 3 pages = 90 issues
                resp = self._session.get(
                    GITHUB_SEARCH_URL,
                    params={"q": self.SEARCH_QUERY, "per_page": 30, "page": page},
                    timeout=15,
                )
                if resp.status_code == 403:
                    print(f"[GitHubBounty] Rate limited — using partial results ({len(all_issues)} issues)", flush=True)
                    break
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                if not items:
                    break
                for item in items:
                    converted = self._convert(item)
                    if converted:
                        all_issues.append(converted)
                page += 1
        except requests.RequestException as e:
            print(f"[GitHubBounty] Search error: {e}", flush=True)

        return all_issues

    def _convert(self, issue: dict) -> Optional[dict]:
        """Convert a GitHub issue to the unified bounty format.

        Extracts bounty amount from title via regex.
        """
        title = issue.get("title", "") or ""
        body = issue.get("body", "") or ""
        html_url = issue.get("html_url", "")
        repo_full = (issue.get("repository_url") or "").replace("https://api.github.com/repos/", "")

        if not html_url:
            return None

        # Extract dollar amount from title (most reliable signal)
        value_usdt = self._extract_amount(title) or self._extract_amount(body) or "0"

        # Determine repo URL from full name
        repo_url = f"https://github.com/{repo_full}" if repo_full else ""

        # Tags from GitHub labels
        labels = [lb.get("name", "") for lb in (issue.get("labels") or [])]

        # Stable ID from repo + number
        issue_number = issue.get("number", "")
        issue_id = f"gh:{repo_full.replace('/', '-')}:{issue_number}" if repo_full and issue_number else f"gh:{uuid.uuid4().hex[:12]}"

        return {
            "id": issue_id,
            "title": title[:200],
            "description": (title + "\n\n" + (body or ""))[:2000],
            "github_url": html_url,
            "url": html_url,
            "repo_url": repo_url,
            "status": "OPEN",
            "value_in_usdt": value_usdt,
            "source": "github_bounty",
            "metadata": {
                "labels": labels,
                "created_at": issue.get("created_at", ""),
                "repo": repo_full,
                "score": issue.get("score", 0),
            },
        }

    @staticmethod
    def _extract_amount(text: str) -> Optional[str]:
        """Find dollar/reward amount in text using regex.

        Matches patterns like: $500, $500 USDC, 500 USDC, 5000 degen, $75 reward
        """
        if not text:
            return None
        # Try: $500 USDC/USDT/USD, $500 reward/bounty
        patterns = [
            r'\$(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:USDC|USDT|USD)?',
            r'(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:USDC|USDT|USD)\s+(?:bounty|reward)',
            r'(?:bounty|reward)[:\s]+\$?(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).replace(",", "")
                try:
                    fval = float(val)
                    if 5 <= fval <= 100_000:  # sanity range
                        return val
                except ValueError:
                    continue
        return None

    @staticmethod
    def mock_bounties() -> list[dict]:
        return [b for b in HISTORICAL_BOUNTIES if b["source"] == "github_bounty"]


# ══════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════

def _extract_github(summary: str, feed: list) -> str:
    """Find first GitHub URL in text."""
    pattern = r"https?://github\.com/[^\s\r\n,;)\'\"\]>]+"
    for text in [summary] + [f.get("text", "") for f in (feed or [])]:
        m = re.search(pattern, text)
        if m:
            return m.group(0).rstrip("/")
    return ""


# ══════════════════════════════════════════════════════════════
# AGGREGATOR — orchestrates all sources
# ══════════════════════════════════════════════════════════════

class MultiSourceAggregator:
    """Fetch from all sources, deduplicate, filter, merge."""

    def __init__(self):
        self.bountycaster = BountycasterClient()
        self.github = GitHubBountyClient()
        self.dedup = DedupEngine()

    def fetch_all(self) -> list[dict]:
        """Fetch from all live sources, deduplicate, apply MIN_BOUNTY_USD, return merged list."""
        all_bounties: list[dict] = []

        # Source A: Bountycaster
        try:
            bc = self.bountycaster.fetch_and_convert()
            print(f"[Aggregator] Bountycaster: {len(bc)} bounties", flush=True)
            all_bounties.extend(bc)
        except Exception as e:
            print(f"[Aggregator] Bountycaster failed: {e}", flush=True)

        # Source B: GitHub Bounties
        try:
            gh = self.github.fetch()
            print(f"[Aggregator] GitHubBounty: {len(gh)} issues", flush=True)
            all_bounties.extend(gh)
        except Exception as e:
            print(f"[Aggregator] GitHubBounty failed: {e}", flush=True)

        # Deduplicate by URL
        deduped = self.dedup.filter(all_bounties)
        if len(deduped) < len(all_bounties):
            print(f"[Aggregator] Dedup removed {len(all_bounties) - len(deduped)} duplicates", flush=True)

        # Filter by MIN_BOUNTY_USD
        filtered = [b for b in deduped if is_valid_bounty(b)]
        if len(filtered) < len(deduped):
            print(f"[Aggregator] MIN_BOUNTY_USD={MIN_BOUNTY_USD} filtered out {len(deduped) - len(filtered)} low-value", flush=True)

        print(f"[Aggregator] Returning {len(filtered)} bounties total", flush=True)
        return filtered

    def fetch_mock(self) -> list[dict]:
        """Get mock data from all sources, deduplicated and filtered."""
        raw = BountycasterClient.mock_bounties() + GitHubBountyClient.mock_bounties()
        deduped = self.dedup.filter(raw)
        return [b for b in deduped if is_valid_bounty(b)]


# ── HTTP Server ──

class AdapterHandler(BaseHTTPRequestHandler):
    """Serves aggregated multi-source bounty JSON."""

    def _respond(self, data: list[dict], status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/health":
            self._respond([{"status": "ok"}])
            return

        if path == "/mock":
            self._respond(self.server.aggregator.fetch_mock())
            return

        if path == "/sources":
            mock_bc = BountycasterClient.mock_bounties()
            mock_gh = GitHubBountyClient.mock_bounties()
            self._respond([
                {"source": "bountycaster", "type": "live-api", "url": BOUNTYCASTER_API, "mock_count": len(mock_bc)},
                {"source": "github_bounty", "type": "github-search", "url": GITHUB_SEARCH_URL, "mock_count": len(mock_gh)},
                {"min_bounty_usd": MIN_BOUNTY_USD},
            ])
            return

        # Mock mode?
        if getattr(self.server, "mock_mode", False):
            self._respond(self.server.aggregator.fetch_mock())
            return

        # Live aggregated fetch
        try:
            results = self.server.aggregator.fetch_all()
            self._respond(results)
        except Exception as e:
            self._respond(
                [{"error": str(e), "message": "Falling back to mock data"}],
                status=503,
            )

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[Adapter] {args[0]} {args[1]} {args[2]}\n")


def run_server(mock_mode: bool = False):
    """Start the multi-source aggregation gateway."""
    server = HTTPServer(("0.0.0.0", ADAPTER_PORT), AdapterHandler)
    server.aggregator = MultiSourceAggregator()
    server.mock_mode = mock_mode
    mode = "MOCK" if mock_mode else "LIVE"
    print(f"[Adapter] Multi-source gateway ({mode}) on :{ADAPTER_PORT}", flush=True)
    print(f"[Adapter] Sources: Bountycaster + GitHub Bounties", flush=True)
    print(f"[Adapter] MIN_BOUNTY_USD={MIN_BOUNTY_USD} | GITHUB_TOKEN={'set' if GITHUB_TOKEN else 'unset (60 req/hr)'}", flush=True)
    print(f"[Adapter] Point GITCOIN_API=http://localhost:{ADAPTER_PORT} at the sniper", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Adapter] Shutting down.", flush=True)
        server.server_close()


# ── CLI ──

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Multi-Source Bounty Gateway — aggregates Bountycaster + GitHub bounties"
    )
    parser.add_argument("--once", action="store_true", help="Fetch once, print merged JSON, exit")
    parser.add_argument("--mock", action="store_true", help="Serve mock data instead of live")
    parser.add_argument("--sources", action="store_true", help="Print source info and exit")
    args = parser.parse_args()

    if args.sources:
        bc = BountycasterClient.mock_bounties()
        gh = GitHubBountyClient.mock_bounties()
        print(json.dumps([
            {"source": "bountycaster", "type": "live-api", "url": BOUNTYCASTER_API, "mock_count": len(bc)},
            {"source": "github_bounty", "type": "github-search", "url": GITHUB_SEARCH_URL, "mock_count": len(gh)},
            {"min_bounty_usd": MIN_BOUNTY_USD},
        ], indent=2))
        return

    aggregator = MultiSourceAggregator()

    if args.once:
        try:
            data = aggregator.fetch_all()
            if not data:
                print("[Adapter] Live returned empty — falling back to mock", flush=True)
                data = aggregator.fetch_mock()
        except Exception as e:
            print(f"[Adapter] Live fetch failed: {e}", file=sys.stderr)
            data = aggregator.fetch_mock()

        print(json.dumps(data, indent=2))
        return

    run_server(mock_mode=args.mock)


if __name__ == "__main__":
    main()
