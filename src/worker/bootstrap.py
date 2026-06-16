"""Dynamic Skill Bootstrap — fetches and executes logic.py from the AIMS Gateway.

Workers use this module to load dynamically uploaded skills at runtime.
Includes multimodal input preprocessing (base64 binary, URL download).

The bootstrap flow:

  1. Preprocess payload for multimodal inputs (base64 decode, URL download)
  2. Fetch ``logic.py`` source from ``GET /api/skills/{skill_id}/logic``
  3. Compile and load the source as a Python module via ``importlib``
  4. Call ``module.execute(payload)`` with the task's payload dict
  5. Return the result dict

Usage::

    from src.worker.bootstrap import execute_dynamic_skill

    result = execute_dynamic_skill(
        gateway_url="https://api.aimsgateway.com",
        skill_id="my_skill",
        payload={"query": "hello", "image": "data:image/png;base64,..."},
        worker_id="worker-001",
    )
"""

from __future__ import annotations

import base64
import importlib.util
import logging
import os
import re
import sys
import tempfile
import urllib.request
from typing import Any

import requests

from src.worker.utils.signer import sign_headers

logger = logging.getLogger(__name__)


# ── Multimodal preprocessing ──────────────────────────────────────────────


def _detect_base64(value: str) -> bytes | None:
    """Detect and decode base64-encoded binary data.

    Returns decoded bytes if *value* looks like base64 (>20 chars, valid
    base64 alphabet, decodes to ≥16 bytes).  Returns ``None`` for short
    or non-base64 strings.
    """
    if len(value) < 20:
        return None
    b64_pattern = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
    if not b64_pattern.match(value):
        return None
    try:
        decoded = base64.b64decode(value)
        if len(decoded) >= 16:
            return decoded
    except Exception:
        pass
    return None


def _detect_url(value: str) -> str | None:
    """Detect if *value* is a downloadable URL (http/https/file).

    Returns the URL string or ``None``.
    """
    if not isinstance(value, str):
        return None
    if value.startswith(('http://', 'https://', 'file://')):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.netloc or value.startswith('file://'):
            return value
    return None


def _download_to_temp(url: str) -> tuple[str, str]:
    """Download *url* content to a temporary file.

    Returns ``(file_path, mime_type)``.
    """
    _, ext = os.path.splitext(url.split('?')[0].split('#')[0])
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
        '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
        '.mp4': 'video/mp4', '.pdf': 'application/pdf',
    }
    mime_type = mime_map.get(ext.lower(), 'application/octet-stream')

    with tempfile.NamedTemporaryFile(
        suffix=ext if ext else '.bin', delete=False, prefix='aims_modal_',
    ) as f:
        with urllib.request.urlopen(url, timeout=30) as resp:
            f.write(resp.read())
        temp_path = f.name

    return temp_path, mime_type


def preprocess_multimodal(payload: dict[str, Any]) -> dict[str, Any]:
    """Scan payload values for multimodal inputs and preprocess them.

    Detected patterns:
      - **Base64-encoded binary** (image, audio, etc.) → decoded to temp file
      - **Downloadable URLs** (http/https/file) → downloaded to temp file

    Matching values are replaced with a metadata dict::

        {"_type": "file", "path": "...", "mime_type": "...", "size_bytes": N}

    Non-matching values pass through unchanged.
    """
    processed = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            processed[key] = value
            continue

        # Check for downloadable URL
        url = _detect_url(value)
        if url:
            file_path, mime_type = _download_to_temp(url)
            processed[key] = {
                "_type": "file",
                "path": file_path,
                "mime_type": mime_type,
                "original_url": url,
            }
            logger.info(
                "MULTIMODAL: Downloaded %s → %s (mime=%s)", url, file_path, mime_type,
            )
            continue

        # Check for base64-encoded binary
        decoded = _detect_base64(value)
        if decoded:
            ext = '.bin'
            if decoded.startswith(b'\x89PNG'):
                ext = '.png'
            elif decoded.startswith(b'\xff\xd8'):
                ext = '.jpg'
            elif decoded.startswith(b'GIF8'):
                ext = '.gif'
            elif decoded.startswith(b'RIFF'):
                ext = '.webp'

            with tempfile.NamedTemporaryFile(
                suffix=ext, delete=False, prefix='aims_modal_',
            ) as f:
                f.write(decoded)
                file_path = f.name

            mime_map = {
                '.png': 'image/png', '.jpg': 'image/jpeg',
                '.gif': 'image/gif', '.webp': 'image/webp',
            }
            processed[key] = {
                "_type": "file",
                "path": file_path,
                "mime_type": mime_map.get(ext, 'application/octet-stream'),
                "size_bytes": len(decoded),
            }
            logger.info(
                "MULTIMODAL: Decoded base64 → %s (mime=%s, %d bytes)",
                file_path, processed[key]["mime_type"], len(decoded),
            )
            continue

        processed[key] = value

    return processed


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

    Payload values are preprocessed for multimodal inputs: base64-encoded
    binary data is decoded to temp files, downloadable URLs are fetched
    and saved locally, and the original values are replaced with file
    metadata dicts before passing to the skill's ``execute()``.

    Args:
        gateway_url: Base URL of the AIMS Gateway.
        skill_id: The skill identifier (matches the manifest ``name``).
        payload: Input arguments passed to the skill's ``execute()``.
            String values are scanned for base64 binary and downloadable
            URLs and preprocessed automatically.
        worker_id: Worker identifier used for HMAC-signed requests.

    Returns:
        The dict returned by the skill's ``execute()``.
    """
    payload = preprocess_multimodal(payload)
    source = fetch_logic(gateway_url, skill_id, worker_id)
    module_name = f"aims_dynamic_{skill_id.replace('-', '_')}"
    return _load_and_execute(source, module_name, payload)
