from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api import tasks as task_api
from backend.api.tasks import analyze_task, create_task, get_task, get_task_events, plan_task
from backend.models.schemas import TaskCreateRequest
from backend.services import repository_service


def test_task_api_create_analyze_plan_and_get(monkeypatch, python_repo):
    monkeypatch.setattr(repository_service.repository_service, "clone", lambda url, task_id: python_repo)
    monkeypatch.setattr(task_api, "planning_workflow", type("Graph", (), {
        "invoke": staticmethod(lambda state: {
            **state,
            "relevant_files": ["app/main.py", "tests/test_main.py"],
            "plan": {
                "goal": "Add a health endpoint",
                "assumptions": [],
                "files_to_inspect": [],
                "files_to_modify": [{"path": "app/main.py", "reason": "Register the route."}],
                "files_to_create": [],
                "implementation_steps": [{"step": 1, "description": "Add route and test."}],
                "testing_strategy": ["Test a successful response."],
                "risks": [],
                "dependencies": [],
            },
        })
    })())
    created = create_task(TaskCreateRequest(
        repository_url="https://github.com/example/demo",
        task="Add a health-check endpoint and create tests for it.",
    ))
    task_id = created["task_id"]

    analyzed = analyze_task(task_id)
    assert analyzed["status"] == "completed"
    assert analyzed["repository"]["framework"] == "FastAPI"

    planned = plan_task(task_id)
    assert planned["status"] == "completed"
    assert planned["plan"]["goal"] == "Add a health endpoint"

    task = get_task(task_id)
    assert task["status"] == "planned"
    assert "repo_path" not in task
    events = get_task_events(task_id)["events"]
    assert any(event["name"] == "Repository analyzed" for event in events)
    assert any(event["name"] == "Plan generated" for event in events)


def test_task_api_rejects_non_github_url():
    with pytest.raises(HTTPException) as error:
        create_task(TaskCreateRequest(
            repository_url="https://example.com/repo",
            task="Add a health endpoint and tests.",
        ))
    assert error.value.status_code == 400
