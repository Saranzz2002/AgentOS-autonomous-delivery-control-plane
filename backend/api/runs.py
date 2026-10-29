from __future__ import annotations

from typing import Any

from concurrent.futures import ThreadPoolExecutor
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.graph.workflow import build_autonomous_workflow
from backend.services.repository_service import repository_service
from backend.services.run_store import run_store
from backend.tools.repository import RepositoryError, validate_repository_url

router = APIRouter(tags=["runs"])
_run_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agentos-run")


class RunCreateRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=2048)
    task: str = Field(min_length=1, max_length=4000)


def _emit(run_id: str, event_type: str, message: str, iteration: int = 0) -> None:
    run_store.event(run_id, event_type, message, iteration)
    record = run_store.get(run_id) or {}
    if event_type.startswith(("review.", "approval.")) or event_type == "ship.ready":
        updates: dict[str, Any] = {"review_iteration": max(iteration, record.get("review_iteration", 0))}
    else:
        updates = {"iteration": max(iteration, record.get("iteration", 0))}
    if event_type == "repository.analyzing": updates["status"] = "ANALYZING"
    elif event_type in {"planner.started", "context.searching"}: updates["status"] = "PLANNING"
    elif event_type == "tests.started": updates.update(status="TESTING", test_status="running")
    elif event_type == "tests.failed": updates.update(status="DEBUGGING", test_status="failed")
    elif event_type == "tests.passed": updates.update(status="TESTING", test_status="passed")
    elif event_type.startswith(("debugger.", "fix.")): updates["status"] = "DEBUGGING"
    elif event_type.startswith(("coder.", "changes.")): updates["status"] = "CODING"
    elif event_type == "review.started": updates["status"] = "REVIEWING"
    elif event_type == "review.changes_requested": updates["status"] = "CHANGES_REQUESTED"
    # Persist final review statuses together with the review payload in _save_outcome.
    elif event_type in {"approval.approved", "ship.ready"}: updates["status"] = "READY_TO_SHIP"
    elif event_type == "run.failed": updates["status"] = "FAILED"
    run_store.update(run_id, **updates)


def _save_outcome(run_id: str, outcome: dict[str, Any]) -> str:
    from backend.tools.filesystem import get_git_diff
    record = run_store.get(run_id) or {}
    repo_path = outcome.get("repo_path") or record.get("repo_path")
    diff = outcome.get("diff_result") or (get_git_diff(repo_path) if repo_path else record.get("diff", {}))
    test_result = outcome.get("test_result") or {}
    passed = outcome.get("test_status") == "passed" and test_result.get("exit_code") == 0
    status = outcome.get("status") if passed else "FAILED"
    if status not in {"WAITING_FOR_HUMAN_APPROVAL", "REJECTED"}:
        status = "FAILED"
    run_store.update(
        run_id, status=status, iteration=outcome.get("iteration", 0),
        review_iteration=outcome.get("review_iteration", record.get("review_iteration", 0)),
        repository=outcome.get("repository_metadata", record.get("repository")),
        repository_tree=outcome.get("repository_tree", record.get("repository_tree", [])),
        important_files=outcome.get("important_files", record.get("important_files", {})),
        relevant_files=outcome.get("relevant_files", record.get("relevant_files", [])),
        context=outcome.get("context", record.get("context", "")),
        plan=outcome.get("plan", record.get("plan")), test_status=outcome.get("test_status", "failed"),
        test_result=outcome.get("test_result"), debug_result=outcome.get("debug_result", record.get("debug_result")),
        code_changes=outcome.get("code_changes", record.get("code_changes", [])),
        review=outcome.get("review_result"), diff=diff, error=outcome.get("error"),
    )
    return status


def _run(run_id: str) -> None:
    record = run_store.get(run_id)
    if not record:
        return
    try:
        run_store.update(run_id, status="ANALYZING")
        repo_path = repository_service.clone(record["repository_url"], run_id)
        run_store.update(run_id, repo_path=str(repo_path), status="ANALYZING")
        initial: dict[str, Any] = {"task_id": run_id, "repo_path": str(repo_path),
                                   "repository_url": record["repository_url"], "task": record["task"],
                                   "events": [], "status": "CREATED", "iteration": 0,
                                   "review_iteration": 0}
        outcome = build_autonomous_workflow(emit=lambda *event: _emit(run_id, *event)).invoke(initial)
        final_status = _save_outcome(run_id, {**outcome, "repo_path": str(repo_path)})
        event_type = "run.failed" if final_status == "FAILED" else "run.completed"
        message = ("Review complete; waiting for human approval" if final_status == "WAITING_FOR_HUMAN_APPROVAL"
                   else "Review completed and rejected" if final_status == "REJECTED"
                   else outcome.get("error") or "Run failed")
        _emit(run_id, event_type, message, outcome.get("iteration", 0))
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if api_key:
            message = message.replace(api_key, "[redacted]")
        run_store.update(run_id, status="FAILED", error=f"Autonomous run failed: {type(exc).__name__}: {message[:500]}")
        _emit(run_id, "run.failed", "Autonomous run stopped after an internal error")


def _revise(run_id: str, comment: str) -> None:
    record = run_store.get(run_id)
    if not record or not record.get("repo_path"):
        return
    initial = {"task_id": run_id, "repo_path": record["repo_path"],
               "repository_url": record["repository_url"], "task": record["task"],
               "repository_metadata": record.get("repository"),
               "repository_tree": record.get("repository_tree", []),
               "important_files": record.get("important_files", {}),
               "relevant_files": record.get("relevant_files", []), "context": record.get("context", ""),
               "plan": record.get("plan"), "review_feedback": comment,
               "events": [], "status": "CHANGES_REQUESTED", "iteration": 0, "review_iteration": 0}
    try:
        outcome = build_autonomous_workflow(emit=lambda *event: _emit(run_id, *event)).invoke(initial)
        final_status = _save_outcome(run_id, outcome)
        event_type = "run.failed" if final_status == "FAILED" else "run.completed"
        message = ("Revision reviewed; waiting for human approval" if final_status == "WAITING_FOR_HUMAN_APPROVAL"
                   else "Revision reviewed and rejected" if final_status == "REJECTED"
                   else outcome.get("error") or "Revision failed")
        _emit(run_id, event_type, message, outcome.get("iteration", 0))
    except Exception as exc:
        message = str(exc)
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if api_key: message = message.replace(api_key, "[redacted]")
        run_store.update(run_id, status="FAILED", error=f"Revision failed: {type(exc).__name__}: {message[:500]}")
        _emit(run_id, "run.failed", "Revision stopped after an internal error")


@router.post("/runs", status_code=202)
def create_run(payload: RunCreateRequest) -> dict[str, str]:
    try:
        repository_url, _, _ = validate_repository_url(payload.repository_url)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository URL. Use a public HTTPS GitHub repository.") from exc
    record = run_store.create(repository_url, payload.task.strip())
    _run_executor.submit(_run, record["run_id"])
    return {"run_id": record["run_id"], "status": record["status"]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {key: value for key, value in record.items() if key not in {"repo_path", "context"}}


@router.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str) -> dict[str, Any]:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    return record["diff"]


@router.get("/runs/{run_id}/events")
def get_run_events(run_id: str) -> dict[str, Any]:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"run_id": run_id, "events": record["events"]}


@router.get("/runs/{run_id}/review")
def get_run_review(run_id: str) -> dict[str, Any]:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    if not record.get("review"):
        raise HTTPException(status_code=409, detail="Review is not available yet.")
    return {"run_id": run_id, "review": record["review"]}
