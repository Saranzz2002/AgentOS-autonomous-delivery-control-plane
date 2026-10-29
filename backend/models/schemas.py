from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class TaskCreateRequest(BaseModel):
    repository_url: str = Field(validation_alias=AliasChoices("repository_url", "repo_url"), min_length=1)
    task: str = Field(min_length=8, max_length=4_000)


class FileChange(BaseModel):
    path: str
    reason: str


class ImplementationStep(BaseModel):
    step: int = Field(ge=1)
    description: str


class Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal: str
    assumptions: list[str] = Field(default_factory=list)
    files_to_inspect: list[FileChange] = Field(default_factory=list)
    files_to_modify: list[FileChange] = Field(default_factory=list)
    files_to_create: list[FileChange] = Field(default_factory=list)
    implementation_steps: list[ImplementationStep] = Field(default_factory=list)
    testing_strategy: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def goal_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Plan goal cannot be blank.")
        return value.strip()
