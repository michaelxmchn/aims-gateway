"""Skill Store — Dynamic skill upload, storage, and retrieval (Layer 3.5).

Handles zip-based skill uploads, manifest validation, and persistence of
``logic.py`` to the local filesystem.  Works alongside ``SkillRegistry``
to make dynamically uploaded skills available for execution.

Lifecycle:
  1. User uploads a zip containing ``manifest.json`` + ``logic.py``
  2. SkillStore validates the archive structure
  3. ``manifest.json`` is stored in Redis, ``logic.py`` is written to disk
  4. Workers fetch ``logic.py`` via ``GET /api/skills/{skill_id}/logic``
  5. Workers load and execute the logic dynamically (bootstrap.py)
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

SKILL_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")
"""Valid skill_id: letter-start, 2-64 chars, alphanumeric/underscore/dash."""

UPLOAD_BASE = Path(__file__).resolve().parent.parent.parent / "skills" / "uploaded"
"""All uploaded skill files land under ``skills/uploaded/{skill_id}/``."""

MANIFEST_NS = "skill:manifest"
"""Redis namespace for uploaded manifest metadata."""

MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10 MB
"""Maximum allowed zip upload size."""


class SkillStoreError(Exception):
    """Raised when a skill-store operation fails."""


class SkillStore:
    """Persistent store for dynamically uploaded skills.

    Stores manifest metadata in Redis and ``logic.py`` on the local
    filesystem.  Provides methods for installation, lookup, and
    source-code retrieval.
    """

    def __init__(self, storage: Storage, base_dir: str | Path = UPLOAD_BASE) -> None:
        self._storage = storage
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ── Install ──────────────────────────────────────────────────────────

    def install_zip(self, zip_bytes: bytes, author: str = "") -> dict[str, Any]:
        """Validate, extract, and install a skill from a zip archive.

        Expected archive layout::

            manifest.json     — required, valid ``SkillManifest`` JSON
            logic.py          — required, entry point with ``def execute(payload: dict) -> dict``

        Returns a dict with ``skill_id``, ``name``, and ``version`` on
        success.
        """
        if len(zip_bytes) > MAX_ZIP_SIZE:
            raise SkillStoreError(f"Zip exceeds maximum size of {MAX_ZIP_SIZE // 1024 // 1024} MB")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                    # Prevent zip-slip path traversal
                    for entry in zf.infolist():
                        dest = (tmp / entry.filename).resolve()
                        if not str(dest).startswith(str(tmp.resolve())):
                            raise SkillStoreError(f"Zip-slip detected: {entry.filename}")
                    zf.extractall(tmp)
            except zipfile.BadZipFile:
                raise SkillStoreError("Invalid zip archive")

            manifest_path = tmp / "manifest.json"
            logic_path = tmp / "logic.py"

            if not manifest_path.exists():
                raise SkillStoreError("Missing manifest.json in zip root")
            if not logic_path.exists():
                raise SkillStoreError("Missing logic.py in zip root")

            # Validate manifest JSON
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SkillStoreError(f"Invalid manifest.json: {exc}")

            name = raw.get("name", "")
            if not SKILL_ID_PATTERN.match(name):
                raise SkillStoreError(
                    f"Invalid skill name {name!r}: must match {SKILL_ID_PATTERN.pattern}"
                )

            # Set author if not present in manifest
            raw.setdefault("author", author or "unknown")

            # Validate via SkillManifest (do NOT store the Pydantic model,
            # store the raw dict for Redis — matches how SkillRegistry loads)
            from src.skills.manifest import SkillManifest
            try:
                SkillManifest.model_validate(raw)
            except Exception as exc:
                raise SkillStoreError(f"Manifest validation failed: {exc}")

            skill_id = name
            dest_dir = self._base_dir / skill_id

            if dest_dir.exists():
                logger.warning("Overwriting existing uploaded skill '%s'", skill_id)
                shutil.rmtree(dest_dir)

            # Copy files to permanent home
            dest_dir.mkdir(parents=True)
            shutil.copy2(manifest_path, dest_dir / "manifest.json")
            shutil.copy2(logic_path, dest_dir / "logic.py")

            # Store manifest metadata in Redis
            self._storage.dict_set(MANIFEST_NS, skill_id, raw)

            logger.info(
                "INSTALL skill '%s' v%s — %s",
                skill_id, raw.get("version", "?"), raw.get("description", "")[:60],
            )

            return {"skill_id": skill_id, "name": name, "version": raw.get("version", "1.0.0")}

    # ── Lookup ───────────────────────────────────────────────────────────

    def get_manifest(self, skill_id: str) -> Optional[dict[str, Any]]:
        """Return the manifest dict for an uploaded skill, or ``None``."""
        raw = self._storage.dict_get(MANIFEST_NS, skill_id)
        if raw is None:
            return None
        return raw if isinstance(raw, dict) else None

    def get_logic_path(self, skill_id: str) -> Optional[Path]:
        """Return the ``Path`` to ``logic.py`` for *skill_id*, or ``None``."""
        candidate = self._base_dir / skill_id / "logic.py"
        return candidate if candidate.exists() else None

    def get_logic_source(self, skill_id: str) -> Optional[str]:
        """Return the Python source of ``logic.py`` for *skill_id*, or ``None``."""
        path = self.get_logic_path(skill_id)
        if path is None:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read logic.py for '%s': %s", skill_id, exc)
            return None

    def list_skills(self) -> list[str]:
        """Return all uploaded skill IDs."""
        return self._storage.dict_keys(MANIFEST_NS) or []

    # ─── Delete ──────────────────────────────────────────────────────────

    def remove_skill(self, skill_id: str) -> bool:
        """Remove an uploaded skill from Redis and disk.

        Returns ``True`` if the skill existed and was removed.
        """
        manifest = self.get_manifest(skill_id)
        if manifest is None:
            return False

        self._storage.dict_delete(MANIFEST_NS, skill_id)

        dest_dir = self._base_dir / skill_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)

        logger.info("REMOVE skill '%s'", skill_id)
        return True

    # ── Registry integration ─────────────────────────────────────────────

    def load_into_registry(self, registry: Any) -> None:
        """Load all uploaded skills into a ``SkillRegistry``.

        Calls ``registry.install_skill()`` for each uploaded skill so the
        registry can serve them alongside static manifests.
        """
        for skill_id in self.list_skills():
            raw = self.get_manifest(skill_id)
            if raw is None:
                continue
            logic_path = self.get_logic_path(skill_id)
            if logic_path is None:
                continue
            try:
                registry.install_skill(skill_id, raw, str(logic_path))
                logger.debug("Loaded uploaded skill '%s' into registry", skill_id)
            except Exception as exc:
                logger.warning("Failed to load uploaded skill '%s': %s", skill_id, exc)
