from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.graph.workflow import planning_workflow
from backend.models.schemas import TaskCreateRequest
from backend.services.repository_service import repository_service
from backend.services.task_store import task_store
from backend.tools.repository import RepositoryError, validate_repository_url

router = APIRouter(tags=["tasks"])


def _task_view(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in record.items()
        if key not in {"repo_path", "context"}
    }


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
    try:
        repository_url, _, _ = validate_repository_url(payload.repository_url)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository URL. Use a public HTTPS GitHub repository.") from exc
    record = task_store.create(repository_url, payload.task.strip())
    return {"task_id": record["task_id"], "status": record["status"]}


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found.")
    return _task_view(record)


@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: str) -> dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task_id": task_id, "events": record["events"]}


@router.post("/tasks/{task_id}/analyze")
def analyze_task(task_id: str) -> dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found.")
    if record.get("repository"):
        return {"status": record["analysis_status"], "repository": record["repository"]}
    task_store.update(task_id, status="analyzing", analysis_status="running")
    task_store.add_event(task_id, "Repository clone started", "repository", "Cloning the public GitHub repository.")
    try:
        workspace = repository_service.clone(record["repository_url"], task_id)
        task_store.update(task_id, repo_path=str(workspace))
        task_store.add_event(task_id, "Repository cloned", "repository", f"Workspace created for {record['repository_url']}.")
        metadata = repository_service.analyze(workspace, record["repository_url"])
    except RepositoryError as exc:
        task_store.update(task_id, status="failed", analysis_status="failed", error=str(exc))
        task_store.add_event(task_id, "Repository analysis failed", "repository", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task_store.update(task_id, status="analyzed", analysis_status="completed", repository=metadata)
    task_store.add_event(
        task_id,
        "Repository analyzed",
        "repository",
        f"Detected {metadata['language']} / {metadata['framework']}; found {metadata['source_file_count']} source files and {metadata['test_file_count']} test files.",
    )
    return {"status": "completed", "repository": metadata}


@router.post("/tasks/{task_id}/plan")
def plan_task(task_id: str) -> dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found.")
    if not record.get("repository") or not record.get("repo_path"):
        raise HTTPException(status_code=409, detail="Analyze the repository before generating a plan.")
    if record.get("plan"):
        return {"status": "completed", "plan": record["plan"]}
    task_store.update(task_id, status="planning", plan_status="running", context_status="running")
    task_store.add_event(task_id, "Context retrieval started", "context", "Searching repository files for task-relevant implementation patterns.")
    initial: dict[str, Any] = {
        "task_id": task_id,
        "repo_path": record["repo_path"],
        "repository_url": record["repository_url"],
        "task": record["task"],
        "repository_metadata": record["repository"],
        "repository_tree": record["repository"]["tree"],
        "important_files": record["repository"]["important_files"],
        "events": [],
        "status": "analyzed",
    }
    try:
        task_store.add_event(task_id, "Planner started", "planner", "Generating a structured plan from selected repository context.")
        result = planning_workflow.invoke(initial)
    except Exception as exc:
        message = "Planner temporarily unavailable. Check GROQ_API_KEY and retry."
        task_store.update(task_id, status="failed", plan_status="failed", context_status="failed", error=message)
        task_store.add_event(task_id, "Planning failed", "planner", message)
        status_code = 503 if "GROQ_API_KEY" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=message) from exc

    plan = result.get("plan")
    relevant_files = result.get("relevant_files", [])
    task_store.update(
        task_id,
        status="planned",
        context_status="completed",
        plan_status="completed",
        relevant_files=relevant_files,
        plan=plan,
        context_summary={"selected_files": relevant_files},
    )
    task_store.add_event(task_id, "Context selected", "context", f"Selected {len(relevant_files)} relevant repository files.")
    task_store.add_event(task_id, "Plan generated", "planner", "Structured plan validated against the AgentOS plan schema.")
    return {"status": "completed", "plan": plan, "relevant_files": relevant_files}
