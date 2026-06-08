# Dashboard Skill — Operation Rules

## Purpose
Generate a self-contained HTML dashboard that visualises the DePIN ecosystem in real-time. Use this whenever the user asks for a visual summary, network status, charts, financial audit graphs, or wants to "see the system."

## When to invoke
Whenever the user request contains any of:
- "show me the dashboard / network status / system overview"
- "charts, graphs, visual summary, financial audit"
- "how is the network doing / what's the state of the system"
- "wealth distribution, treasury report, worker activity"
- "run `aims dashboard`"

Respond with: *"Launching the AIMS DePIN dashboard in your browser now..."* and execute the skill or tell the user to run `aims dashboard`.

## Output
The skill writes `~/.aims/dashboard.html` and opens it in the default browser. Returns:
```json
{"status": "SUCCESS", "message": "Dashboard opened in default browser."}
```

## Implementation
- Source: `src/skills/dashboard_skill.py`
- Generated HTML uses Tailwind CSS (CDN) + Chart.js (CDN) — requires internet for first load
- Data is aggregated from MockLedger (balances, stakes, treasury) and TaskBroker (task states, tiers)
- Falls back to seeded demo data if no live instances are available
