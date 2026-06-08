"""Tests for SkillManifest Pydantic model."""
from src.skills.manifest import SkillManifest, to_anthropic_tool_def, to_openai_tool_def


class TestSkillManifest:
    def test_minimal_valid(self):
        m = SkillManifest(
            name="test_skill",
            description="A test skill",
            input_schema={"type": "object", "properties": {}},
            author="test_author",
        )
        assert m.name == "test_skill"
        assert m.version == "1.0.0"
        assert m.price_points == 0
        assert m.staked_points == 0.0
        assert not m.is_frozen()

    def test_name_pattern_valid(self):
        m = SkillManifest(
            name="my_cool-skill_42",
            description="Pattern test",
            input_schema={"type": "object"},
            author="dev",
        )
        assert m.name == "my_cool-skill_42"

    def test_name_pattern_invalid(self):
        import pytest
        with pytest.raises(Exception):
            SkillManifest(
                name="bad name!",
                description="Bad name",
                input_schema={"type": "object"},
                author="dev",
            )

    def test_input_schema_must_have_type(self):
        import pytest
        with pytest.raises(Exception, match="input_schema must have a top-level 'type'"):
            SkillManifest(
                name="bad_schema",
                description="No type field",
                input_schema={"properties": {}},
                author="dev",
            )

    def test_is_frozen(self):
        import time
        m = SkillManifest(
            name="frozen_skill",
            description="Frozen for testing",
            input_schema={"type": "object"},
            author="dev",
            frozen_until=time.time() + 86400,
        )
        assert m.is_frozen()
        assert not m.is_frozen(now=time.time() + 172800)

    def test_price_points_ge_zero(self):
        import pytest
        with pytest.raises(Exception):
            SkillManifest(
                name="neg_price",
                description="Negative price",
                input_schema={"type": "object"},
                author="dev",
                price_points=-1,
            )

    def test_anthropic_tool_def(self):
        m = SkillManifest(
            name="test_tool",
            description="Tool description",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            author="dev",
        )
        t = to_anthropic_tool_def(m)
        assert t["name"] == "test_tool"
        assert t["description"] == "Tool description"
        assert t["input_schema"]["type"] == "object"

    def test_openai_tool_def(self):
        m = SkillManifest(
            name="test_oa",
            description="OA tool",
            input_schema={"type": "object"},
            author="dev",
        )
        t = to_openai_tool_def(m)
        assert t["type"] == "function"
        assert t["function"]["name"] == "test_oa"
