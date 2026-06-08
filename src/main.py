"""AIMS — Assembly Root (Layer 7).

Minimal entry point that wires the core modules together.
Run as: python -m src.main
"""

from __future__ import annotations

import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aims")


def main() -> None:
    from src.skills.registry import SkillRegistry
    from src.gateway.router import GatewayRouter
    from src.runtime.executor import SkillRuntime

    # Wire modules
    registry = SkillRegistry()
    runtime = SkillRuntime()
    router = GatewayRouter(registry=registry, executor=runtime.execute)

    # Health check
    report = registry.health_report()
    logger.info("AIMS registry status: %s (%d manifests)", report["status"], report["manifest_count"])
    for name in report["manifest_names"]:
        logger.info("  loaded: %s", name)

    print(f"\nAIMS v0.1.0 — {report['manifest_count']} skill(s) loaded")
    print("Ready. Route prompts through GatewayRouter.route().")


if __name__ == "__main__":
    main()
