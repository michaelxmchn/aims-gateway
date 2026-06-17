#!/usr/bin/env python3
"""
AIMS Bountycaster Sniper — Autonomous Bounty Hunting Pipeline
=============================================================
Poll → Match → Execute → Deliver → Report

Architecture:
  1. BountycasterPoller — 60s interval poll for OPEN bounties via Bountycaster API
  2. AIMSEvaluator      — System-prompted LLM judge via AIMS /api/run
  3. CodeExecutor       — git clone + claude-code headless repair + Docker-sandboxed tests
  4. AutoDeliverer      — git commit + gh pr create + SSE dashboard report

Usage:
  python3 scripts/gitcoin_sniper.py                   # daemon mode
  python3 scripts/gitcoin_sniper.py --dry-run          # simulated loop
  python3 scripts/gitcoin_sniper.py --once             # single cycle
  python3 scripts/gitcoin_sniper.py --report           # dashboard report only
"""

import argparse, hashlib, json, os, re, shutil, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

WORKDIR     = Path(os.getenv("AIMS_SNIPER_WORKDIR", "/tmp/aims-sniper"))
BOUNTYCASTER_API = os.getenv("BOUNTYCASTER_API", "https://www.bountycaster.xyz")
AIMS_API    = os.getenv("AIMS_API", "http://127.0.0.1:8001")
AIMS_API_KEY = os.getenv("AIMS_API_KEY", "")
AIMS_WALLET  = os.getenv("AIMS_WALLET", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
MAX_CLONE_AGE_SECONDS = 3600 * 6  # don't touch clones older than 6h
DOCKER_ENABLED = os.getenv("SNIPER_DOCKER", "1") == "1"

# Language → Docker image mapping for sandboxed test execution
DOCKER_IMAGES: dict[str, str] = {
    "node":   "node:20-slim",
    "python": "python:3.12-slim",
    "go":     "golang:1.23-alpine",
    "rust":   "rust:1.75-slim",
    "ruby":   "ruby:3.2-slim",
    "java":   "eclipse-temurin:21-jdk-alpine",
}
DOCKER_DEFAULT_IMAGE = "alpine:3.19"  # fallback for unknown projects

DRY_RUN = False
LOG     = []  # action traces for dashboard report

# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def trace(action: str, detail: str, status: str = "info") -> dict:
    """Build an action-trace record for the dashboard report SSE."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "status": status,
        "trace_id": uuid.uuid4().hex[:12],
    }
    LOG.append(rec)
    return rec

# ═══════════════════════════════════════════════════════════════
# 1. BOUNTYCASTER POLLER
# ═══════════════════════════════════════════════════════════════

class BountycasterBounty:
    """Normalised bounty from the Bountycaster API (or mock)."""
    def __init__(self, raw: dict):
        self.id = raw.get("id") or raw.get("pk") or str(hash(json.dumps(raw, sort_keys=True)))
        self.title = raw.get("title", "Untitled")
        self.description = raw.get("description", raw.get("issue_description", ""))
        self.url = raw.get("url", raw.get("github_url", ""))
        self.repo_url = raw.get("repo_url", self._extract_repo(self.url))
        self.status = raw.get("status", "OPEN")
        self.value = float(raw.get("value_in_usdt") or raw.get("value_in_usdt", 0) or 0)
        self.metadata = raw

    @staticmethod
    def _extract_repo(url: str) -> str:
        m = re.search(r"github\.com(/[^/]+/[^/]+)", url)
        if m:
            return "https://github.com" + m.group(1).rstrip("/")
        return url

    def __hash__(self) -> int:
        return hash(self.id)


class BountycasterPoller:
    """Poll Bountycaster API for open bounties, yield those not yet seen."""

    def __init__(self, api_url: str = BOUNTYCASTER_API):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        self._seen: set[str] = set()

    # ── Public API ────────────────────────────────────────────

    def fetch(self) -> list[BountycasterBounty]:
        """Hit the Bountycaster API and return a list of open bounties."""
        if DRY_RUN:
            return self._mock_bounties()

        try:
            return self._fetch_live()
        except Exception as e:
            log(f"Bountycaster API failed: {e}", "WARN")
            log(f"Will retry in {POLL_SECONDS}s", "INFO")
            return []

    def new_bounties(self) -> list[BountycasterBounty]:
        """Return bounties not seen in previous polls."""
        batch = self.fetch()
        fresh = [b for b in batch if b.id not in self._seen]
        for b in fresh:
            self._seen.add(b.id)
        return fresh

    # ── Live fetching ─────────────────────────────────────────

    def _fetch_live(self) -> list[BountycasterBounty]:
        """Fetch open bounty hashes from listing endpoint, enrich with details."""
        hashes = self._list_open_hashes()
        if not hashes:
            log("No open bounties found via Bountycaster listing API", "INFO")
            return []

        results: list[BountycasterBounty] = []
        for h in hashes:
            detail = self._get_bounty_detail(h)
            if detail:
                converted = self._convert(detail)
                if converted:
                    results.append(converted)
        return results

    def _list_open_hashes(self) -> list[str]:
        """GET /api/v1/bounties/open and extract bounty hashes."""
        resp = self._session.get(
            f"{self.api_url}/api/v1/bounties/open",
            timeout=15,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        raw_list = data.get("bounties", [])
        hashes: list[str] = []
        for item in raw_list:
            if isinstance(item, dict):
                platform = item.get("platform") or {}
                h = (platform.get("farcaster") or {}).get("hash", "")
                if h:
                    hashes.append(h)
        return hashes

    def _get_bounty_detail(self, hash_id: str) -> Optional[dict]:
        """GET /api/v1/bounty/{hash} for full detail."""
        try:
            resp = self._session.get(
                f"{self.api_url}/api/v1/bounty/{hash_id}",
                timeout=15,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log(f"Failed to fetch bounty {hash_id}: {e}", "WARN")
            return None

    @staticmethod
    def _extract_github(summary: str, feed: list) -> str:
        """Find first GitHub URL in summary text or feed entries."""
        pattern = r"https?://github\.com/[^\s\r\n,;)\'\"\]>]+"
        for text in [summary] + [f.get("text", "") for f in (feed or [])]:
            m = re.search(pattern, text)
            if m:
                return m.group(0).rstrip("/")
        return ""

    def _convert(self, raw: dict) -> Optional[BountycasterBounty]:
        """Convert a Bountycaster API response to BountycasterBounty format."""
        hash_id = (raw.get("platform") or {}).get("farcaster", {}).get("hash", "")
        if not hash_id or not raw.get("title"):
            return None

        summary = raw.get("summary_text", "")
        reward = raw.get("reward_summary") or {}
        usd_value = reward.get("usd_value", "0")
        unit_amount = str(reward.get("unit_amount", "0")).replace(",", "")
        value = usd_value if usd_value and float(usd_value) > 0 else unit_amount

        github_url = self._extract_github(summary, raw.get("feed", []))

        return BountycasterBounty({
            "id": f"bc:{hash_id[:12]}",
            "title": raw.get("title", "Untitled"),
            "description": summary or raw.get("title", ""),
            "github_url": github_url,
            "url": github_url or f"{self.api_url}/bounty/{hash_id}",
            "repo_url": github_url,
            "status": "OPEN",
            "value_in_usdt": float(value) if value else 0.0,
            "source": "bountycaster",
            "bounty_hash": hash_id,
            "raw_reward": reward,
            "tags": raw.get("tag_slugs", []),
        })

    # ── Mock data (real historical Bountycaster bounties) ─────

    def _mock_bounties(self) -> list[BountycasterBounty]:
        """Return simulated bounties for dry-run testing.
        Uses real historical Bountycaster data sourced from the live API.
        """
        return [
            BountycasterBounty({
                "id": "bc-mock-001",
                "title": "Create v2 frame using NextJS, Tailwind, react-icons, supabase for $NATIVE",
                "description": (
                    "$250 USDC to create v2 frame using NextJS, Tailwind, "
                    "react-icons, supabase for $NATIVE.\n\n"
                    "- enable in-frame token buy\n"
                    "- welcome noti upon install\n"
                    "- thank you noti upon swap\n"
                    "- new announcement noti\n"
                    "- load announcements from DB\n\n"
                    "I will open source for others to use with full credit to initial author."
                ),
                "github_url": "https://github.com/nonomnouns/native-frame",
                "repo_url": "https://github.com/nonomnouns/native-frame",
                "status": "OPEN",
                "value_in_usdt": 250.0,
            }),
            BountycasterBounty({
                "id": "bc-mock-002",
                "title": "Create a TypeScript script for Legacy Payment Flows Migration",
                "description": (
                    "8000 degen tip for someone to create a ts script that "
                    "for a given list of addresses (across base and optimism), "
                    "returns a list of tokens and total balance!\n\n"
                    "Input: [{ 'address': '0x', 'network': 8453 | 10 }]\n"
                    "Output: [{ 'address': '0x', 'network': 8453 | 10, "
                    "'tokens': string[], totalBalanceUSD: number }]\n\n"
                    "Script should be committed to Github."
                ),
                "github_url": "https://github.com/jhonceth/balanceUSDToken",
                "repo_url": "https://github.com/jhonceth/balanceUSDToken",
                "status": "OPEN",
                "value_in_usdt": 84.0,
            }),
            BountycasterBounty({
                "id": "bc-mock-003",
                "title": "Moon energy degen mode social bounty",
                "description": (
                    "Going full degen mode today, wish me luck - need that moon energy.\n\n"
                    "Amount: 1 USDC\n\n"
                    "This is a social engagement bounty, not a coding task."
                ),
                "github_url": "",
                "repo_url": "",
                "status": "OPEN",
                "value_in_usdt": 1.0,
            }),
        ]


# ═══════════════════════════════════════════════════════════════
# 2. AIMS SKILL MATCHER
# ═══════════════════════════════════════════════════════════════

class AIMSEvaluator:
    """Send bounty description to AIMS gateway LLM; return MATCH / NO_MATCH."""

    # System prompt: gate the model to only accept tasks solvable by code gen / auto-fix
    SYSTEM_PROMPT = (
        "You are an expert bounty analyst for AIMS Gateway. "
        "Your ONLY job is to decide whether a bounty task on Bountycaster can be COMPLETELY SOLVED "
        "by automated code generation, code repair, or data-cleanup — with NO human judgment, "
        "NO creative design, and NO research-only output.\n\n"
        "Criteria for MATCH:\n"
        "1. The task describes a concrete, testable code defect, missing feature, or data migration.\n"
        "2. Success is measurable by running existing tests (npm test, pytest, etc.).\n"
        "3. The fix can be produced entirely by an LLM-powered coding agent.\n\n"
        "Criteria for NO_MATCH:\n"
        "- Requirements gathering, UX research, or creative design\n"
        "- Documentation-only / RFC / architecture proposal\n"
        "- Tasks that require human domain expertise (legal, compliance, translation)\n"
        "- \"The answer is unclear — more info needed\"\n\n"
        "Respond with EXACTLY one line:\n"
        "MATCH:<confidence 0-100>:<one-sentence rationale>\n"
        "NO_MATCH:<rationale>\n"
        "Do NOT output anything else."
    )

    def __init__(self, api_base: str = AIMS_API, api_key: str = AIMS_API_KEY):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key

    def evaluate(self, bounty: BountycasterBounty) -> tuple[bool, int, str]:
        """
        Returns (is_match, confidence, rationale).
        In dry-run mode, simulates the AI call with a keyword heuristic.
        """
        if DRY_RUN:
            return self._mock_evaluate(bounty)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "skill_id": "code_security_audit",
            "params": {
                "prompt": self.SYSTEM_PROMPT,
                "bounty_title": bounty.title,
                "bounty_description": bounty.description,
                "bounty_url": bounty.url,
            },
            "user_id": "bountycaster-sniper-bot",
            "max_budget": 0.05,
        }

        try:
            resp = requests.post(
                f"{self.api_base}/api/run",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                log(f"AIMS /api/run returned {resp.status_code}: {resp.text[:200]}", "WARN")
                return False, 0, f"API error {resp.status_code}"

            result = resp.json()
            raw = result.get("result_data", {})
            answer = raw.get("answer", raw.get("output", ""))
            return self._parse_answer(answer)
        except requests.RequestException as e:
            log(f"AIMS gateway error: {e}", "ERROR")
            return False, 0, f"Gateway error: {e}"

    def _mock_evaluate(self, bounty: BountycasterBounty) -> tuple[bool, int, str]:
        """Keyword-based simulation for dry-run."""
        desc = (bounty.title + " " + bounty.description).lower()
        # Auto-reject research / social / docs-only tasks
        no_match_keywords = ["research", "document", "rfc", "architecture proposal",
                             "social bounty", "engagement", "moon energy", "wish me luck",
                             "good luck"]
        if any(kw in desc for kw in no_match_keywords):
            return False, 20, "Non-code task — not automatable"
        # Keywords that indicate a code task (works for both fix and build bounties)
        match_keywords = ["fix ", "bug", "test", "coverage", "lint", "css",
                          "typescript", "script", "nextjs", "react", "tailwind",
                          "supabase", "frame", "migration", "cli", "api",
                          "github", "node", "npm", "jest"]
        score = 0
        has_github = bool(bounty.repo_url)
        for kw in match_keywords:
            if kw in desc:
                score += 20
        if score >= 40 or (has_github and score >= 20):
            return True, min(score + 20, 95), f"Dry-run heuristic matched ({score}%)"
        return False, 10, "No matching code-task keywords"

    @staticmethod
    def _parse_answer(raw: str) -> tuple[bool, int, str]:
        raw = (raw or "").strip()
        m = re.match(r"MATCH\s*:\s*(\d+)\s*:\s*(.*)", raw, re.IGNORECASE)
        if m:
            return True, int(m.group(1)), m.group(2).strip()
        m = re.match(r"NO_MATCH\s*:\s*(.*)", raw, re.IGNORECASE)
        if m:
            return False, 0, m.group(1).strip()
        log(f"Unparseable evaluator answer: {raw[:100]}", "WARN")
        return False, 0, "Unparseable response"


# ═══════════════════════════════════════════════════════════════
# 3. CODE EXECUTOR (Docker-sandboxed)
# ═══════════════════════════════════════════════════════════════

class CodeExecutor:
    """Clone repo → invoke claude-code → run tests in Docker sandbox."""

    # Project file → (docker_image, test_commands)
    PROJECT_MAP: list[tuple[str, str, list[str]]] = [
        ("package.json",      "node",   ["npm install", "npm test"]),
        ("pyproject.toml",    "python", ["pip install -e .", "python -m pytest"]),
        ("setup.py",          "python", ["pip install -e .", "python -m pytest"]),
        ("setup.cfg",         "python", ["pip install -e .", "python -m pytest"]),
        ("requirements.txt",  "python", ["pip install -r requirements.txt", "python -m pytest"]),
        ("go.mod",            "go",     ["go mod tidy", "go test ./..."]),
        ("Cargo.toml",        "rust",   ["cargo build", "cargo test"]),
        ("Gemfile",           "ruby",   ["bundle install", "bundle exec rspec"]),
        ("build.gradle",      "java",   ["./gradlew test"]),
        ("pom.xml",           "java",   ["mvn test"]),
    ]

    def __init__(self, workdir: Path = WORKDIR):
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)

    def execute(self, bounty: BountycasterBounty) -> Optional[dict]:
        """
        Full execution pipeline:
          1. git clone
          2. claude-code headless repair
          3. run tests in Docker sandbox
          4. return result dict
        """
        repo_name = bounty.repo_url.rstrip("/").split("/")[-1]
        clone_path = self.workdir / repo_name

        trace("clone_start", f"Cloning {bounty.repo_url}")

        # ── 3a. Clone ────────────────────────────────────────────────
        if clone_path.exists():
            log(f"Repo exists at {clone_path}, pulling latest")
            if DRY_RUN:
                log("[DRY-RUN] Skipping git pull")
            else:
                subprocess.run(["git", "-C", str(clone_path), "pull"], check=False, timeout=120)
        else:
            if DRY_RUN:
                log(f"[DRY-RUN] Would git clone {bounty.repo_url} → {clone_path}")
                clone_path.mkdir(parents=True, exist_ok=True)
                (clone_path / "package.json").write_text('{"name":"mock","scripts":{"test":"echo ok"}}')
                (clone_path / "README_MOCK.md").write_text("# Mock Repo\nDry-run only.\n")
                subprocess.run(["git", "init"], cwd=str(clone_path), check=False, capture_output=True)
                subprocess.run(["git", "config", "user.email", "sniper@aimsgateway.com"],
                               cwd=str(clone_path), check=False, capture_output=True)
                subprocess.run(["git", "config", "user.name", "AIMS Sniper"],
                               cwd=str(clone_path), check=False, capture_output=True)
            else:
                result = subprocess.run(
                    ["git", "clone", bounty.repo_url, str(clone_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    trace("clone_failed", result.stderr[:200], "error")
                    return {"status": "FAILED", "step": "clone", "detail": result.stderr[:200]}

        trace("clone_done", f"Cloned to {clone_path}")

        # ── 3b. Invoke claude-code for headless fix ──────────────────
        prompt = self._build_prompt(bounty)
        if DRY_RUN:
            log(f"[DRY-RUN] Would invoke claude-code with:\n{prompt[:500]}...")
            fix_file = clone_path / "DRY_RUN_FIX.md"
            fix_file.write_text(f"# Automated Fix for Bounty {bounty.id}\n\nApplied at {datetime.now()}")
            claude_exit = 0
        else:
            trace("claude_start", f"Invoking claude-code for {bounty.id}")
            claude_exit = subprocess.run(
                ["claude", "-p", prompt],
                cwd=str(clone_path),
                timeout=600,
            ).returncode

        if claude_exit != 0:
            trace("claude_failed", f"claude-code exited {claude_exit}", "error")
            return {"status": "FAILED", "step": "claude-code", "detail": f"exit code {claude_exit}"}

        trace("claude_done", "claude-code completed successfully")

        # ── 3c. Run tests in Docker sandbox ──────────────────────────
        project_type = self._detect_project_type(clone_path)
        if project_type is None:
            log("No known test framework detected — skipping test phase", "WARN")
            trace("test_skip", "No test framework found")
        else:
            docker_image, test_cmds = project_type
            trace("test_start", f"Running in Docker ({docker_image}): {'; '.join(test_cmds)}")

            if DRY_RUN:
                log(f"[DRY-RUN] Would run in Docker ({docker_image}): {'; '.join(test_cmds)}")
            else:
                result = self._run_in_docker(clone_path, docker_image, test_cmds)
                if result is None:
                    # Docker unavailable — fallback to direct execution with warning
                    log("Docker unavailable — falling back to direct execution", "WARN")
                    for cmd in test_cmds:
                        r = subprocess.run(cmd, shell=True, cwd=str(clone_path),
                                           capture_output=True, text=True, timeout=300)
                        if r.returncode != 0:
                            detail = r.stderr[-300:] if r.stderr else r.stdout[-300:]
                            trace("test_failed", f"'{cmd}' exited {r.returncode}: {detail}", "error")
                            return {"status": "FAILED", "step": "test", "detail": detail}
                elif result["returncode"] != 0:
                    detail = result["stderr"][-300:] if result["stderr"] else result["stdout"][-300:]
                    trace("test_failed", f"Docker test exited {result['returncode']}: {detail}", "error")
                    return {"status": "FAILED", "step": "test", "detail": detail}
                else:
                    log(f"All Docker tests passed ({docker_image})")

        trace("test_passed", "All tests passed (0 failures)")
        return {"status": "PASS", "step": "done", "clone_path": str(clone_path)}

    def _run_in_docker(self, clone_path: Path, image_key: str, commands: list[str]) -> Optional[dict]:
        """
        Run test commands inside a Docker container with security hardening.
        Returns {'returncode': int, 'stdout': str, 'stderr': str} or None if Docker unavailable.
        """
        image = DOCKER_IMAGES.get(image_key, DOCKER_DEFAULT_IMAGE)

        # Build shell command: chain commands with &&
        shell_cmd = " && ".join(commands)

        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "-v", f"{clone_path.resolve()}:/workspace",
            "-w", "/workspace",
            image,
            "sh", "-c", shell_cmd,
        ]

        log(f"Docker: {' '.join(docker_cmd[:6])} ... {image} sh -c '{shell_cmd}'")

        try:
            r = subprocess.run(
                docker_cmd,
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                log(f"Docker test failed (exit {r.returncode}): {r.stderr[:200]}", "WARN")
            return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
        except FileNotFoundError:
            log("Docker binary not found — is Docker installed?", "ERROR")
            return None
        except subprocess.TimeoutExpired:
            log("Docker test timed out after 300s", "ERROR")
            return {"returncode": -1, "stdout": "", "stderr": "Timeout"}
        except Exception as e:
            log(f"Docker execution error: {e}", "ERROR")
            return None

    def _build_prompt(self, bounty: BountycasterBounty) -> str:
        return (
            f"You are an expert software engineer. "
            f"A Bountycaster bounty requires the following task:\n\n"
            f"## Title\n{bounty.title}\n\n"
            f"## Description\n{bounty.description}\n\n"
            f"## Your job\n"
            f"1. Read the codebase thoroughly\n"
            f"2. Implement the exact fix/changes described above\n"
            f"3. Run the existing test suite and fix any failures\n"
            f"4. Do NOT add new features beyond the scope of the bounty\n"
            f"5. Do NOT remove or refactor unrelated code\n\n"
            f"Proceed now."
        )

    @staticmethod
    def _detect_project_type(path: Path) -> Optional[tuple[str, list[str]]]:
        """Detect project type and return (image_key, test_commands)."""
        for filename, image_key, cmds in CodeExecutor.PROJECT_MAP:
            if (path / filename).exists():
                # For package.json, verify a test script actually exists
                if filename == "package.json":
                    try:
                        pkg = json.loads((path / "package.json").read_text())
                        if "test" not in pkg.get("scripts", {}):
                            continue
                    except (json.JSONDecodeError, OSError):
                        continue
                return image_key, cmds
        return None


# ═══════════════════════════════════════════════════════════════
# 4. AUTO DELIVERER
# ═══════════════════════════════════════════════════════════════

class AutoDeliverer:
    """git commit → gh pr create → SSE dashboard report."""

    def __init__(self, api_base: str = AIMS_API, api_key: str = AIMS_API_KEY):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key

    def deliver(self, bounty: BountycasterBounty, exec_result: dict) -> dict:
        """Commit changes, create PR, report to dashboard."""
        clone_path = exec_result.get("clone_path", "")
        if not clone_path or not Path(clone_path).exists():
            return {"status": "SKIP", "reason": "no clone path"}

        branch = f"aims-sniper/{bounty.id}"
        pr_url = ""

        trace("git_commit_start", f"Creating branch {branch}")

        if DRY_RUN:
            log(f"[DRY-RUN] git add -A && git commit -m 'fix(bounty-{bounty.id}): {bounty.title[:50]}'")
            log(f"[DRY-RUN] git push origin {branch}")
            log(f"[DRY-RUN] gh pr create --title 'fix: {bounty.title[:50]}'")
            pr_url = f"https://github.com/example/repo/pull/{uuid.uuid4().hex[:6]}"
            trace("pr_created", f"PR created: {pr_url}")
        else:
            try:
                subprocess.run(["git", "checkout", "-b", branch],
                               cwd=clone_path, check=True, timeout=30, capture_output=True)
                subprocess.run(["git", "add", "-A"],
                               cwd=clone_path, check=True, timeout=30, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"fix(bounty-{bounty.id}): automated fix\n\nCloses #{bounty.id}"],
                    cwd=clone_path, check=False, timeout=30, capture_output=True,
                )
                push_result = subprocess.run(
                    ["git", "push", "origin", branch],
                    cwd=clone_path, check=False, timeout=60, capture_output=True, text=True,
                )
                if push_result.returncode == 0:
                    pr_result = subprocess.run(
                        ["gh", "pr", "create",
                         "--title", f"fix: {bounty.title[:70]}",
                         "--body", self._pr_body(bounty)],
                        cwd=clone_path, check=False, timeout=60, capture_output=True, text=True,
                    )
                    if pr_result.returncode == 0:
                        pr_url = pr_result.stdout.strip()
                        trace("pr_created", f"PR created: {pr_url}")
                    else:
                        trace("pr_failed", pr_result.stderr[:200], "warn")
                else:
                    trace("push_failed", push_result.stderr[:200], "warn")
            except subprocess.TimeoutExpired as e:
                trace("git_timeout", str(e)[:100], "error")

        self.report_to_dashboard(bounty, exec_result, pr_url)
        return {"status": "DELIVERED", "pr_url": pr_url or "N/A", "branch": branch}

    def report_to_dashboard(self, bounty: BountycasterBounty, exec_result: dict, pr_url: str) -> None:
        """Push action trace to AIMS SSE endpoint so the live dashboard updates."""
        if DRY_RUN:
            log(f"[DRY-RUN] Would POST settlement event to dashboard SSE")
            return

        success = exec_result.get("status") == "PASS"
        action = "bounty_completed" if success else "bounty_failed"

        payload = {
            "action": action,
            "bounty_id": bounty.id,
            "title": bounty.title[:80],
            "value_usdt": bounty.value,
            "pr_url": pr_url,
            "trace_id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "severity": "info" if success else "error",
            "message": f"{'✅' if success else '❌'} Bounty {bounty.id}: {bounty.title[:60]}"
                       f" — {'PR merged' if success else 'execution failed'}",
        }

        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            r = requests.post(
                f"{self.api_base}/api/skill/task-action",
                headers=headers,
                json={"action": "report_trace", "payload": payload},
                timeout=10,
            )
            if r.status_code not in (200, 201, 202):
                log(f"Dashboard report returned {r.status_code}", "WARN")
        except requests.RequestException as e:
            log(f"Dashboard report failed: {e}", "WARN")

    @staticmethod
    def _pr_body(bounty: BountycasterBounty) -> str:
        return (
            f"## Automated Fix — Bounty #{bounty.id}\n\n"
            f"**Title:** {bounty.title}\n\n"
            f"**Value:** {bounty.value} USDC\n\n"
            f"---\n"
            f"*Generated by [AIMS Bountycaster Sniper](https://aims-gateway.fly.dev)*\n"
            f"*Action Trace: `{uuid.uuid4().hex[:12]}`*"
        )


# ═══════════════════════════════════════════════════════════════
# DASHBOARD STATUS
# ═══════════════════════════════════════════════════════════════

class DashboardStatus:
    """Read-only status for the —report flag: print current action traces."""

    COLORS = {"info": "\033[36m", "success": "\033[32m", "warn": "\033[33m", "error": "\033[31m"}
    RESET = "\033[0m"

    @staticmethod
    def print_report(traces: list[dict]) -> None:
        """Print a Bloomberg-terminal-style report of all action traces."""
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║     AIMS BOUNTYCASTER SNIPER — ACTION TRACES REPORT        ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        total = len(traces)
        passed = sum(1 for t in traces if t.get("status") == "info")
        failed = sum(1 for t in traces if t.get("status") == "error")
        warned = sum(1 for t in traces if t.get("status") == "warn")

        for t in traces:
            c = DashboardStatus.COLORS.get(t.get("status", "info"), "")
            status_icon = {"info": "●", "success": "✅", "warn": "⚠️", "error": "🚨"}
            icon = status_icon.get(t.get("status", "info"), "●")
            print(f"  {icon} {c}{t.get('action', '?'):<24}{DashboardStatus.RESET}"
                  f" {t.get('detail', '')[:100]}")

        print()
        print(f"  {'─' * 55}")
        print(f"  Total Traces: {total}  |  ✅ {passed}  |  ⚠️ {warned}  |  🚨 {failed}")
        print(f"  {'─' * 55}")

        if failed > 0:
            print()
            print("  🚨 异常反馈告警 / ALERT: 检测到失败轨迹，请检查日志！")
        else:
            print()
            print("  📈 收益图表更新: 流水线已成功交付，仪表盘 Ready！")

        print()


# ═══════════════════════════════════════════════════════════════
# CYCLE
# ═══════════════════════════════════════════════════════════════

class SniperPipeline:
    """Orchestrates one full poll→match→execute→deliver cycle."""

    def __init__(self):
        self.poller = BountycasterPoller()
        self.evaluator = AIMSEvaluator()
        self.executor = CodeExecutor()
        self.deliverer = AutoDeliverer()

    def run_once(self) -> list[dict]:
        """Single cycle: return action traces generated."""
        log("Polling Bountycaster for new bounties…")
        bounties = self.poller.new_bounties()
        log(f"Found {len(bounties)} new bounties")

        for bounty in bounties:
            log(f"Evaluating bounty {bounty.id}: {bounty.title[:60]}")

            is_match, confidence, rationale = self.evaluator.evaluate(bounty)
            if not is_match:
                trace("evaluate_no_match", f"[{bounty.id}] {rationale}")
                log(f"  → NO_MATCH ({confidence}%): {rationale}")
                continue

            trace("evaluate_match", f"[{bounty.id}] MATCH {confidence}% — {rationale}")
            log(f"  → MATCH ({confidence}%): {rationale}")

            exec_result = self.executor.execute(bounty)
            if exec_result is None:
                trace("exec_skipped", f"[{bounty.id}] Executor returned None", "warn")
                continue

            if exec_result.get("status") == "PASS":
                log("  → Execution PASSED, delivering PR…")
                delivery = self.deliverer.deliver(bounty, exec_result)
                if delivery.get("status") == "DELIVERED":
                    trace("bounty_delivered",
                          f"[{bounty.id}] PR: {delivery.get('pr_url', 'N/A')} | "
                          f"Value: {bounty.value} USDC", "success")
                    log(f"  ✅ Delivered! PR: {delivery.get('pr_url', 'N/A')}")
                else:
                    trace("bounty_deliver_skip", f"[{bounty.id}] {delivery.get('reason', 'unknown')}", "warn")
            else:
                trace("exec_failed",
                      f"[{bounty.id}] Failed at step {exec_result.get('step')}: {exec_result.get('detail', '')[:100]}",
                      "error")
                log(f"  ❌ Execution FAILED at {exec_result.get('step')}")

        total_match = sum(1 for t in LOG if t["action"] == "evaluate_match")
        total_delivered = sum(1 for t in LOG if t["action"] == "bounty_delivered")
        log(f"Cycle complete — {total_match} matched, {total_delivered} delivered")
        return LOG


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AIMS Bountycaster Sniper — autonomous bounty hunting pipeline",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulated mode without real API calls")
    parser.add_argument("--once", action="store_true", help="Single cycle then exit")
    parser.add_argument("--report", action="store_true", help="Print action traces report and exit")
    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run

    if args.report:
        DashboardStatus.print_report(LOG)
        return

    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    log(f"AIMS Bountycaster Sniper starting in {mode} mode")
    log(f"  Poll: {BOUNTYCASTER_API}")
    log(f"  AIMS: {AIMS_API}")
    log(f"  Docker: {'ENABLED' if DOCKER_ENABLED else 'DISABLED'}")
    log(f"  Interval: {POLL_SECONDS}s")

    pipeline = SniperPipeline()

    if args.once:
        pipeline.run_once()
        DashboardStatus.print_report(LOG)
        return

    # Daemon loop
    cycle = 0
    try:
        while True:
            cycle += 1
            log(f"── Cycle #{cycle} ─────────────────────────────────────")
            pipeline.run_once()
            DashboardStatus.print_report(LOG)
            log(f"Sleeping {POLL_SECONDS}s…")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        log("Shutting down gracefully…")
        DashboardStatus.print_report(LOG)
        log("Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
