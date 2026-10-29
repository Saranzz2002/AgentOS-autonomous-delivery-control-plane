from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


class TaskStore:
    """Small in-memory store for the single-process hackathon MVP."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create(self, repository_url: str, task: str) -> dict[str, Any]:
        task_id = str(uuid4())
        record: dict[str, Any] = {
            "task_id": task_id,
            "repository_url": repository_url,
            "task": task,
            "status": "created",
            "analysis_status": "pending",
            "context_status": "pending",
            "plan_status": "pending",
            "repository": None,
            "relevant_files": [],
            "plan": None,
            "events": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo_path": None,
        }
        with self._lock:
            self._records[task_id] = record
        self.add_event(task_id, "Task created", "task", "Task accepted for repository analysis.")
        return self.get(task_id) or record

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(task_id)
            return _copy(record) if record else None

    def update(self, task_id: str, **values: Any) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                return None
            record.update(values)
            return _copy(record)

    def add_event(self, task_id: str, name: str, agent: str, message: str) -> None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return
            record["events"].append({
                "id": str(uuid4()),
                "name": name,
                "agent": agent,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


task_store = TaskStore()
