from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


class RunStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create(self, repository_url: str, task: str) -> dict[str, Any]:
        run_id = "run_" + uuid4().hex[:12]
        record = {"run_id": run_id, "repository_url": repository_url, "task": task,
                  "status": "CREATED", "iteration": 0, "review_iteration": 0,
                  "human_revision_cycles": 0, "test_status": "pending",
                  "events": [], "created_at": datetime.now(timezone.utc).isoformat(),
                  "repository": None, "plan": None, "diff": {"files_changed": [], "insertions": 0,
                  "deletions": 0, "diff": ""}, "test_result": None, "review": None,
                  "approval": None, "error": None}
        with self._lock:
            self._records[run_id] = record
        return record

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._records.get(run_id)

    def update(self, run_id: str, **values: Any) -> None:
        with self._lock:
            if run_id in self._records:
                self._records[run_id].update(values)

    def transition(self, run_id: str, expected_status: str, **values: Any) -> bool:
        """Atomically apply an approval transition only from the expected state."""
        with self._lock:
            record = self._records.get(run_id)
            if not record or record.get("status") != expected_status:
                return False
            record.update(values)
            return True

    def event(self, run_id: str, event_type: str, message: str, iteration: int = 0) -> None:
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": event_type,
                 "message": message, "iteration": iteration}
        with self._lock:
            if run_id in self._records:
                self._records[run_id]["events"].append(event)


run_store = RunStore()
