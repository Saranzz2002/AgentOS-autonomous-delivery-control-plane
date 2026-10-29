from __future__ import annotations

from typing import Any

from backend.agents.coder import generate_code
from backend.agents.debugger import analyze_failure
from backend.tools.filesystem import apply_patch, create_file, get_git_diff, write_file
from backend.tools.testing import run_tests

MAX_ITERATIONS = 3


def _apply_changes(repo_path: str, changes: list[dict[str, Any]]) -> list[str]:
    applied = []
    for change in changes:
        path = change["file"]
        if change["action"] == "create":
            create_file(repo_path, path, change["content"])
        elif change["action"] == "modify":
            write_file(repo_path, path, change["content"])
        else:
            apply_patch(repo_path, path, change["content"])
        applied.append(path)
    return applied


def execute_code_test_loop(state: dict[str, Any], *, emit, llm=None, tester=run_tests) -> dict[str, Any]:
    current = dict(state)
    emit("coder.started", "Coding Agent generating structured file changes", 1)
    changes = generate_code(current, llm)
    emit("coder.completed", f"Coding Agent proposed {len(changes)} file change(s)", 1)
    emit("changes.applying", "Validating and applying proposed repository changes", 1)
    paths = _apply_changes(current["repo_path"], changes)
    emit("changes.applied", "Applied: " + ", ".join(paths), 1)
    current["code_changes"] = changes
    for iteration in range(1, MAX_ITERATIONS + 1):
        current["iteration"] = iteration
        diff = get_git_diff(current["repo_path"])
        current.update(git_diff=diff["diff"])
        emit("tests.started", f"Running detected tests in Docker (attempt {iteration}/{MAX_ITERATIONS})", iteration)
        result = tester(current["repo_path"])
        current.update(test_output=(result.get("stdout", "") + "\n" + result.get("stderr", ""))[-40_000:],
                       test_status=result["status"], test_result=result, git_diff=diff["diff"])
        if result["status"] == "passed" and result.get("exit_code") == 0:
            emit("tests.passed", result.get("summary", "Test runner returned exit code 0"), iteration)
            current["status"] = "completed"
            return current
        emit("tests.failed", result.get("summary", result["status"]), iteration)
        if result["status"] in {"unavailable", "no_tests_detected"}:
            current["status"] = "failed"
            current["error"] = result.get("summary")
            break
        if iteration == MAX_ITERATIONS:
            current["status"] = "failed"
            current["error"] = "Maximum retry attempts reached"
            break
        emit("debugger.started", "Debugger analyzing captured test output and current diff", iteration)
        diagnosis = analyze_failure(current, llm)
        current["debug_result"] = diagnosis
        emit("debugger.completed", diagnosis["root_cause"], iteration)
        fixes = diagnosis["recommended_changes"]
        # Reuse coder validation before applying debugger-proposed files.
        from backend.agents.coder import CodingOutput, ProposedChange, validate_changes
        validated = validate_changes(current["repo_path"], CodingOutput(changes=[ProposedChange.model_validate(item) for item in fixes])) if fixes else []
        if not validated:
            current["status"] = "failed"
            current["error"] = "Debugger produced no actionable fix"
            break
        emit("fix.applying", diagnosis["fix_description"], iteration)
        fixed = _apply_changes(current["repo_path"], validated)
        emit("fix.applied", "Applied debugger fix: " + ", ".join(fixed), iteration)
        current["code_changes"] = current.get("code_changes", []) + validated
        diff = get_git_diff(current["repo_path"])
        current["git_diff"] = diff["diff"]
    return current
