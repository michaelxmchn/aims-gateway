"""AIMS CLI — Universal AI Skill Hub command-line interface.

Usage:
    aims dashboard    Launch the DePIN ecosystem dashboard in your browser
    aims exec <name>  Execute a skill with JSON arguments (inline or file)
    aims list         List all available skills
    aims login        Initialize a session key for wallet authentication
    aims mcp          Start the MCP stdio server (for AI client integration)
    aims help         Show this help message
"""

from __future__ import annotations

import json
import logging
import sys
from typing import No Return

logger = logging.getLogger(__name__)


def _show_help() -> NoReturn:
    print(__doc__)
    sys.exit(0)


def _cmd_dashboard() -> None:
    from src.skills.dashboard_skill import run_dashboard
    run_dashboard()


def _cmd_list() -> None:
    from src.skills.registry import SkillRegistry
    registry = SkillRegistry()
    manifests = registry.get_all_manifests()
    if not manifests:
        print("No skills available.")
        return
    print(f"{'Name':24s}  {'Version':8s}  {'Price':6s}  {'Tags'}")
    print("-" * 70)
    for m in manifests:
        tags = ", ".join(m.tags[:3]) if m.tags else ""
        print(f"{m.name:24s}  v{m.version:6s}  ${m.price_points:>4d}  {tags}")
    print(f"\nTotal: {len(manifests)} skill(s)")


def _cmd_exec() -> None:
    if len(sys.argv) < 3:
        print("Usage: aims exec <skill_name> [<json-args> | @file.json]")
        sys.exit(1)

    skill_name = sys.argv[2]

    if len(sys.argv) >= 4:
        raw = sys.argv[3]
        if raw.startswith("@"):
            with open(raw[1:], "r") as f:
                arguments = json.load(f)
        else:
            arguments = json.loads(raw)
    else:
        arguments = {}

    from src.skills.registry import SkillRegistry
    from src.runtime.sandbox import WorkflowEngine, resolve_impl

    registry = SkillRegistry()
    engine = WorkflowEngine(resolve_impl)

    manifest = registry.get(skill_name)
    if manifest is None:
        print(f"Error: skill '{skill_name}' not found. Use 'aims list' to see available skills.")
        sys.exit(1)

    receipt = engine.execute(manifest, arguments)
    print(json.dumps({
        "skill": receipt.skill_name,
        "status": receipt.status,
        "output": receipt.output if receipt.status == "SUCCESS" else None,
        "error": receipt.error_message if receipt.status == "FAILED" else None,
        "compute_consumed": round(receipt.compute_consumed, 3),
    }, indent=2))
    sys.exit(0 if receipt.status == "SUCCESS" else 1)


def _cmd_login() -> None:
    from src.chain.wallet import SessionKeyManager

    mgr = SessionKeyManager()
    scopes = ["aims:exec", "aims:dashboard"]
    key = mgr.create_session_key(scopes=scopes, expiry=86400 * 7)
    print(json.dumps({
        "status": "created",
        "session_key": key.key_id,
        "scopes": key.scopes,
        "expires_at": key.expiry,
        "message": "Session key created. Use this for AI-client authentication.",
    }, indent=2))


def _cmd_mcp() -> None:
    from src.client.mcp_server import main as mcp_main
    mcp_main()


def main() -> None:
    """Dispatch CLI commands."""
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        _show_help()

    command = sys.argv[1]

    if command == "dashboard":
        _cmd_dashboard()
    elif command == "list":
        _cmd_list()
    elif command == "exec":
        _cmd_exec()
    elif command == "login":
        _cmd_login()
    elif command == "mcp":
        _cmd_mcp()
    else:
        print(f"Unknown command: {command}")
        _show_help()


if __name__ == "__main__":
    main()
