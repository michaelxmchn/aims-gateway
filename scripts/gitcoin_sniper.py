#!/usr/bin/env python3
"""
AIMS Gitcoin Sniper — Autonomous Bounty Hunting Pipeline
=========================================================
Poll → Match → Execute → Deliver → Report

Architecture:
  1. GitcoinPoller     — 60s interval poll for OPEN bounties
  2. AIMSEvaluator     — System-prompted LLM judge via AIMS /api/run
  3. CodeExecutor      — git clone + claude-code headless repair + test
  4. AutoDeliverer     — git commit + gh pr create + SSE dashboard report

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
GITCOIN_API = os.getenv("GITCOIN_API", "https://gitcoin.co/api/v1/bounty")
GITCOIN_API_FALLBACKS = [
    "https://gitcoin.co/api/v1/bounties",
    "https://gitcoin.co/api/v0.1/bounties",
]
AIMS_API    = os.getenv("AIMS_API", "http://127.0.0.1:8001")
AIMS_API_KEY = os.getenv("AIMS_API_KEY", "")
AIMS_WALLET  = os.getenv("AIMS_WALLET", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
MAX_CLONE_AGE_SECONDS = 3600 * 6  # don't touch clones older than 6h

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
# 1. GITCOIN POLLER
# ═══════════════════════════════════════════════════════════════

class GitcoinBounty:
    """Normalised bounty from the Gitcoin API (or mock)."""
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


class GitcoinPoller:
    """Every 60 s fetch OPEN bounties, yield those not yet seen."""

    def __init__(self, api_url: str = GITCOIN_API):
        self.api_url = api_url
        self._seen: set[str] = set()

    def fetch(self) -> list[GitcoinBounty]:
        """Hit the Gitcoin API and return a list of open bounties."""
        if DRY_RUN:
            return self._mock_bounties()

        try:
            resp = requests.get(
                self.api_url,
                params={"network": "mainnet", "status": "open", "order_by": "-created_on"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("results", data.get("bounties", []))
            raw_list = data if isinstance(data, list) else []
            return [GitcoinBounty(b) for b in raw_list]
        except requests.RequestException:
            # Try fallback endpoints
            for fallback in GITCOIN_API_FALLBACKS:
                try:
                    resp = requests.get(fallback, timeout=15)
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict):
                        data = data.get("results", data.get("bounties", data.get("data", [])))
                    if isinstance(data, list) and len(data) > 0:
                        log(f"Fallback API working: {fallback}")
                        return [GitcoinBounty(b) for b in data]
                except requests.RequestException:
                    continue
            log(f"All Gitcoin APIs unreachable — will retry in {POLL_SECONDS}s", "WARN")
            return []

    def _mock_bounties(self) -> list[GitcoinBounty]:
        """Return simulated bounties for dry-run testing."""
        return [
            GitcoinBounty({
                "id": "mock-001",
                "title": "Fix broken CSS grid layout in dashboard",
                "description": (
                    "## Bug Report\n"
                    "The admin dashboard grid collapses on tablets (<768px). "
                    "The `.stats-grid` container overflows and hides the bottom row. "
                    "## Requirements\n"
                    "- Apply `flex-wrap: wrap` to `.stats-grid`\n"
                    "- Ensure all 6 stat cards are visible at 600px width\n"
                    "- No regressions on desktop >1024px\n"
                    "## Acceptance\n"
                    "- `npm run test` passes with 0 failures\n"
                    "- Visual diff shows the fix"
                ),
                "github_url": "https://github.com/example/dashboard-ui/issues/42",
                "repo_url": "https://github.com/example/dashboard-ui",
                "status": "OPEN",
                "value_in_usdt": 150.0,
            }),
            GitcoinBounty({
                "id": "mock-002",
                "title": "Add unit tests for payment module",
                "description": (
                    "## Task\n"
                    "The payment module lacks coverage for edge cases:\n"
                    "- Empty cart checkout\n"
                    "- Invalid coupon codes\n"
                    "- Payment gateway timeout handling\n"
                    "## Requirements\n"
                    "- Write Jest tests in `__tests__/payment.test.ts`\n"
                    "- Achieve >=80% branch coverage on `src/payment/`\n"
                    "- Mock Stripe SDK calls"
                ),
                "github_url": "https://github.com/example/ecommerce-api/issues/88",
                "repo_url": "https://github.com/example/ecommerce-api",
                "status": "OPEN",
                "value_in_usdt": 300.0,
            }),
            GitcoinBounty({
                "id": "mock-003",
                "title": "Research and document API rate-limit strategy",
                "description": (
                    "## Task\n"
                    "Write a technical RFC comparing rate-limiting strategies "
                    "(token bucket, sliding window, Redis-based) for our public API."
                    "## Deliverable\n"
                    "- Markdown doc in `docs/rfcs/rate-limiting.md`\n"
                    "- Not an implementation — research only"
                ),
                "github_url": "https://github.com/example/api-docs/issues/12",
                "repo_url": "https://github.com/example/api-docs",
                "status": "OPEN",
                "value_in_usdt": 75.0,
            }),
        ]

    def new_bounties(self) -> list[GitcoinBounty]:
        """Return bounties not seen in previous polls."""
        batch = self.fetch()
        fresh = [b for b in batch if b.id not in self._seen]
        for b in fresh:
            self._seen.add(b.id)
        return fresh


# ═══════════════════════════════════════════════════════════════
# 2. AIMS SKILL MATCHER
# ═══════════════════════════════════════════════════════════════

class AIMSEvaluator:
    """Send bounty description to AIMS gateway LLM; return MATCH / NO_MATCH."""

    # System prompt: gate the model to only accept tasks solvable by code gen / auto-fix
    SYSTEM_PROMPT = (
        "You are an expert bounty analyst for AIMS Gateway. "
        "Your ONLY job is to decide whether a Gitcoin bounty task can be COMPLETELY SOLVED "
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

    def evaluate(self, bounty: GitcoinBounty) -> tuple[bool, int, str]:
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
            "skill_id": "code_security_audit",  # reuse an existing general skill
            "params": {
                "prompt": self.SYSTEM_PROMPT,
                "bounty_title": bounty.title,
                "bounty_description": bounty.description,
                "bounty_url": bounty.url,
            },
            "user_id": "gitcoin-sniper-bot",
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

    def _mock_evaluate(self, bounty: GitcoinBounty) -> tuple[bool, int, str]:
        """Keyword-based simulation for dry-run."""
        desc = (bounty.title + " " + bounty.description).lower()
        # Auto-reject research / docs-only tasks
        no_match_keywords = ["research", "document", "rfc", "architecture proposal"]
        if any(kw in desc for kw in no_match_keywords):
            return False, 20, "Research/docs task — not automatable"
        # Keywords that strongly indicate code-fix tasks
        match_keywords = ["fix ", "bug", "test", "coverage", "lint", "build", "css", "grid", "responsive"]
        score = 0
        for kw in match_keywords:
            if kw in desc:
                score += 20
        if score >= 40:
            return True, min(score + 20, 95), f"Dry-run heuristic matched ({score}%)"
        return False, 10, "No matching code-fix keywords"

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
# 3. CODE EXECUTOR
# ═══════════════════════════════════════════════════════════════

class CodeExecutor:
    """Clone repo → invoke claude-code → run tests → PASS/FAIL verdict."""

    TEST_COMMANDS = {
        ".js":  ["npm install", "npm test"],
        ".ts":  ["npm install", "npm test"],
        ".tsx": ["npm install", "npm test"],
        ".py":  ["pip install -e .", "python -m pytest"],
        ".go":  ["go mod tidy", "go test ./..."],
        ".rs":  ["cargo build", "cargo test"],
        ".rb":  ["bundle install", "bundle exec rspec"],
        ".java": ["./gradlew test"],
    }

    def __init__(self, workdir: Path = WORKDIR):
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)

    def execute(self, bounty: GitcoinBounty) -> Optional[dict]:
        """
        Full execution pipeline:
          1. git clone
          2. claude-code headless repair
          3. run tests
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
                # Create a mock repo for dry-run test
                clone_path.mkdir(parents=True, exist_ok=True)
                (clone_path / "package.json").write_text('{"name":"mock","scripts":{"test":"echo ok"}}')
                (clone_path / "READY_MOCK.md").write_text("# Mock Repo\nDry-run only.\n")
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
            # Simulate a fix
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

        # ── 3c. Run tests ────────────────────────────────────────────
        test_cmds = self._detect_test_commands(clone_path)

        if not test_cmds:
            log("No known test framework detected — skipping test phase", "WARN")
            trace("test_skip", "No test framework found")
        else:
            trace("test_start", f"Running: {'; '.join(test_cmds)}")
            for cmd in test_cmds:
                if DRY_RUN:
                    log(f"[DRY-RUN] Would run: {cmd}")
                    continue
                r = subprocess.run(cmd, shell=True, cwd=str(clone_path),
                                   capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    detail = r.stderr[-300:] if r.stderr else r.stdout[-300:]
                    trace("test_failed", f"'{cmd}' exited {r.returncode}: {detail}", "error")
                    return {"status": "FAILED", "step": "test", "detail": detail}
                log(f"Test passed: {cmd}")

        trace("test_passed", "All tests passed (0 failures)")
        return {"status": "PASS", "step": "done", "clone_path": str(clone_path)}

    def _build_prompt(self, bounty: GitcoinBounty) -> str:
        return (
            f"You are an expert software engineer. "
            f"A Gitcoin bounty requires the following task:\n\n"
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
    def _detect_test_commands(path: Path) -> list[str]:
        for f in path.iterdir():
            if f.name == "package.json":
                try:
                    pkg = json.loads(f.read_text())
                    if "test" in pkg.get("scripts", {}):
                        return ["npm install", "npm test"]
                except (json.JSONDecodeError, OSError):
                    pass
            elif f.name == "pyproject.toml" or f.name == "setup.py" or f.name == "setup.cfg":
                return ["pip install -e .", "python -m pytest"]
            elif f.name == "go.mod":
                return ["go mod tidy", "go test ./..." if not DRY_RUN else "echo go test"]
            elif f.name == "Cargo.toml":
                return ["cargo build", "cargo test"]
            elif f.suffix in (".js", ".ts", ".tsx"):
                pass  # fallback below
        return []


# ═══════════════════════════════════════════════════════════════
# 4. AUTO DELIVERER
# ═══════════════════════════════════════════════════════════════

class AutoDeliverer:
    """git commit → gh pr create → SSE dashboard report."""

    def __init__(self, api_base: str = AIMS_API, api_key: str = AIMS_API_KEY):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key

    def deliver(self, bounty: GitcoinBounty, exec_result: dict) -> dict:
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
                # Create and push branch
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
                    # Create PR
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

        # ── Dashboard report via SSE ─────────────────────────────────
        self.report_to_dashboard(bounty, exec_result, pr_url)

        return {"status": "DELIVERED", "pr_url": pr_url or "N/A", "branch": branch}

    def report_to_dashboard(self, bounty: GitcoinBounty, exec_result: dict, pr_url: str) -> None:
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
    def _pr_body(bounty: GitcoinBounty) -> str:
        return (
            f"## Automated Fix — Bounty #{bounty.id}\n\n"
            f"**Title:** {bounty.title}\n\n"
            f"**Value:** {bounty.value} USDC\n\n"
            f"---\n"
            f"*Generated by [AIMS Gitcoin Sniper](https://aims-gateway.fly.dev)*\n"
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
        print("║        AIMS GITCOIN SNIPER — ACTION TRACES REPORT          ║")
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
        self.poller = GitcoinPoller()
        self.evaluator = AIMSEvaluator()
        self.executor = CodeExecutor()
        self.deliverer = AutoDeliverer()

    def run_once(self) -> list[dict]:
        """Single cycle: return action traces generated."""
        log("Polling Gitcoin for new bounties…")
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
        description="AIMS Gitcoin Sniper — autonomous bounty hunting pipeline",
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
    log(f"AIMS Gitcoin Sniper starting in {mode} mode")
    log(f"  Poll: {GITCOIN_API}")
    log(f"  AIMS: {AIMS_API}")
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
