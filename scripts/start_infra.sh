#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# AIMS Bounty Infrastructure — Local Daemon Manager
# ═══════════════════════════════════════════════════════════════
# Manages adapter.py (:9812) + gitcoin_sniper.py as background
# services that survive terminal close (SIGHUP).
#
# Usage:
#   ./scripts/start_infra.sh start       # launch both daemons
#   ./scripts/start_infra.sh stop        # kill both
#   ./scripts/start_infra.sh restart     # stop + start
#   ./scripts/start_infra.sh status      # print status & PIDs
#   ./scripts/start_infra.sh logs        # tail -f both logs
#   ./scripts/start_infra.sh watch       # watchdog mode (auto-restart)
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PIDFILE="$ROOT/.infra.pid"
LOG_DIR="$ROOT/logs"
ADAPTER_LOG="$LOG_DIR/adapter.log"
SNIPER_LOG="$LOG_DIR/sniper.log"

mkdir -p "$LOG_DIR"

# ── helpers ────────────────────────────────────────────────

load_pids() {
    ADAPTER_PID=; SNIPER_PID=; WATCH_PID=
    [[ -f "$PIDFILE" ]] && source "$PIDFILE" || true
}

save_pids() {
    cat > "$PIDFILE" <<-EOF
ADAPTER_PID=${ADAPTER_PID:-}
SNIPER_PID=${SNIPER_PID:-}
WATCH_PID=${WATCH_PID:-}
EOF
}

is_running() {
    local pid=$1 name=$2
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        echo "  🟢 $name (PID $pid)"
        return 0
    else
        echo "  ⚪ $name (stopped)"
        return 1
    fi
}

# ── commands ───────────────────────────────────────────────

cmd_start() {
    echo "🔧 AIMS Infrastructure — Starting daemons..."
    echo "   Root: $ROOT"

    # Kill any leftovers first
    cmd_stop_quiet

    # Export GitHub token so both processes inherit it
    # (also read from .env if present)
    if [[ -f "$ROOT/.env" ]]; then
        set -a; source "$ROOT/.env"; set +a
    fi

    # ── Adapter ──────────────────────────────────────────────
    nohup python3 "$ROOT/scripts/bounty_adapter.py" \
        >> "$ADAPTER_LOG" 2>&1 &
    ADAPTER_PID=$!
    disown "$ADAPTER_PID" 2>/dev/null || true
    echo "   ✅ adapter.py → PID $ADAPTER_PID  (log: logs/adapter.log)"

    # Small gap so startup messages flush before sniper
    sleep 1

    # ── Sniper ───────────────────────────────────────────────
    nohup python3 "$ROOT/scripts/gitcoin_sniper.py" \
        >> "$SNIPER_LOG" 2>&1 &
    SNIPER_PID=$!
    disown "$SNIPER_PID" 2>/dev/null || true
    echo "   ✅ gitcoin_sniper.py → PID $SNIPER_PID  (log: logs/sniper.log)"

    save_pids
    echo "   📍 PIDs saved to .infra.pid"
    echo "   🛡️  SIGHUP protected — close terminal safely."
}

cmd_stop() {
    echo "🔧 AIMS Infrastructure — Stopping daemons..."
    cmd_stop_quiet
    echo "   ✅ All processes stopped."
}

cmd_stop_quiet() {
    load_pids
    for pid_var in ADAPTER_PID SNIPER_PID WATCH_PID; do
        local pid="${!pid_var:-}"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            # Wait up to 5s for graceful shutdown, then -9
            for _ in $(seq 1 5); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 1
            done
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
    rm -f "$PIDFILE"
}

cmd_status() {
    echo "🔧 AIMS Infrastructure — Status"
    load_pids
    is_running "$ADAPTER_PID" "bounty_adapter.py" || true
    is_running "$SNIPER_PID"  "gitcoin_sniper.py" || true
    is_running "$WATCH_PID"   "watchdog" || true

    echo ""
    echo "   Last log lines:"
    echo "   ── adapter.log ──"
    tail -3 "$ADAPTER_LOG" 2>/dev/null | sed 's/^/   /'
    echo "   ── sniper.log ──"
    tail -3 "$SNIPER_LOG" 2>/dev/null | sed 's/^/   /'
}

cmd_logs() {
    tail -f "$ADAPTER_LOG" "$SNIPER_LOG"
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

# ── Watchdog: auto-restart on crash ──────────────────────

cmd_watch() {
    cmd_start
    echo "🔧 Watchdog enabled — monitoring every 30s..."

    (
        while true; do
            load_pids
            restarted=0

            if ! kill -0 "$ADAPTER_PID" 2>/dev/null; then
                echo "[watchdog] adapter.py died — restarting..." >> "$ADAPTER_LOG"
                nohup python3 "$ROOT/scripts/bounty_adapter.py" >> "$ADAPTER_LOG" 2>&1 &
                ADAPTER_PID=$!
                disown "$ADAPTER_PID" 2>/dev/null || true
                save_pids
                restarted=1
            fi

            if ! kill -0 "$SNIPER_PID" 2>/dev/null; then
                echo "[watchdog] gitcoin_sniper.py died — restarting..." >> "$SNIPER_LOG"
                nohup python3 "$ROOT/scripts/gitcoin_sniper.py" >> "$SNIPER_LOG" 2>&1 &
                SNIPER_PID=$!
                disown "$SNIPER_PID" 2>/dev/null || true
                save_pids
                restarted=1
            fi

            [[ "$restarted" -eq 1 ]] && echo "[watchdog] $(date) — auto-restart complete" >> "$ADAPTER_LOG"
            sleep 30
        done
    ) &

    WATCH_PID=$!
    disown "$WATCH_PID" 2>/dev/null || true
    save_pids
    echo "   ✅ Watchdog PID $WATCH_PID"
    echo "   👁️  Checking every 30s — auto-restarts on crash."
}

# ── dispatch ─────────────────────────────────────────────

case "${1:-start}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    watch)   cmd_watch ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|watch}"
        exit 1
        ;;
esac
