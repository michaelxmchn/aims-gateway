"""Tests for SkillRegistry — domain detection, priority scoring, jail."""
import time
from pathlib import Path
from src.skills.registry import SkillRegistry, detect_domain


class TestDomainDetection:
    def test_security_domain(self):
        assert detect_domain("audit this Solidity contract for exploits") == "security"

    def test_git_domain(self):
        assert detect_domain("show me the git changelog from last branch") == "git"

    def test_code_domain(self):
        assert detect_domain("review my code and refactor the function") == "code"

    def test_data_domain(self):
        assert detect_domain("scrape Amazon for data analysis query") == "data"

    def test_general_domain(self):
        assert detect_domain("hello, how are you?") == "general"


class TestSkillRegistry:
    def test_load_all_returns_dict(self):
        reg = SkillRegistry()
        manifests = reg.load_all()
        assert isinstance(manifests, dict)

    def test_count_skills(self):
        reg = SkillRegistry()
        assert reg.count >= 5  # at least 5 seed manifests

    def test_get_known_skill(self):
        reg = SkillRegistry()
        m = reg.get("amazon_scraper")
        assert m is not None
        assert m.name == "amazon_scraper"

    def test_get_unknown_skill(self):
        reg = SkillRegistry()
        assert reg.get("nonexistent_skill") is None

    def test_get_all_manifests(self):
        reg = SkillRegistry()
        all_m = reg.get_all_manifests()
        assert len(all_m) == reg.count

    def test_priority_score_default(self):
        reg = SkillRegistry()
        score = reg.get_priority_score("amazon_scraper")
        # Default: freq=0 + staked=0 => 0
        assert score >= 0.0

    def test_priority_score_with_frequency(self):
        reg = SkillRegistry()
        reg.record_execution("amazon_scraper", success=True)
        score = reg.get_priority_score("amazon_scraper")
        assert score >= 1.0  # freq at least 1

    def test_priority_breakdown(self):
        reg = SkillRegistry()
        bd = reg.get_priority_breakdown("amazon_scraper")
        assert "priority_score" in bd
        assert "usage_frequency" in bd
        assert "staked_points" in bd

    def test_record_execution_success_resets_failures(self):
        reg = SkillRegistry()
        reg.record_execution("test_fail_reset", success=False)
        reg.record_execution("test_fail_reset", success=True)
        event = reg.record_execution("test_fail_reset", success=True)
        assert event["consecutive_failures"] == 0

    def test_consecutive_failures_count(self):
        reg = SkillRegistry()
        # After 2 failures (no jail yet)
        reg.record_execution("test_consecutive_1", success=False)
        event = reg.record_execution("test_consecutive_1", success=False)
        assert event["consecutive_failures"] == 2

    def test_get_rules_known_skill(self):
        reg = SkillRegistry()
        rules = reg.get_rules("amazon_scraper")
        assert rules is not None
        assert len(rules) > 0

    def test_get_rules_unknown_skill(self):
        reg = SkillRegistry()
        assert reg.get_rules("nonexistent") is None

    def test_health_report(self):
        reg = SkillRegistry()
        report = reg.health_report()
        assert report["status"] in ("healthy", "empty")
        assert "manifest_count" in report
        assert "manifest_names" in report
