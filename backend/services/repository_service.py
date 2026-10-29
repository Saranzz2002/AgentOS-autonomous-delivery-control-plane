from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.tools.filesystem import get_repository_tree, important_files
from backend.tools.repository import analyze_repository, clone_repository


class RepositoryService:
    def clone(self, repository_url: str, task_id: str) -> Path:
        return clone_repository(repository_url, task_id)

    def analyze(self, repo_path: str | Path, repository_url: str) -> dict[str, Any]:
        metadata = analyze_repository(repo_path, repository_url)
        tree = get_repository_tree(repo_path)
        metadata["tree"] = tree
        metadata["important_files"] = important_files(tree)
        return metadata


repository_service = RepositoryService()
