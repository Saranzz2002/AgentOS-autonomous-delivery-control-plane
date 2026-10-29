import pytest
from fastapi import HTTPException

from backend.api import runs


def test_create_run_schedules_background_and_returns_id(monkeypatch):
    submitted = []

    class Executor:
        def submit(self, function, run_id):
            submitted.append((function, run_id))

    monkeypatch.setattr(runs, "_run_executor", Executor())
    response = runs.create_run(runs.RunCreateRequest(
        repository_url="https://github.com/example/project", task="Add a health endpoint"
    ))
    assert response["status"] == "CREATED"
    assert response["run_id"] == submitted[0][1]
    assert submitted[0][0] is runs._run
    assert runs.get_run(response["run_id"])["status"] == "CREATED"
    assert runs.get_run_events(response["run_id"])["events"] == []
    assert runs.get_run_diff(response["run_id"])["diff"] == ""


def test_create_run_rejects_non_github_url():
    with pytest.raises(HTTPException) as error:
        runs.create_run(runs.RunCreateRequest(repository_url="https://example.com/repo", task="Add endpoint"))
    assert error.value.status_code == 400
