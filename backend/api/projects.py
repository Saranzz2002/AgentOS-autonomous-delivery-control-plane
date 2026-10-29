from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from backend.tools.repository import RepositoryError, clone_repository, validate_repository_url

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    repo_url: HttpUrl


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict[str, str]:
    """Clone a public GitHub repository into an isolated per-project directory."""
    project_id = str(uuid4())
    url = str(payload.repo_url)
    try:
        normalized_url, _, name = validate_repository_url(url)
        destination = clone_repository(normalized_url, project_id)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": project_id,
        "name": name,
        "repo_url": url,
        "status": "cloned",
        "workspace": str(destination),
    }
