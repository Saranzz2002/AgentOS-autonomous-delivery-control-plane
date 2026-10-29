from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.runs import _emit, _run_executor, _revise
from backend.services.run_store import run_store

router = APIRouter(tags=["approval"])
MAX_HUMAN_REVISION_CYCLES = 2


class ApprovalComment(BaseModel):
    comment: str = Field(default="", max_length=2_000)


def _stamp(status: str, comment: str) -> dict:
    return {"status": status, "comment": comment.strip(),
            "updated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, payload: ApprovalComment) -> dict:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    if not record.get("review") or record["review"].get("recommendation") != "APPROVE":
        raise HTTPException(status_code=409, detail="A reviewer-approved run is required before human approval.")
    approval = _stamp("APPROVED", payload.comment)
    if not run_store.transition(run_id, "WAITING_FOR_HUMAN_APPROVAL", status="READY_TO_SHIP", approval=approval):
        raise HTTPException(status_code=409, detail="Run is not waiting for human approval.")
    _emit(run_id, "approval.approved", payload.comment.strip() or "Human approved the reviewed changes", record.get("review_iteration", 0))
    _emit(run_id, "ship.ready", "Approved and ready to ship; no deployment was performed", record.get("review_iteration", 0))
    return {"run_id": run_id, "status": "READY_TO_SHIP", "approval": approval}


@router.post("/runs/{run_id}/reject")
def reject_run(run_id: str, payload: ApprovalComment) -> dict:
    record = run_store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    cycles = record.get("human_revision_cycles", 0)
    if cycles >= MAX_HUMAN_REVISION_CYCLES:
        approval = _stamp("REJECTED", payload.comment)
        if not run_store.transition(run_id, "WAITING_FOR_HUMAN_APPROVAL", status="REJECTED",
                                    approval=approval, error="Human revision limit reached"):
            raise HTTPException(status_code=409, detail="Run is not waiting for human approval.")
        _emit(run_id, "approval.rejected", "Human rejected the run; revision limit reached", record.get("review_iteration", 0))
        return {"run_id": run_id, "status": "REJECTED", "approval": approval}

    approval = _stamp("REVISION_REQUESTED", payload.comment)
    if not run_store.transition(run_id, "WAITING_FOR_HUMAN_APPROVAL", status="CHANGES_REQUESTED",
                                approval=approval, human_revision_cycles=cycles + 1):
        raise HTTPException(status_code=409, detail="Run is not waiting for human approval.")
    feedback = payload.comment.strip() or "Please address the review findings and submit for approval again."
    _emit(run_id, "approval.rejected", feedback, record.get("review_iteration", 0))
    _emit(run_id, "approval.revision_requested", "Human feedback sent to the Coding Agent", record.get("review_iteration", 0))
    _run_executor.submit(_revise, run_id, feedback)
    return {"run_id": run_id, "status": "CHANGES_REQUESTED", "approval": approval,
            "human_revision_cycles": cycles + 1}
