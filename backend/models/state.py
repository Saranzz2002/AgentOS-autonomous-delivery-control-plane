from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    project_id: str
    task_id: str
    repo_path: str
    repository_url: str
    task: str
    repository_metadata: dict[str, Any]
    repository_tree: list[str]
    important_files: dict[str, list[str]]
    relevant_files: list[str]
    context: str
    plan: dict[str, Any]
    code_changes: list[dict[str, Any]]
    test_output: str
    test_status: str
    test_result: dict[str, Any]
    debug_result: dict[str, Any]
    git_diff: str
    diff_result: dict[str, Any]
    iteration: int
    review_result: dict[str, Any]
    review_iteration: int
    review_feedback: str
    human_revision_cycles: int
    approval: dict[str, Any]
    events: list[dict[str, Any]]
    status: str
    error: str | None
