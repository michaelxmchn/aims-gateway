"""DAG Engine — Layer 3.

Serial orchestration of tool calls returned by the LLM.
MVP only supports linear (1→2→3) execution; parallel scheduling
is deferred to post-MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.skills.manifest import SkillManifest

SkillExecutor = Callable[[SkillManifest, Dict[str, Any]], str]


@dataclass
class DAGPlan:
    """A linear DAG of skill steps to execute in order."""

    steps: List["DAGStep"] = field(default_factory=list)


@dataclass
class DAGStep:
    """A single node in the execution plan."""

    skill_name: str
    manifest: SkillManifest
    arguments: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)


@dataclass
class DAGResult:
    """The result of executing a DAGPlan."""

    step_results: Dict[str, str] = field(default_factory=dict)
    step_errors: Dict[str, str] = field(default_factory=dict)


class DAGEngine:
    """Serial skill orchestrator.

    For MVP, steps execute in declaration order. If step B lists A in
    ``depends_on`` and A's result should feed into B's arguments, the
    caller is responsible for stitching — this engine only guarantees
    serial in-order execution.
    """

    def __init__(self, executor: SkillExecutor) -> None:
        self._executor = executor

    def run(self, plan: DAGPlan) -> DAGResult:
        result = DAGResult()
        for step in plan.steps:
            try:
                output = self._executor(step.manifest, step.arguments)
                result.step_results[step.skill_name] = output
            except Exception as exc:
                result.step_errors[step.skill_name] = str(exc)
                break  # serial fail-fast
        return result
