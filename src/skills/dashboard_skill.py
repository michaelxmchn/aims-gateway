"""Ephemeral Dashboard Skill — real-time DePIN ecosystem visualiser.

Generates a self-contained HTML dashboard (Tailwind + Chart.js) showing
network health, wealth distribution, task throughput, and slashing logs.
Opens the dashboard in the user's default browser.

Two modes:
  - **Live**: pass existing MockLedger / TaskBroker instances.
  - **Demo** (default): creates fresh instances with rich seed data.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from src.gateway.broker import TaskBroker
from src.ledger.mock_counter import MockLedger
from src.runtime.sandbox import SKILL_IMPLS, WorkflowEngine, resolve_impl, start_worker_loop
from src.skills.manifest import SkillManifest

logger = logging.getLogger(__name__)

# ── Seed Data ──────────────────────────────────────────────────────────────


def _seed_ecosystem(ledger: MockLedger, broker: TaskBroker) -> Dict[str, Any]:
    """Populate ledger and broker with realistic DePIN ecosystem data.

    Returns a dict of aggregated metrics for the HTML template.
    """

    # ── Users ──────────────────────────────────────────────────────
    users = {
        "alice": 100.0,
        "bob": 50.0,
        "carol": 25.0,
    }
    for uid, bal in users.items():
        ledger.seed_usdt(uid, bal)

    # ── Workers & staking ──────────────────────────────────────────
    workers = {
        "worker_alpha": {"stake": 5.0, "strikes": 0},
        "worker_beta": {"stake": 5.0, "strikes": 0},
        "worker_gamma": {"stake": 5.0, "strikes": 3, "slashed": 1.0},
        "worker_delta": {"stake": 10.0, "strikes": 0},
    }
    for wid, info in workers.items():
        ledger.seed_dev_usdt(wid, info["stake"])
        ledger.register_worker(wid, info["stake"])
        if info.get("slashed"):
            # Manually reduce collateral to simulate past slash
            ledger._staked_collateral[wid] = info["stake"] - info["slashed"]
            ledger._founder_treasury_usdt += info["slashed"]
            ledger.worker_strikes[wid] = info["strikes"]

    # ── Slashing events ────────────────────────────────────────────
    slashing_log: List[Dict[str, Any]] = [
        {"worker": "worker_gamma", "reason": "timeout (3 strikes)", "penalty": 1.0,
         "collateral_before": 5.0, "collateral_after": 4.0,
         "timestamp": "2026-06-08 14:23:11"},
        {"worker": "worker_gamma", "reason": "corrupt output: missing 'products'", "penalty": 0.0,
         "collateral_before": 4.0, "collateral_after": 4.0,
         "timestamp": "2026-06-08 14:25:37"},
        {"worker": "worker_beta", "reason": "output validation: bad price=-5", "penalty": 0.0,
         "collateral_before": 5.0, "collateral_after": 5.0,
         "timestamp": "2026-06-08 14:28:04"},
    ]

    # ── Publish tasks across compute tiers ─────────────────────────
    task_configs = [
        ("ASIN-A", 1, 1.0, 2.0, 10),
        ("ASIN-B", 2, 1.0, 2.5, 6),
        ("ASIN-C", 3, 1.0, 6.0, 3),
        ("ASIN-D", 1, 1.0, 2.0, 8),
        ("ASIN-E", 2, 1.0, 2.5, 4),
    ]
    for asin, tier, budget, _mult, count in task_configs:
        for _ in range(count):
            broker.publish_task(
                user_id="alice",
                asin=asin,
                developer_premium=budget,
                max_budget=budget,
                skill_id="amazon_scraper",
                compute_tier=tier,
            )

    # ── Process tasks through workers ──────────────────────────────
    manifest = SkillManifest(
        name="amazon_scraper",
        description="Scrape Amazon listings",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema={"type": "object", "properties": {}, "required": []},
        version="1.0.0",
        author="aims_seed",
        price_points=1.0,
        tags=["scraping"],
    )

    engine = WorkflowEngine(resolve_impl)
    stop_event = threading.Event()
    threads = []
    for wid in list(workers.keys())[:3]:  # 3 active workers
        t = threading.Thread(
            target=start_worker_loop,
            args=(wid, ledger, broker, engine, manifest, stop_event),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Wait for drain
    while broker.pending_count > 0:
        time.sleep(0.3)

    # Recycle any claimed leftovers
    broker.check_timeouts()
    while broker.status_counts().get("CLAIMED", 0) > 0:
        broker.check_timeouts()
        time.sleep(0.3)
    time.sleep(2.0)
    stop_event.set()

    # ── Reputation data ────────────────────────────────────────────
    for uid in list(users.keys())[:2]:
        ledger._user_skill_usage.setdefault(uid, set()).add("amazon_scraper")
        ledger._user_reputation.setdefault(uid, 1.0)
    ledger._user_reputation["malicious_actor"] = 0.7

    rating_entries = [
        {"user_id": "alice", "reputation": 1.0, "rating": 5.0},
        {"user_id": "bob", "reputation": 1.0, "rating": 4.5},
        {"user_id": "carol", "reputation": 1.0, "rating": 5.0},
    ]
    ledger._skill_rating_entries["amazon_scraper"] = rating_entries
    total_w = sum(e["reputation"] * e["rating"] for e in rating_entries)
    total_r = sum(e["reputation"] for e in rating_entries)
    ledger._skill_weighted_score["amazon_scraper"] = (
        round(total_w / total_r, 2) if total_r > 0 else 5.0
    )

    # ── Build metrics dict ─────────────────────────────────────────
    status_counts = broker.status_counts()
    tier_counts: Dict[int, int] = {1: 0, 2: 0, 3: 0}
    for tid, state in broker._status.items():
        task = broker._tasks.get(tid)
        if task:
            tier_counts[task.compute_tier] = tier_counts.get(task.compute_tier, 0) + 1

    total_user_balances = sum(ledger._user_balances.values())
    total_staked = sum(ledger._staked_collateral.values())
    total_dev_balances = sum(ledger._dev_balances.values())
    treasury = ledger._founder_treasury_usdt

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": {
            "pending": status_counts.get("PENDING", 0),
            "claimed": status_counts.get("CLAIMED", 0),
            "completed": status_counts.get("SUCCESS", 0) + status_counts.get("FAILED", 0),
            "total": len(broker._status),
        },
        "wealth": {
            "user_balances": round(total_user_balances, 2),
            "worker_stakes": round(total_staked, 2),
            "treasury": round(treasury, 2),
            "dev_balances": round(total_dev_balances, 2),
            "total_value_locked": round(total_user_balances + total_staked + treasury + total_dev_balances, 2),
        },
        "tier_counts": tier_counts,
        "workers": [
            {"id": wid, "stake": ledger.get_staked_collateral(wid),
             "strikes": ledger.worker_strikes.get(wid, 0)}
            for wid in workers
        ],
        "slashing_log": slashing_log,
        "reputation": {
            "skill": ledger.get_skill_weighted_score("amazon_scraper"),
            "users": {uid: ledger.get_user_reputation(uid) for uid in list(users.keys()) + ["malicious_actor"]},
            "total_ratings": len(rating_entries),
        },
    }


# ── HTML Template ─────────────────────────────────────────────────────────


def _build_html(metrics: Dict[str, Any]) -> str:
    """Render a self-contained HTML dashboard page."""

    # Serialise metrics as JSON once for Chart.js
    data_json = json.dumps(metrics)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIMS DePIN Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * {{ font-family: 'Inter', sans-serif; }}
  body {{ background: #0b0f1a; }}
  .glass {{ background: rgba(255,255,255,0.03); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.06); }}
  .stat-card {{ transition: transform 0.2s ease, box-shadow 0.2s ease; }}
  .stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.4); }}
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: #0b0f1a; }}
  ::-webkit-scrollbar-thumb {{ background: #2a2f42; border-radius: 3px; }}
</style>
</head>
<body class="text-gray-100 p-4 md:p-8">

<div class="max-w-7xl mx-auto">

  <!-- ── Header ────────────────────────────────────────────── -->
  <div class="flex items-center justify-between mb-8">
    <div>
      <h1 class="text-3xl font-bold tracking-tight">
        <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-500">
          AIMS DePIN Dashboard
        </span>
      </h1>
      <p class="text-gray-500 text-sm mt-1">Universal AI Skill Hub — Live Network Overview</p>
    </div>
    <div class="text-right text-sm text-gray-500">
      <div id="live-time" class="font-mono text-cyan-400"></div>
      <div class="mt-1">generated <span id="gen-time" class="font-mono text-gray-400">{metrics['timestamp']}</span></div>
    </div>
  </div>

  <!-- ── Stat Cards ─────────────────────────────────────────── -->
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
    <div class="stat-card glass rounded-xl p-5">
      <div class="text-gray-500 text-xs uppercase tracking-widest">Total Tasks</div>
      <div class="text-3xl font-bold mt-1 text-white">{metrics['tasks']['total']}</div>
      <div class="flex gap-3 text-xs mt-2 text-gray-400">
        <span><span class="text-yellow-400">●</span> Pending {metrics['tasks']['pending']}</span>
        <span><span class="text-blue-400">●</span> Claimed {metrics['tasks']['claimed']}</span>
        <span><span class="text-green-400">●</span> Done {metrics['tasks']['completed']}</span>
      </div>
    </div>
    <div class="stat-card glass rounded-xl p-5">
      <div class="text-gray-500 text-xs uppercase tracking-widest">Active Workers</div>
      <div class="text-3xl font-bold mt-1 text-white">{len(metrics['workers'])}</div>
      <div class="text-xs mt-2 text-gray-400">
        <span class="text-green-400">●</span> {sum(1 for w in metrics['workers'] if w['strikes'] == 0)} honest
        <span class="text-red-400">●</span> {sum(1 for w in metrics['workers'] if w['strikes'] > 0)} flagged
      </div>
    </div>
    <div class="stat-card glass rounded-xl p-5">
      <div class="text-gray-500 text-xs uppercase tracking-widest">Platform Treasury</div>
      <div class="text-3xl font-bold mt-1 text-emerald-400">${metrics['wealth']['treasury']:.2f}</div>
      <div class="text-xs mt-2 text-gray-400">incl. slashed collateral</div>
    </div>
    <div class="stat-card glass rounded-xl p-5">
      <div class="text-gray-500 text-xs uppercase tracking-widest">Total Value Locked</div>
      <div class="text-3xl font-bold mt-1 text-violet-400">${metrics['wealth']['total_value_locked']:.2f}</div>
      <div class="text-xs mt-2 text-gray-400">USDT across all pools</div>
    </div>
  </div>

  <!-- ── Charts Row ─────────────────────────────────────────── -->
  <div class="grid md:grid-cols-2 gap-6 mb-8">
    <div class="glass rounded-xl p-6">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Wealth Distribution</h2>
      <canvas id="wealthChart" height="220"></canvas>
    </div>
    <div class="glass rounded-xl p-6">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Active Tasks by Compute Tier</h2>
      <canvas id="tierChart" height="220"></canvas>
    </div>
  </div>

  <!-- ── Slashing & Arbitration Logs ────────────────────────── -->
  <div class="glass rounded-xl p-6 mb-8">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">
        ⚡ Slashing & Arbitration Logs
      </h2>
      <span class="text-xs text-gray-600">{len(metrics['slashing_log'])} events</span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
            <th class="text-left py-3 px-2">Worker</th>
            <th class="text-left py-3 px-2">Reason</th>
            <th class="text-right py-3 px-2">Penalty</th>
            <th class="text-right py-3 px-2">Collateral</th>
            <th class="text-right py-3 px-2">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {''.join(f'''
          <tr class="border-b border-gray-800/50 hover:bg-white/5 transition-colors">
            <td class="py-3 px-2 font-mono text-red-400">{e['worker']}</td>
            <td class="py-3 px-2 text-gray-300">{e['reason']}</td>
            <td class="py-3 px-2 text-right">{"−$" + f"{e['penalty']:.2f}" if e['penalty'] > 0 else '<span class="text-gray-600">—</span>'}</td>
            <td class="py-3 px-2 text-right font-mono">${e['collateral_before']:.2f} → ${e['collateral_after']:.2f}</td>
            <td class="py-3 px-2 text-right text-gray-500 font-mono text-xs">{e['timestamp']}</td>
          </tr>''' for e in metrics['slashing_log'])}
        </tbody>
      </table>
    </div>
  </div>

  <!-- ── Reputation Panel ────────────────────────────────────── -->
  <div class="grid md:grid-cols-2 gap-6 mb-8">
    <div class="glass rounded-xl p-6">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Skill Reputation</h2>
      <div class="flex items-center gap-3">
        <span class="text-4xl font-bold text-cyan-400">{metrics['reputation']['skill']:.1f}</span>
        <div class="text-sm text-gray-400">
          <div>amazon_scraper</div>
          <div class="text-xs">{metrics['reputation']['total_ratings']} ratings</div>
        </div>
      </div>
    </div>
    <div class="glass rounded-xl p-6">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">User Reputation</h2>
      <div class="space-y-2">
        {''.join(f'''
        <div class="flex items-center justify-between">
          <span class="text-sm font-mono text-gray-300">{uid}</span>
          <div class="flex items-center gap-2">
            <div class="w-24 h-1.5 rounded-full bg-gray-700 overflow-hidden">
              <div class="h-full rounded-full {"bg-green-500" if rep >= 1.0 else "bg-yellow-500" if rep >= 0.8 else "bg-red-500"}" style="width:{rep * 100:.0f}%"></div>
            </div>
            <span class="text-xs font-mono {"text-green-400" if rep >= 1.0 else "text-yellow-400" if rep >= 0.8 else "text-red-400"}">{rep:.2f}</span>
          </div>
        </div>''' for uid, rep in metrics['reputation']['users'].items())}
      </div>
    </div>
  </div>

  <!-- ── Footer ─────────────────────────────────────────────── -->
  <div class="text-center text-xs text-gray-700 py-6 border-t border-gray-800">
    AIMS Protocol — Autonomous Intelligence Market Settlement &nbsp;·&nbsp; Dashboard auto-generated
  </div>

</div>

<script>
const data = {data_json};

// ── Wealth Pie Chart ──────────────────────────────────────
new Chart(document.getElementById('wealthChart'), {{
  type: 'pie',
  data: {{
    labels: ['User Balances', 'Worker Stakes', 'Platform Treasury'],
    datasets: [{{
      data: [data.wealth.user_balances, data.wealth.worker_stakes, data.wealth.treasury],
      backgroundColor: ['#22d3ee', '#a78bfa', '#34d399'],
      borderColor: '#0b0f1a',
      borderWidth: 3,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ color: '#9ca3af', padding: 16, font: {{ size: 12 }} }} }},
      tooltip: {{ callbacks: {{ label: ctx => `${{ctx.parsed.toFixed(2)}} USDT` }} }}
    }}
  }}
}});

// ── Tier Bar Chart ────────────────────────────────────────
new Chart(document.getElementById('tierChart'), {{
  type: 'bar',
  data: {{
    labels: ['Tier 1 (1.0x)', 'Tier 2 (2.5x)', 'Tier 3 (6.0x)'],
    datasets: [{{
      label: 'Tasks',
      data: [data.tier_counts['1'] || 0, data.tier_counts['2'] || 0, data.tier_counts['3'] || 0],
      backgroundColor: ['rgba(34,211,238,0.7)', 'rgba(167,139,250,0.7)', 'rgba(244,114,182,0.7)'],
      borderColor: ['#22d3ee', '#a78bfa', '#f472b6'],
      borderWidth: 1,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      x: {{ ticks: {{ color: '#9ca3af' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
      y: {{ beginAtZero: true, ticks: {{ stepSize: 1, color: '#9ca3af' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// ── Live clock ────────────────────────────────────────────
function updateClock() {{
  document.getElementById('live-time').textContent =
    new Date().toLocaleTimeString('en-US', {{ hour12: false }}) + ' UTC';
}}
updateClock();
setInterval(updateClock, 1000);
</script>
</body>
</html>"""


# ── Public API ─────────────────────────────────────────────────────────────


def generate_dashboard(
    ledger: Optional[MockLedger] = None,
    broker: Optional[TaskBroker] = None,
) -> Dict[str, Any]:
    """Aggregate metrics, write HTML to ``~/.aims/dashboard.html``, open browser.

    If *ledger* and *broker* are provided, uses live data from those
    instances. Otherwise creates fresh instances with demo seed data.
    """
    if broker is None or ledger is None:
        ledger = MockLedger()
        broker = TaskBroker(ledger)

    metrics = _seed_ecosystem(ledger, broker)
    html = _build_html(metrics)

    html_dir = os.path.expanduser("~/.aims")
    os.makedirs(html_dir, exist_ok=True)
    html_path = os.path.join(html_dir, "dashboard.html")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    webbrowser.open(f"file://{html_path}")

    return {
        "status": "SUCCESS",
        "message": "Dashboard opened in default browser.",
        "path": html_path,
    }


# ── CLI entry point ─────────────────────────────────────────────────────────


def run_dashboard() -> None:
    """CLI entry point for ``aims dashboard``."""
    import logging
    logging.basicConfig(level=logging.WARNING)

    result = generate_dashboard()
    print(json.dumps(result, indent=2))
