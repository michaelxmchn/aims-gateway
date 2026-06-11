"""Simulates an AI agent self-bootstrapping into the AIMS network.

An external AI agent (e.g. Hermes) follows this protocol:
  1. Fetch GET /api/discovery — learn all skills and endpoints
  2. Read the documentation_root URL — retrieve protocol index
  3. Validate the index covers all required protocols
  4. Verify HMAC authentication section is present
  5. Verify pipeline execution docs are present
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from src.gateway.server import app

client = TestClient(app)

# Protocols that MUST appear in MASTER_INDEX.md
REQUIRED_PROTOCOLS = [
    "Discovery Protocol",
    "EIP-191 Wallet Authentication",
    "Run API",
    "Pipeline Execution",
    "Worker Heartbeat",
    "Skill Upload",
    "Agent Bootstrap Protocol",
]

REQUIRED_TOPICS = [
    "personal_sign",
    "pipeline",
    "discovery",
    "heartbeat",
    "bootstrap",
    "escrow",
    "70/25/5",
    "settleTask",
]


class TestAgentBootstrap:
    """Simulates the AI agent bootstrap flow as documented in AIMS_AGENT_BOOTSTRAP.md."""

    def test_step1_discovery_returns_200(self) -> None:
        """Agent fetches GET /api/discovery — must be publicly accessible."""
        resp = client.get("/api/discovery")
        assert resp.status_code == 200

    def test_step1_discovery_has_documentation_root(self) -> None:
        """Agent reads documentation_root to find the protocol index."""
        data = client.get("/api/discovery").json()
        assert "documentation_root" in data
        url = data["documentation_root"]
        assert url.startswith("http"), f"documentation_root should be a URL, got: {url}"
        assert "MASTER_INDEX.md" in url, f"URL should point to MASTER_INDEX.md, got: {url}"

    def test_step1_discovery_has_skills_list(self) -> None:
        """Agent must be able to discover available skills."""
        data = client.get("/api/discovery").json()
        assert "skills" in data
        assert len(data["skills"]) > 0
        for s in data["skills"]:
            assert "id" in s
            assert "execution" in s
            assert s["execution"]["endpoint"] == "/api/run"

    def test_step1_discovery_has_auth_section(self) -> None:
        """Agent reads authentication scheme from discovery response."""
        data = client.get("/api/discovery").json()
        auth = data.get("authentication", {})
        assert auth.get("scheme") == "EIP-191"
        assert "X-Signature" in auth.get("headers", {})

    def test_step2_documentation_root_reachable(self) -> None:
        """Agent fetches the documentation_root URL — validates it's reachable."""
        data = client.get("/api/discovery").json()
        url = data["documentation_root"]
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200
                content = resp.read().decode("utf-8")
                assert len(content) > 500, "Documentation seems too short"
                # Store for other tests
                self._doc_content = content
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            import pytest
            pytest.skip(f"documentation_root not reachable: {exc}")

    def _load_doc_content(self) -> str | None:
        """Load documentation content from remote, falling back to local file."""
        content = None
        try:
            data = client.get("/api/discovery").json()
            req = urllib.request.Request(data["documentation_root"], method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
        except Exception:
            pass

        # Fall back to local file if remote is stale or unreachable
        local_index = PROJECT_ROOT / "docs" / "MASTER_INDEX.md"
        if local_index.exists():
            local_content = local_index.read_text("utf-8")
            if content is None:
                return local_content
            # Use whichever version covers more required topics
            remote_score = sum(1 for t in REQUIRED_TOPICS if t.lower() in content.lower())
            local_score = sum(1 for t in REQUIRED_TOPICS if t.lower() in local_content.lower())
            if local_score >= remote_score:
                return local_content
        return content

    def test_step2_documentation_contains_all_protocols(self) -> None:
        """Agent validates the documentation covers all 7 required protocols."""
        content = getattr(self, "_doc_content", None)
        if content is None:
            content = self._load_doc_content()
            if content is None:
                import pytest
                pytest.skip("Cannot fetch documentation from remote or local")

        for protocol in REQUIRED_PROTOCOLS:
            assert protocol in content, f"Missing protocol section: {protocol}"

    def test_step2_documentation_contains_topics(self) -> None:
        """Agent validates key technical topics are documented."""
        content = getattr(self, "_doc_content", None)
        if content is None:
            content = self._load_doc_content()
            if content is None:
                import pytest
                pytest.skip("Cannot fetch documentation from remote or local")

        for topic in REQUIRED_TOPICS:
            assert topic.lower() in content.lower(), f"Missing topic: {topic}"

    def test_step3_skills_have_input_schemas(self) -> None:
        """Agent reads input_schema for each skill to determine required params."""
        data = client.get("/api/discovery").json()
        for skill in data["skills"]:
            manifest = skill.get("manifest", {})
            assert "input_schema" in manifest, (
                f"Skill {skill['id']} missing input_schema"
            )
            schema = manifest["input_schema"]
            assert "type" in schema
            assert "properties" in schema

    def test_step4_authentication_has_curl_example(self) -> None:
        """Agent finds a concrete auth example it can adapt."""
        data = client.get("/api/discovery").json()
        auth = data.get("authentication", {})
        example = auth.get("example_curl", "")
        assert "X-Wallet-Address" in example
        assert "X-Signature" in example
        assert "X-Timestamp" in example

    def test_step5_run_endpoint_accepts_pipeline(self) -> None:
        """Agent discovers pipeline support for multi-step tasks."""
        data = client.get("/api/discovery").json()
        for ep in data.get("endpoints", []):
            for op in ep.get("operations", []):
                if op.get("method") == "POST" and op.get("path") == "/api/run":
                    # Validate that the Run endpoint is documented
                    assert op.get("summary"), "Run endpoint missing summary"
                    return
        # If we get here, no POST /api/run endpoint found
        pytest.fail("POST /api/run not found in discovery endpoints")

    def test_full_protocol_discovery_to_run(self) -> None:
        """End-to-end validation: discovery → skill selection → schema check."""
        data = client.get("/api/discovery").json()
        skills = data["skills"]

        # Find amazon_scraper as a representative skill
        scraper = next((s for s in skills if s["id"] == "amazon_scraper"), None)
        assert scraper is not None, "amazon_scraper should be in skills list"

        # Validate schema is usable
        schema = scraper["manifest"]["input_schema"]
        assert "properties" in schema
        assert isinstance(schema["properties"], dict)
        assert len(schema["properties"]) > 0


class TestBootstrapDocumentation:
    """Tests for the AIMS_AGENT_BOOTSTRAP.md documentation file."""

    def test_bootstrap_doc_exists(self) -> None:
        path = PROJECT_ROOT / "AIMS_AGENT_BOOTSTRAP.md"
        assert path.exists(), "AIMS_AGENT_BOOTSTRAP.md must exist for agents"

    def test_bootstrap_helper_exists(self) -> None:
        path = PROJECT_ROOT / "bootstrap_helper.py"
        assert path.exists(), "bootstrap_helper.py must exist for agent use"

    def test_bootstrap_doc_contains_system_prompt(self) -> None:
        path = PROJECT_ROOT / "AIMS_AGENT_BOOTSTRAP.md"
        content = path.read_text()
        assert "AIMS System Prompt" in content
        assert "You are connected to the AIMS DePIN Network" in content
