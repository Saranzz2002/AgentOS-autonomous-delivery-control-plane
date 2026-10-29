from __future__ import annotations

import json
import subprocess

import pytest

from backend.agents.coder import CodingOutput, ProposedChange, validate_changes
from backend.agents.debugger import analyze_failure
from backend.graph import workflow
from backend.tools.filesystem import RepositoryFileError, apply_patch, create_file, read_file, write_file
from backend.tools.sandbox import _copy_safe_workspace, run_in_sandbox
from backend.tools.testing import detect_test_command, run_tests


def test_filesystem_create_modify_patch_and_reject_escape(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    create_file(repo, "src/a.py", "value = 1\n")
    write_file(repo, "src/a.py", "value = 2\n")
    assert read_file(repo, "src/a.py") == "value = 2\n"
    patch = "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-value = 2\n+value = 3\n"
    apply_patch(repo, "src/a.py", patch)
    assert read_file(repo, "src/a.py").splitlines() == ["value = 3"]
    agent_patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-value = 3\n+value = 4\n*** End Patch"
    apply_patch(repo, "src/a.py", agent_patch)
    assert read_file(repo, "src/a.py").splitlines() == ["value = 4"]
    for path in ("../outside", ".env", "nested/.env.local", "C:\\Windows\\x"):
        with pytest.raises(RepositoryFileError):
            create_file(repo, path, "x")


def test_coder_validates_paths_and_action(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(RepositoryFileError):
        validate_changes(str(repo), CodingOutput(changes=[ProposedChange(
            file="../../outside", action="create", reason="bad", content="x")]))


def test_sandbox_workspace_omits_credentials_and_caches(tmp_path):
    source, destination = tmp_path / "repo", tmp_path / "stage"
    source.mkdir()
    (source / "app.py").write_text("print('safe')")
    (source / ".env").write_text("GROQ_API_KEY=fake")
    (source / "id_rsa").write_text("private key")
    (source / ".ssh").mkdir()
    (source / ".ssh" / "config").write_text("ssh config")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "module.pyc").write_bytes(b"binary")
    _copy_safe_workspace(source, destination)
    assert (destination / "app.py").is_file()
    assert not (destination / ".env").exists()
    assert not (destination / "id_rsa").exists()
    assert not (destination / ".ssh").exists()
    assert not (destination / "__pycache__").exists()


def test_debugger_corrects_malformed_structured_output():
    valid = json.dumps({"root_cause": "Assertion shows wrong body", "affected_files": ["app.py"],
                        "fix_description": "Return the expected status", "recommended_changes": []})
    llm = FakeLLM([json.dumps({"root_cause": "wrong body", "affected_files": [], "fix_description": "fix",
                              "recommended_changes": [{"path": "app.py", "change": "bad"}]}), valid])
    result = analyze_failure({"task": "health", "test_output": "assert failed"}, llm)
    assert result["root_cause"] == "Assertion shows wrong body"


def test_detect_test_command_is_deterministic(tmp_path):
    assert detect_test_command(tmp_path) is None
    (tmp_path / "tests").mkdir()
    assert detect_test_command(tmp_path)[1] == ["python", "-m", "pytest", "-q"]
    (tmp_path / "tests").rmdir()
    (tmp_path / "test_app.py").write_text("def test_ok(): pass")
    assert detect_test_command(tmp_path)[1] == ["python", "-m", "pytest", "-q"]
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
    assert detect_test_command(tmp_path)[1] == ["npm", "test"]


def test_no_tests_returns_without_runner(tmp_path):
    assert run_tests(tmp_path, runner=lambda *args, **kwargs: pytest.fail("runner must not execute"))["status"] == "no_tests_detected"


def test_sandbox_captures_success_and_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.tools.sandbox._ensure_python_image", lambda: None)
    monkeypatch.setattr("backend.tools.sandbox.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "ok", ""))
    assert run_in_sandbox(tmp_path, ["pytest"], image="agentos-python-sandbox:latest")["status"] == "passed"
    monkeypatch.setattr("backend.tools.sandbox.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a[0], 2, "", "broken"))
    failed = run_in_sandbox(tmp_path, ["pytest"], image="node:22-bookworm-slim")
    assert failed["status"] == "failed" and failed["exit_code"] == 2


def test_sandbox_timeout_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.tools.sandbox.subprocess.run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("docker", 1, output=b"partial")))
    result = run_in_sandbox(tmp_path, ["pytest"], image="node:22-bookworm-slim", timeout=1)
    assert result["status"] == "timeout"
    assert "exceeded 1 seconds" in result["summary"]


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, *args, **kwargs):
        return next(self.responses)


