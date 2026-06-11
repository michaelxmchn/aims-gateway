"""Test/Sandbox Skill — pure echo for DePIN pipeline smoke tests.

Accepts any input, echoes it back in a standard envelope.
Billing and output validation are bypassed for this skill.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def echo(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Echo the input params back in a standard envelope.

    Args:
        params: Arbitrary input data (may be None).

    Returns:
        Always returns ``{"status": "accepted", "echo": <params>}``.
    """
    result = {
        "status": "accepted",
        "echo": params or {},
    }
    logger.info("test_skill echo: %s", result)
    return result
