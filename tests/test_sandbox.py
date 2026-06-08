"""Tests for WorkflowEngine sandbox execution."""
import json
from src.skills.manifest import SkillManifest
from src.runtime.sandbox import WorkflowEngine, ExecutionReceipt


def dummy_executor(manifest: SkillManifest, arguments: dict) -> str:
    """Simple executor that returns a canned response."""
    return json.dumps({"status": "ok", "input": arguments})


def failing_executor(manifest: SkillManifest, arguments: dict) -> str:
    raise RuntimeError("simulated failure")


class TestWorkflowEngine:
    def setup_method(self):
        self.engine = WorkflowEngine(dummy_executor)
        self.manifest = SkillManifest(
            name="test_skill",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            author="test",
        )

    def test_execute_success(self):
        receipt = self.engine.execute(self.manifest, {"q": "hello"})
        assert receipt.status == "SUCCESS"
        assert receipt.skill_name == "test_skill"
        assert receipt.compute_consumed > 0
        assert receipt.execution_time > 0
        data = json.loads(receipt.output)
        assert data["status"] == "ok"

    def test_execute_with_error(self):
        engine = WorkflowEngine(failing_executor)
        receipt = engine.execute(self.manifest, {})
        assert receipt.status == "FAILED"
        assert "RuntimeError" in receipt.error_message
        assert receipt.compute_consumed > 0

    def test_receipt_output_string(self):
        receipt = self.engine.execute(self.manifest, {})
        assert isinstance(receipt.output, str)

    def test_failed_receipt_empty_output(self):
        engine = WorkflowEngine(failing_executor)
        receipt = engine.execute(self.manifest, {})
        assert receipt.output == ""

    def test_output_schema_validation_passes(self):
        manifest = SkillManifest(
            name="validated_skill",
            description="With output schema",
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["status"]},
            author="test",
        )
        receipt = self.engine.execute(manifest, {})
        assert receipt.status == "SUCCESS"

    def test_invalid_output_fails_validation(self):
        def bad_executor(manifest, args):
            return "not json at all"

        engine = WorkflowEngine(bad_executor)
        manifest = SkillManifest(
            name="bad_output",
            description="Bad output for schema",
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["status"]},
            author="test",
        )
        receipt = engine.execute(manifest, {})
        assert receipt.status == "FAILED"

    def test_no_output_schema_skips_validation(self):
        def executor(manifest, args):
            return "any string is fine"

        engine = WorkflowEngine(executor)
        manifest = SkillManifest(
            name="no_schema",
            description="No output schema",
            input_schema={"type": "object"},
            output_schema=None,
            author="test",
        )
        receipt = engine.execute(manifest, {})
        assert receipt.status == "SUCCESS"

    def test_string_output_validator(self):
        manifest = SkillManifest(
            name="string_output",
            description="String output",
            input_schema={"type": "object"},
            output_schema={"type": "string"},
            author="test",
        )
        receipt = self.engine.execute(manifest, {})
        assert receipt.status == "SUCCESS"

    def test_execution_time_measured(self):
        receipt = self.engine.execute(self.manifest, {})
        assert receipt.execution_time > 0.0  # wall-clock time
        assert receipt.compute_consumed > 0.0  # perf counter
