from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from backend.tools.filesystem import get_repository_tree, important_files, read_file


class RepositoryError(ValueError):
    pass


def validate_repository_url(repository_url: str) -> tuple[str, str, str]:
    parsed = urlparse(repository_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RepositoryError("Repository URL contains an invalid port.") from exc
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username
            or parsed.password or port not in (None, 443) or parsed.query or parsed.fragment):
        raise RepositoryError("Only public HTTPS GitHub repository URLs are supported.")
    parts = [part for part in parsed.path.strip("/").removesuffix(".git").split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise RepositoryError("Use a repository URL like https://github.com/owner/repository.")
    return repository_url, parts[0], parts[1]


def clone_repository(repository_url: str, workspace_id: str, workspace_root: str | Path | None = None) -> Path:
    url, _, _ = validate_repository_url(repository_url)
    root = Path(workspace_root or os.getenv("AGENTOS_WORKSPACES", Path(__file__).resolve().parents[2] / "workspaces")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = (root / workspace_id).resolve()
    if not destination.is_relative_to(root):
        raise RepositoryError("Workspace id is invalid.")
    if destination.exists():
        if (destination / ".git").is_dir():
            return destination
        raise RepositoryError("The task workspace already exists and is not a Git repository.")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--", url, str(destination)],
            capture_output=True, text=True, timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryError("Repository clone could not complete. Check URL or repository accessibility.") from exc
    if result.returncode:
        if destination.exists():
            # Preserve partial clones for inspection; never recursively delete an unexpected path.
            raise RepositoryError("Repository could not be cloned. Check URL or repository accessibility.")
        raise RepositoryError("Repository could not be cloned. Check URL or repository accessibility.")
    return destination


def _git_value(repo_path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def analyze_repository(repo_path: str | Path, repository_url: str | None = None) -> dict:
    root = Path(os.path.abspath(repo_path))
    if not root.is_dir():
        raise RepositoryError("Repository workspace does not exist.")
    tree = get_repository_tree(root)
    suffix_counts: dict[str, int] = {}
    for file in tree:
        suffix = Path(file).suffix.lower()
        if suffix:
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    language_suffixes = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust"}
    languages: dict[str, int] = {}
    for suffix, count in suffix_counts.items():
        if suffix in language_suffixes:
            language = language_suffixes[suffix]
            languages[language] = languages.get(language, 0) + count
    primary = max(languages, key=languages.get) if languages else "Unknown"
    important = important_files(tree)
    file_set = {p.lower() for p in tree}
    snippets: list[str] = []
    for path in important["configuration_files"] + important["documentation"]:
        if Path(path).name.lower() in {"package.json", "requirements.txt", "pyproject.toml", "readme.md", "pipfile"}:
            try:
                snippets.append(read_file(root, path, max_bytes=80_000))
            except ValueError:
                pass
    config_text = "\n".join(snippets).lower()
    framework = "unknown"
    checks = [
        ("FastAPI", "fastapi" in config_text), ("Flask", "flask" in config_text),
        ("Django", "django" in config_text), ("Next.js", "next" in config_text and "package.json" in file_set),
        ("React", "react" in config_text), ("Express", "express" in config_text),
        ("Spring", "spring-boot" in config_text or "springframework" in config_text),
    ]
    framework = next((name for name, detected in checks if detected), "Node.js" if "package.json" in file_set and primary in {"JavaScript", "TypeScript"} else "unknown")
    package_manager = next((name for filename, name in (
        ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "Yarn"), ("package-lock.json", "npm"),
        ("bun.lockb", "Bun"), ("poetry.lock", "Poetry"), ("Pipfile", "Pipenv"),
    ) if filename.lower() in file_set), "pip" if primary == "Python" else "unknown")
    test_framework = next((name for token, name in (
        ("pytest", "pytest"), ("jest", "Jest"), ("vitest", "Vitest"), ("mocha", "Mocha"),
        ("unittest", "unittest"), ("playwright", "Playwright"),
    ) if token in config_text), "unknown")
    entry_point = important["entry_points"][0] if important["entry_points"] else None
    repo_name = root.name
    if repository_url:
        try:
            _, _, repo_name = validate_repository_url(repository_url)
        except RepositoryError:
            pass
    return {
        "name": repo_name,
        "repository_url": repository_url,
        "branch": _git_value(root, "branch", "--show-current") if (root / ".git").exists() else None,
        "commit_sha": _git_value(root, "rev-parse", "HEAD") if (root / ".git").exists() else None,
        "language": primary,
        "languages": languages,
        "framework": framework,
        "package_manager": package_manager,
        "test_framework": test_framework,
        "entry_point": entry_point,
        "important_files": important,
        "source_file_count": sum(suffix_counts.get(ext, 0) for ext in language_suffixes),
        "test_file_count": sum(1 for path in tree if "test" in Path(path).name.lower() or "test" in {part.lower() for part in Path(path).parts[:-1]}),
        "tree": tree,
    }
