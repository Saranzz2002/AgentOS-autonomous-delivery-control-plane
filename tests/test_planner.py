from __future__ import annotations

import json

import pytest

from backend.agents.planner import PlannerError, generate_plan


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def valid_plan(**overrides):
    plan = {
        "goal": "Add a health endpoint",
        "assumptions": [],
        "files_to_inspect": [{"path": "app/main.py", "reason": "Existing API entry point."}],
        "files_to_modify": [],
        "files_to_create": [{"path": "tests/test_health.py", "reason": "Add endpoint coverage."}],
        "implementation_steps": [{"step": 1, "description": "Inspect route setup."}],
        "testing_strategy": ["Test the response body."],
        "risks": [],
        "dependencies": [],
    }
    plan.update(overrides)
    return json.dumps(plan)


def test_plan_is_validated_against_schema():
    result = generate_plan({"context": "Task and repository context"}, FakeLLM([valid_plan()]))
    assert result["plan"]["goal"] == "Add a health endpoint"
    assert result["plan"]["files_to_create"][0]["path"] == "tests/test_health.py"


def test_malformed_plan_gets_one_correction_retry():
    llm = FakeLLM(["not json", valid_plan()])
    result = generate_plan({"context": "Task and repository context"}, llm)
    assert llm.calls == 2
    assert result["status"] == "planned"


def test_plan_rejects_path_traversal():
    llm = FakeLLM([valid_plan(files_to_create=[{"path": "../outside.py", "reason": "escape"}])])
    with pytest.raises(PlannerError, match="outside the repository"):
        generate_plan({"context": "Task and repository context"}, llm)
