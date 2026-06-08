"""AIMS CLI — Universal AI Skill Hub command-line interface.

Usage:
    aims dashboard    Launch the DePIN ecosystem dashboard in your browser
    aims help         Show this help message
"""

from __future__ import annotations

import sys
from typing import NoReturn


def _show_help() -> NoReturn:
    print(__doc__)
    sys.exit(0)


def main() -> None:
    """Dispatch CLI commands."""
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        _show_help()

    command = sys.argv[1]

    if command == "dashboard":
        from src.skills.dashboard_skill import run_dashboard
        run_dashboard()
    else:
        print(f"Unknown command: {command}")
        _show_help()


if __name__ == "__main__":
    main()
