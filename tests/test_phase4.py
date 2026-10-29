from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.agents import reviewer
from backend.agents.coder import generate_code
from backend.api import approval
from backend.api import runs
from backend.graph import workflow
from backend.models.review import ReviewResult
from backend.services.run_store import run_store


def valid_review(**overrides):
    value = {"recommendation": "APPROVE", "summary": "Looks good", "task_compliance_score": 9,
             "code_quality_score": 8, "test_quality_score": 9, "security_score": 10,
             "findings": [], "strengths": [], "risks": []}
    value.update(overrides)
    return value


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        return next(self.outputs)


def test_reviewer_parses_structured_result_and_receives_diff():
    llm = FakeLLM([json.dumps(valid_review())])
    result = reviewer.review_changes({"test_status": "passed", "test_result": {"exit_code": 0},
        "task": "Add health endpoint", "git_diff": "+app route", "diff_result": {"files_changed": ["app.py"]}}, llm)
    assert result["recommendation"] == "APPROVE"
    assert "+app route" in llm.prompts[0][0]


def test_reviewer_corrects_malformed_output_once():
    llm = FakeLLM(["not json", json.dumps(valid_review())])
    assert reviewer.review_changes({"test_status": "passed", "test_result": {"exit_code": 0}}, llm)["recommendation"] == "APPROVE"
    assert len(llm.prompts) == 2


@pytest.mark.parametrize("override", [{"task_compliance_score": 11}, {"recommendation": "MAYBE"}])
def test_review_schema_rejects_invalid_values(override):
    with pytest.raises(ValidationError):
        ReviewResult.model_validate(valid_review(**override))


def test_critical_review_finding_forces_rejection():
    finding = {"severity": "critical", "category": "security", "file": "app.py", "line": 1,
               "description": "Hardcoded credential", "recommendation": "Remove it"}
    llm = FakeLLM([json.dumps(valid_review(findings=[finding]))])
    state = {"test_status": "passed", "test_result": {"exit_code": 0},
             "diff_result": {"files_changed": ["app.py"]}}
    assert reviewer.review_changes(state, llm)["recommendation"] == "REJECT"


def test_reviewer_rejects_nonpassing_tests():
    with pytest.raises(ValueError, match="passing test"):
        reviewer.review_changes({"test_status": "failed", "test_result": {"exit_code": 1}}, FakeLLM([]))


def test_coder_corrects_malformed_structured_output(python_repo):
    llm = FakeLLM(["not json", json.dumps({"changes": [{"file": "new.py", "action": "create",
        "reason": "Add requested module", "content": "value = 1\n"}]})])
    result = generate_code({"repo_path": str(python_repo), "task": "Add module"}, llm)
    assert result[0]["file"] == "new.py"
    assert len(llm.prompts) == 2


def test_approval_requires_waiting_state_and_is_single_use(monkeypatch):
    run = run_store.create("https://github.com/example/repo", "task")
    rid = run["run_id"]
    run_store.update(rid, status="CODING", review=valid_review())
    with pytest.raises(Exception) as error:
        approval.approve_run(rid, approval.ApprovalComment(comment="ok"))
    assert getattr(error.value, "status_code", None) == 409
    run_store.update(rid, status="WAITING_FOR_HUMAN_APPROVAL")
    result = approval.approve_run(rid, approval.ApprovalComment(comment="approved"))
    assert result["status"] == "READY_TO_SHIP"
    assert run_store.get(rid)["approval"]["comment"] == "approved"
    with pytest.raises(Exception) as error:
        approval.approve_run(rid, approval.ApprovalComment(comment="again"))
    assert getattr(error.value, "status_code", None) == 409


def test_human_rejection_stores_feedback_and_schedules_bounded_revision(monkeypatch):
    run = run_store.create("https://github.com/example/repo", "task")
    rid = run["run_id"]
    run_store.update(rid, status="WAITING_FOR_HUMAN_APPROVAL", review=valid_review(), repo_path="/tmp/repo")
    submitted = []
    class Executor:
        def submit(self, function, *args):
            submitted.append((function, args))
    monkeypatch.setattr(approval, "_run_executor", Executor())
    result = approval.reject_run(rid, approval.ApprovalComment(comment="Please add a missing test"))
    assert result["status"] == "CHANGES_REQUESTED"
    assert run_store.get(rid)["approval"]["comment"] == "Please add a missing test"
    assert submitted[0][0] is approval._revise
    assert submitted[0][1] == (rid, "Please add a missing test")


def test_reject_after_two_human_revisions_ends_run():
    run = run_store.create("https://github.com/example/repo", "task")
    rid = run["run_id"]
    run_store.update(rid, status="WAITING_FOR_HUMAN_APPROVAL", review=valid_review(), human_revision_cycles=2)
    result = approval.reject_run(rid, approval.ApprovalComment(comment="still broken"))
    assert result["status"] == "REJECTED"
    assert run_store.get(rid)["human_revision_cycles"] == 2


def test_reviewer_rejection_remains_rejected_after_completion_event():
    record = run_store.create("https://github.com/example/repo", "task")
    rid = record["run_id"]
    outcome = {"status": "REJECTED", "test_status": "passed", "test_result": {"exit_code": 0},
               "review_result": valid_review(recommendation="REJECT"),
               "diff_result": {"files_changed": [], "insertions": 0, "deletions": 0, "diff": ""}}
    assert runs._save_outcome(rid, outcome) == "REJECTED"
    runs._emit(rid, "run.completed", "Review completed and rejected")
    assert run_store.get(rid)["status"] == "REJECTED"


def test_workflow_reviewer_requests_changes_then_approves(tmp_path, monkeypatch):
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    (repo / "app.py").write_text("status = 'old'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-m", "initial"], check=True, capture_output=True)
    monkeypatch.setattr(workflow.repository_service, "analyze", lambda *args: {
        "name": "repo", "language": "Python", "framework": "none", "test_framework": "pytest",
        "tree": ["app.py"], "important_files": {}})
    monkeypatch.setattr(workflow, "retrieve_context", lambda state, llm=None: {"context": "app.py", "relevant_files": ["app.py"]})
    monkeypatch.setattr(workflow, "generate_plan", lambda state, llm=None: {"plan": {"steps": ["edit"]}})
    code_calls = []
    def code(state, llm=None):
        code_calls.append(1)
        return [{"file": "app.py", "action": "modify", "reason": "task", "content":
                 "status = 'new'\n# test coverage added\n" if len(code_calls) == 1 else "status = 'new'\n# test coverage added\n# review addressed\n"}]
    monkeypatch.setattr(workflow, "generate_code", code)
    decisions = iter([valid_review(recommendation="CHANGES_REQUESTED"), valid_review()])
    def review(state, llm=None):
        assert state["test_status"] == "passed"
        return next(decisions)
    events = []
    graph = workflow.build_autonomous_workflow(emit=lambda *event: events.append(event),
        tester=lambda path: {"status": "passed", "exit_code": 0, "summary": "tests passed", "stdout": "", "stderr": ""},
        reviewer=review)
    result = graph.invoke({"task_id": "test", "repo_path": str(repo), "task": "change status", "events": []})
    assert result["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert result["review_iteration"] == 2
    assert len(code_calls) == 2
    assert any(event[0] == "review.changes_requested" for event in events)
    assert any(event[0] == "approval.requested" for event in events)

