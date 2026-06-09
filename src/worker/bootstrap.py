"""Dynamic Skill Bootstrap — fetches and executes logic.py from the AIMS Gateway.

Workers use this module to load dynamically uploaded skills at runtime.
The bootstrap flow:

  1. Fetch ``logic.py`` source from ``GET /api/skills/{skill_id}/logic``
  2. Compile and load the source as a Python module via ``importlib``
  3. Call ``module.execute(payload)`` with the task's payload dict
  4. Return the result dict

Usage::

    from src.worker.bootstrap import execute_dynamic_skill

    result = execute_dynamic_skill(
        gateway_url="https://aims-gateway.fly.dev",
        skill_id="my_skill",
        payload={"query": "hello"},
        worker_id="worker-001",
    )
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import tempfile
from typing import Any

import requests

from src.worker.utils.signer import sign_headers

logger = logging.getLogger(__name__)


def fetch_logic(gateway_url: str, skill_id: str, worker_id: str) -> str:
    """Fetch ``logic.py`` source from the gateway.

    Returns the raw Python source string.

    Raises ``requests.RequestException`` on HTTP errors.
    """
    url = f"{gateway_url.rstrip('/')}/api/skills/{skill_id}/logic"
    headers = sign_headers(None, worker_id)
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def _load_and_execute(source: str, module_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Compile *source* as a module and call ``execute(payload)``.

    The module is loaded into a temporary file, executed, and cleaned up.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, prefix=f"aims_{module_name}_",
    ) as f:
        f.write(source)
        temp_path = f.name

    try:
        spec = importlib.util.spec_from_file_location(module_name, temp_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not create module spec for {module_name}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, "execute"):
            raise ValueError(f"Skill '{module_name}' has no execute() function")

        result = module.execute(payload)
        if not isinstance(result, dict):
            raise ValueError(f"execute() must return a dict, got {type(result).__name__}")
        return result
    finally:
        os.unlink(temp_path)
        sys.modules.pop(module_name, None)


def execute_dynamic_skill(
    gateway_url: str,
    skill_id: str,
    payload: dict[str, Any],
    worker_id: str,
) -> dict[str, Any]:
    """Fetch, load, and execute a dynamic skill from the gateway.

    Args:
        gateway_url: Base URL of the AIMS Gateway (e.g. ``http://localhost:9876``).
        skill_id: The skill identifier (matches the manifest ``name``).
        payload: Input arguments passed to the skill's ``execute()`` function.
        worker_id: Worker identifier used for HMAC-signed requests.

    Returns:
        The dict returned by the skill's ``execute()``.

    Raises:
        ``requests.RequestException`` if the fetch fails.
        ``ValueError`` if the skill has no ``execute()`` function.
        ``ImportError`` if the module cannot be loaded.
    """
    source = fetch_logic(gateway_url, skill_id, worker_id)
    module_name = f"aims_dynamic_{skill_id.replace('-', '_')}"
    return _load_and_execute(source, module_name, payload)
