#!/usr/bin/env python3
"""AIMS 2.0 业务端到端联调测试 — 跨境贸易结算触发脚本。

模拟一笔真实的跨境贸易采购结算业务：
  1. 生成买方钱包（随机 EOA）
  2. EIP-191 签名 → POST /api/run 触发任务
  3. 轮询任务状态直至完成
  4. 打印完整结算报告

使用方法:
  python3 scripts/test_trigger_biz.py
  python3 scripts/test_trigger_biz.py --watch-logs   # 同时跟踪 docker 日志
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from threading import Thread
from typing import Any

import requests

from eth_account import Account
from eth_account.messages import encode_defunct

GATEWAY_URL = os.getenv("AIMS_GATEWAY_URL", "http://localhost:8000")
RUN_ENDPOINT = f"{GATEWAY_URL}/api/run"
STATUS_ENDPOINT = f"{GATEWAY_URL}/api/tasks/{{task_id}}/status"
HEALTH_ENDPOINT = f"{GATEWAY_URL}/api/health"
USDC_DECIMALS = 6

# ── 跨境贸易模拟数据 ──────────────────────────────────────────────────────────

TRADE_SCENARIO = {
    "skill_id": "amazon_scraper",
    "params": {
        "search_term": "wholesale electronics components global shipping",
        "max_results": 25,
        "sort_by": "relevance",
    },
    "user_id": "",  # filled at runtime with buyer wallet
    "developer_premium": 0.0,
    "max_budget": 2.0,
    "compute_tier": 1,
}
"""模拟数据：一位海外买家正在搜索电子元器件全球批发电商数据，用于跨境采购比价和合规结算审查。"""

BIZ_CONTEXT = {
    "buyer": "Overseas Electronics Co., Ltd (Singapore)",
    "compliance_ref": "CRC-2026-0616-AIMS",
    "settlement_currency": "USDC",
    "network": "Base (chain 8453)",
    "purpose": "Cross-border electronic components procurement — price benchmarking & compliance settlement",
}
"""业务上下文——用于日志展示，不参与实际的 API 调用。"""


# ── 辅助函数 ─────────────────────────────────────────────────────────────────


def style(label: str, text: str, color: str = "cyan") -> str:
    """Simple terminal coloring."""
    codes = {"cyan": "36", "green": "32", "yellow": "33", "red": "31", "magenta": "35", "bold": "1"}
    c = codes.get(color, "0")
    return f"\033[{c}m{label}\033[0m{text}"


def generate_buyer_wallet() -> tuple[Account, str]:
    """Generate a fresh random EVM wallet for the buyer."""
    account = Account.create()
    return account, account.address


def sign_body(body: dict[str, Any], account: Account) -> tuple[str, str, str]:
    """EIP-191 personal_sign over the raw JSON body.

    Returns (wallet_address, signature, timestamp).
    """
    ts = str(int(time.time()))
    body_bytes = json.dumps(body).encode()
    signable = encode_defunct(primitive=body_bytes)
    signed = account.sign_message(signable)
    return account.address, signed.signature.hex(), ts


def eip191_headers(body: dict[str, Any], account: Account) -> dict[str, str]:
    """Build the three EIP-191 auth headers for a POST request."""
    wallet, sig, ts = sign_body(body, account)
    return {
        "X-Wallet-Address": wallet,
        "X-Signature": sig,
        "X-Timestamp": ts,
        "Content-Type": "application/json",
    }


def check_health() -> dict[str, Any]:
    """Check gateway health."""
    resp = requests.get(HEALTH_ENDPOINT, timeout=5)
    resp.raise_for_status()
    return resp.json()


def trigger_task(body: dict[str, Any], account: Account) -> str:
    """POST /api/run and return the task_id."""
    headers = eip191_headers(body, account)
    resp = requests.post(RUN_ENDPOINT, json=body, headers=headers, timeout=15)

    if resp.status_code == 402:
        detail = resp.json().get("detail", "")
        print(style("  ⛔ 余额不足: ", detail, "red"))
        print(style("  ➜  ", "请先通过 POST /api/wallet/deposit 充值 USDC", "yellow"))
    elif resp.status_code == 503:
        detail = resp.json().get("detail", "")
        print(style("  ⛔ 熔断中: ", detail, "red"))
        print(style("  ➜  ", "请等待自愈或联系管理员 POST /api/admin/reset", "yellow"))

    resp.raise_for_status()
    data = resp.json()
    return data["task_id"]


def poll_task(task_id: str, interval: float = 2.0, timeout: float = 120.0) -> dict[str, Any]:
    """Poll task status until completion or timeout."""
    start = time.time()
    last_status = ""

    while time.time() - start < timeout:
        resp = requests.get(STATUS_ENDPOINT.format(task_id=task_id), timeout=10)
        resp.raise_for_status()
        status = resp.json()

        current_status = status.get("status", "UNKNOWN")
        if current_status != last_status:
            ts = time.time() - start
            print(style(f"  ▸ [{ts:6.1f}s] 状态: ", f"{current_status:<12}", "cyan"), end="")
            if status.get("worker_id"):
                print(style("  Worker: ", status["worker_id"], "magenta"))
            else:
                print()

            if current_status in ("SUCCESS", "FAILED"):
                return status

            last_status = current_status

        time.sleep(interval)

    print(style("  ⏰ 轮询超时 — 任务 ", task_id, "red"))
    return {"status": "TIMEOUT", "task_id": task_id}


def watch_logs(container_pattern: str = "aims-prod") -> None:
    """Tail docker compose logs in a background thread."""
    def _tail():
        try:
            cmd = [
                "docker", "compose", "-f", "docker-compose.prod.yml",
                "logs", "-f", "--tail", "5",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )
            for line in proc.stdout:
                if "worker" in line.lower() or "judge" in line.lower() or "settl" in line.lower():
                    print(f"  [LOG] {line.rstrip()}")
        except Exception:
            pass

    Thread(target=_tail, daemon=True).start()


# ── 主流程 ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="AIMS 2.0 跨境贸易结算 E2E 联调测试")
    parser.add_argument("--watch-logs", action="store_true", help="跟踪 docker 日志")
    parser.add_argument("--search-term", default=TRADE_SCENARIO["params"]["search_term"],
                        help="搜索关键词（默认：跨境电子元器件）")
    args = parser.parse_args()

    print()
    print(style("=", 70, "bold"))
    print(style("  AIMS 2.0 业务端到端联调测试", "  — 跨境贸易结算", "bold"))
    print(style("=", 70, "bold"))
    print()

    # ── 1. 检查网关 ──────────────────────────────────────────────────────────
    print(style("▌ 1. 健康检查", "", "bold"))
    try:
        health = check_health()
        print(f"    网关状态: {health['status']}")
        print(f"    待处理任务: {health['tasks_pending']}")
        print(f"    活跃 Worker: {health.get('workers_active', '?')}")
    except Exception as e:
        print(style(f"    ❌ 网关不可达: {e}", "", "red"))
        print(style("    ➜  ", "请确保网关运行在 8000 端口", "yellow"))
        sys.exit(1)
    print()

    # ── 2. 生成买方钱包 ─────────────────────────────────────────────────────
    print(style("▌ 2. 生成买方钱包", "", "bold"))
    buyer, wallet = generate_buyer_wallet()
    print(f"    钱包地址: {wallet}")
    print(f"    私钥前8位: {buyer.key.hex()[:16]}...")
    print()

    # ── 3. 组装业务数据 ─────────────────────────────────────────────────────
    print(style("▌ 3. 组装跨境贸易结算请求", "", "bold"))
    body = dict(TRADE_SCENARIO)
    body["params"]["search_term"] = args.search_term
    body["user_id"] = wallet

    print(f"    Skill:      {body['skill_id']}")
    print(f"    搜索词:     {body['params']['search_term']}")
    print(f"    买家:       {BIZ_CONTEXT['buyer']}")
    print(f"    合规编号:   {BIZ_CONTEXT['compliance_ref']}")
    print(f"    结算币种:   {BIZ_CONTEXT['settlement_currency']} ({BIZ_CONTEXT['network']})")
    print()

    # ── 4. 发送任务 ──────────────────────────────────────────────────────────
    print(style("▌ 4. 发送结算任务 → /api/run", "", "bold"))

    if args.watch_logs:
        watch_logs()
        print(style("    📡 后台日志跟踪已启动", "", "green"))

    try:
        task_id = trigger_task(body, buyer)
        print(f"    任务 ID: {task_id}")
        print(f"    状态:     PENDING (等待 Worker 抢单...)")
    except requests.HTTPError as e:
        print(style(f"    ❌ 任务发送失败: {e}", "", "red"))
        if e.response is not None:
            try:
                detail = e.response.json()
                print(f"    详情: {json.dumps(detail, indent=6)}")
            except Exception:
                print(f"    Body: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(style(f"    ❌ 请求异常: {e}", "", "red"))
        sys.exit(1)
    print()

    # ── 5. 轮询任务完成 ─────────────────────────────────────────────────────
    print(style("▌ 5. 轮询任务 & 实时状态", "", "bold"))
    result = poll_task(task_id)
    print()

    # ── 6. 结算报告 ─────────────────────────────────────────────────────────
    print(style("▌ 6. 结算报告", "", "bold"))

    status = result.get("status", "UNKNOWN")
    worker_id = result.get("worker_id", "N/A")

    if status == "SUCCESS":
        print(f"    {style('✓', '', 'green')} 任务:      {task_id}")
        print(f"    {style('✓', '', 'green')} 抢单 Worker: {worker_id}")
        print(f"    {style('✓', '', 'green')} 链上结算:   已执行")
        outcome = result.get("outcome", "COMPLETED")
        pot = result.get("pot", "")
        print(f"    {style('✓', '', 'green')} 结果:      {outcome}")
        if pot:
            print(f"    {style('✓', '', 'green')} PoT:       {pot[:66]}...")
        print()
        print(style("  🎉 跨境贸易结算全链路验证通过！", "", "green"))
        network = BIZ_CONTEXT['network']
        print(f"  Worker {worker_id} 已抢单并完成执行，链上 {network} 已结算。")

    elif status == "FAILED":
        print(f"    {style('✗', '', 'red')} 任务:      {task_id}")
        outcome = result.get("outcome", "FAILED")
        print(f"    {style('✗', '', 'red')} 结果:      {outcome}")
        print(f"    请检查 DeepSeek AI Judge 判定详情")

    elif status == "PENDING":
        print(f"    {style('○', '', 'yellow')} 任务:      {task_id} (仍在排队中)")
        print(f"    {style('➜', '', 'yellow')} 请检查 Worker 是否运行: docker ps --filter name=aims-prod-worker")
        health = check_health()
        print(f"    当前 Worker 活跃数: {health.get('workers_active', '?')}")

    else:
        print(f"    状态: {status}")

    print()


if __name__ == "__main__":
    main()
