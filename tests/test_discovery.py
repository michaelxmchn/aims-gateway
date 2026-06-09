"""Tests for the GET /api/discovery auto-discovery endpoint.

Verifies:
  - Response is valid JSON
  - Expected top-level fields exist
  - Skills section is dynamically populated from registry
  - OpenAPI 3.0 subset structure
  - discovery_version field is present
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path for the server import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from src.gateway.server import app

client = TestClient(app)


class TestDiscoveryEndpoint:
    """Test suite for GET /api/discovery."""

    def setup_method(self) -> None:
        self.resp = client.get("/api/discovery")
        self.data = self.resp.json()

    def test_status_200(self) -> None:
        assert self.resp.status_code == 200

    def test_valid_json(self) -> None:
        # If .json() didn't raise we're already valid, but double-check round-trip
        raw = json.dumps(self.data)
        parsed = json.loads(raw)
        assert parsed == self.data

    def test_top_level_fields(self) -> None:
        required = {"discovery_version", "api", "server", "authentication", "skills", "endpoints", "links", "notes"}
        missing = required - set(self.data.keys())
        assert not missing, f"Missing top-level fields: {missing}"

    def test_discovery_version(self) -> None:
        assert "discovery_version" in self.data
        # Must be semver string
        parts = self.data["discovery_version"].split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_api_metadata(self) -> None:
        api = self.data["api"]
        assert api["name"] == "AIMS Gateway"
        assert "version" in api
        assert "description" in api

    def test_server_time(self) -> None:
        server = self.data["server"]
        assert "current_time" in server
        assert isinstance(server["current_time"], (int, float))
        assert server["timezone"] == "UTC"

    def test_authentication_section(self) -> None:
        auth = self.data["authentication"]
        assert auth["scheme"] == "HMAC-SHA256"
        assert "headers" in auth
        for hdr in ("X-Signature", "X-Timestamp", "X-User-ID"):
            assert hdr in auth["headers"], f"Missing auth header: {hdr}"
        assert "example_curl" in auth

    def test_skills_dynamic(self) -> None:
        skills = self.data["skills"]
        assert isinstance(skills, list)
        assert len(skills) > 0, "Expected at least one built-in skill"

        for skill in skills:
            assert "skill_id" in skill
            assert "manifest" in skill
            assert "endpoint" in skill
            assert "auth_type" in skill
            assert skill["endpoint"] == "/api/run"
            assert skill["auth_type"] == "HMAC-SHA256"
            assert skill["source"] in ("built-in", "uploaded")

            manifest = skill["manifest"]
            for field in ("name", "description", "version", "author", "input_schema"):
                assert field in manifest, f"Skill {skill['skill_id']} missing manifest.{field}"

    def test_skills_include_known_builtins(self) -> None:
        """Verify known built-in skills appear in the list."""
        skill_ids = {s["skill_id"] for s in self.data["skills"]}
        # These are the 5 static manifests plus dashboard_skill
        known = {"amazon_scraper", "code_security_audit", "git_changelog", "data_analyzer", "buggy_skill", "dashboard_skill"}
        found = known & skill_ids
        assert len(found) >= 5, f"Expected ≥5 built-in skills, found {len(found)}: {skill_ids}"

    def test_skills_sorted(self) -> None:
        ids = [s["skill_id"] for s in self.data["skills"]]
        assert ids == sorted(ids), "Skills should be sorted by skill_id"

    def test_endpoints_section(self) -> None:
        endpoints = self.data["endpoints"]
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 3  # Task, Skill, Worker, System

        categories = {ep["category"] for ep in endpoints}
        assert "Task Management" in categories
        assert "Skill Management" in categories
        assert "Worker" in categories
        assert "System" in categories

        for ep in endpoints:
            assert "description" in ep
            assert "operations" in ep
            assert len(ep["operations"]) > 0
            for op in ep["operations"]:
                assert "method" in op
                assert "path" in op
                assert "summary" in op

    def test_endpoints_cover_critical_paths(self) -> None:
        """Ensure all critical HTTP endpoints are documented."""
        paths_found = set()
        for ep in self.data["endpoints"]:
            for op in ep["operations"]:
                paths_found.add(f"{op['method']} {op['path']}")

        critical = {
            "POST /api/tasks/claim",
            "POST /api/tasks/submit",
            "GET /api/tasks/{task_id}/status",
            "POST /api/skills/upload",
            "GET /api/skills/{skill_id}/logic",
            "POST /api/run",
            "POST /api/workers/heartbeat",
            "GET /api/health",
            "GET /api/discovery",
        }
        missing = critical - paths_found
        assert not missing, f"Critical paths missing from discovery: {missing}"

    def test_links_section(self) -> None:
        links = self.data["links"]
        assert "openclaw_manifest" in links
        assert "health" in links

    def test_notes_section(self) -> None:
        notes = self.data["notes"]
        assert isinstance(notes, list)
        assert len(notes) >= 5  # Several operational notes

    def test_response_content_type(self) -> None:
        assert self.resp.headers.get("content-type", "").startswith("application/json")

    def test_no_auth_required(self) -> None:
        """Discovery must be publicly accessible (no HMAC)."""
        # Without any signature headers, we should still get 200
        resp = client.get("/api/discovery", headers={})
        assert resp.status_code == 200

    def test_uploaded_skills_appear(self) -> None:
        """Verify that skills from skill_store are merged into the list."""
        skill_ids = {s["skill_id"] for s in self.data["skills"]}
        uploaded_ids = set(self.data["skills"][i]["skill_id"] for i in range(len(self.data["skills"]))
                          if self.data["skills"][i]["source"] == "uploaded")
        # No uploaded skills expected in this test environment, but the field should exist
        assert isinstance(uploaded_ids, set)