def _graph(monkeypatch, tmp_path, llm, tester):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 'initial'\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"], capture_output=True, check=True)
    monkeypatch.setattr(workflow, "retrieve_context", lambda state, client: {"context": "repo code", "relevant_files": ["app.py"]})
    monkeypatch.setattr(workflow, "generate_plan", lambda state, client: {"plan": {"goal": "change app"}})
    events = []
    graph = workflow.build_autonomous_workflow(emit=lambda *event: events.append(event), llm=llm, tester=tester,
        reviewer=lambda *_: {"recommendation": "APPROVE", "summary": "Phase 3 regression review",
            "task_compliance_score": 8, "code_quality_score": 8, "test_quality_score": 8,
            "security_score": 8, "findings": [], "strengths": [], "risks": []})
    result = graph.invoke({"repo_path": str(repo), "task": "Change app behavior", "events": [], "iteration": 0})
    return result, events


def _create_response():
    return json.dumps({"changes": [{"file": "app.py", "action": "modify", "reason": "Implement task", "content": "value = 'implemented'\n"}]})


def _debug_response(content="value = 'fixed'\n"):
    return json.dumps({"root_cause": "The current behavior failed the assertion", "affected_files": ["app.py"],
                       "fix_description": "Update app value", "recommended_changes": [
                           {"file": "app.py", "action": "modify", "reason": "Fix failing assertion", "content": content}]})


def test_workflow_plan_code_test_passes(monkeypatch, tmp_path):
    llm = FakeLLM([_create_response()])
    result, events = _graph(monkeypatch, tmp_path, llm, lambda *_: {"status": "passed", "exit_code": 0, "summary": "1 passed", "stdout": "1 passed", "stderr": "", "duration": 0.1})
    assert result["test_status"] == "passed" and result["iteration"] == 1
    assert any(event[0] == "tests.passed" for event in events)


def test_workflow_fail_debug_fix_then_pass(monkeypatch, tmp_path):
    llm = FakeLLM([_create_response(), _debug_response()])
    attempts = iter([{"status": "failed", "exit_code": 1, "summary": "assertion failed", "stdout": "expected 2", "stderr": "", "duration": 0.1},
                     {"status": "passed", "exit_code": 0, "summary": "1 passed", "stdout": "1 passed", "stderr": "", "duration": 0.1}])
    result, events = _graph(monkeypatch, tmp_path, llm, lambda *_: next(attempts))
    assert result["test_status"] == "passed" and result["iteration"] == 2
    assert any(event[0] == "debugger.completed" for event in events)
    assert any(event[0] == "fix.applied" for event in events)


def test_workflow_stops_after_three_failed_attempts(monkeypatch, tmp_path):
    llm = FakeLLM([_create_response(), _debug_response("value = 'fix one'\n"), _debug_response("value = 'fix two'\n")])
    failed = lambda *_: {"status": "failed", "exit_code": 1, "summary": "still failing", "stdout": "", "stderr": "assert", "duration": 0.1}
    result, events = _graph(monkeypatch, tmp_path, llm, failed)
    assert result["iteration"] == 3 and result["test_status"] == "failed"
    assert sum(event[0] == "tests.started" for event in events) == 3
    assert sum(event[0] == "debugger.started" for event in events) == 2
