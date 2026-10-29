from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: Literal["correctness", "security", "testing", "quality", "maintainability", "scope"]
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1, max_length=2_000)
    recommendation: str = Field(min_length=1, max_length=2_000)


class ReviewResult(BaseModel):
    recommendation: Literal["APPROVE", "CHANGES_REQUESTED", "REJECT"]
    summary: str = Field(min_length=1, max_length=4_000)
    task_compliance_score: int = Field(ge=0, le=10)
    code_quality_score: int = Field(ge=0, le=10)
    test_quality_score: int = Field(ge=0, le=10)
    security_score: int = Field(ge=0, le=10)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=50)
    strengths: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=30)
