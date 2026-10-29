from __future__ import annotations

import os
import subprocess
import difflib
from pathlib import Path, PurePosixPath

IGNORED_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
MAX_FILE_BYTES = 256_000
MAX_TREE_FILES = 4_000


class RepositoryFileError(ValueError):
    """A requested path cannot be read safely from a repository."""


def _root(repo_path: str | Path) -> Path:
    root = Path(os.path.abspath(repo_path))
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        raise RepositoryFileError("Repository workspace cannot be a symbolic link or junction.")
    if not root.is_dir():
        raise RepositoryFileError("Repository workspace does not exist.")
    return root


def _safe_relative_path(relative_path: str) -> PurePosixPath:
    if not relative_path or "\x00" in relative_path:
        raise RepositoryFileError("A repository-relative file path is required.")
    normalized = relative_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryFileError("Path must stay inside the repository.")
    if path.parts and (":" in path.parts[0] or path.parts[0].startswith("~")):
        raise RepositoryFileError("Absolute paths are not allowed.")
    name = path.name.lower()
    if (name == ".env" or name.startswith((".env.", "credential", "secret", "id_rsa", "id_ed25519"))
            or name in {"known_hosts", ".npmrc", ".pypirc", ".netrc", ".git-credentials",
                        "credentials", "secrets.json", "service-account.json"}
            or any(part.lower() in {".ssh", ".aws"} for part in path.parts)):
        raise RepositoryFileError("Secret and credential files cannot be read.")
    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        raise RepositoryFileError("Secret and credential files cannot be read.")
    return path


def resolve_repository_file(repo_path: str | Path, relative_path: str, *, must_exist: bool = True) -> Path:
    root = _root(repo_path)
    relative = _safe_relative_path(relative_path)
    candidate = root.joinpath(*relative.parts)
    if not candidate.absolute().is_relative_to(root):
        raise RepositoryFileError("Path must stay inside the repository.")
    # Reject symlinks/junctions at each component. This avoids following a path
    # outside the checkout and works reliably with Windows repository files.
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise RepositoryFileError("Symbolic links and junctions cannot be modified or read.")
    if must_exist and not candidate.is_file():
        raise RepositoryFileError("File does not exist in the repository.")
    if must_exist and not candidate.exists():
        raise RepositoryFileError("File does not exist in the repository.")
    return candidate


def read_file(repo_path: str | Path, relative_path: str, max_bytes: int = MAX_FILE_BYTES) -> str:
    path = resolve_repository_file(repo_path, relative_path)
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise RepositoryFileError(f"File exceeds the {max_bytes:,}-byte read limit.")
        raw = path.read_bytes()
    except OSError as exc:
        raise RepositoryFileError(f"Could not read repository file: {exc}") from exc
    if b"\x00" in raw[:8192]:
        raise RepositoryFileError("Binary files cannot be read as source context.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryFileError("File is not valid UTF-8 text.") from exc


def write_file(repo_path: str | Path, relative_path: str, content: str) -> None:
    """Create or replace a repository file after strict path and secret checks."""
    path = resolve_repository_file(repo_path, relative_path, must_exist=False)
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise RepositoryFileError("Generated file exceeds the write size limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def create_file(repo_path: str | Path, relative_path: str, content: str) -> None:
    path = resolve_repository_file(repo_path, relative_path, must_exist=False)
    if path.exists():
        raise RepositoryFileError("Refusing to overwrite an existing file with a create action.")
    write_file(repo_path, relative_path, content)


def apply_patch(repo_path: str | Path, relative_path: str, patch: str) -> None:
    """Apply a unified diff to exactly one validated repository file."""
    path = resolve_repository_file(repo_path, relative_path)
    if len(patch.encode("utf-8")) > MAX_FILE_BYTES:
        raise RepositoryFileError("Patch exceeds the size limit.")
    expected = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    cleaned = patch.strip().removeprefix("```diff").removesuffix("```").strip()
    lines = cleaned.splitlines()
    is_agent_patch = cleaned.startswith("*** Begin Patch")
    if is_agent_patch:
        targets = [line[len("*** Update File: "):].strip() for line in lines
                   if line.startswith("*** Update File: ")]
        if len(targets) != 1 or targets[0].replace("\\", "/").removeprefix("a/").removeprefix("b/") != expected:
            raise RepositoryFileError("Patch must target only the validated repository file.")
    else:
        headers = []
        for line in lines:
            if line.startswith(("--- ", "+++ ")):
                header = line[4:].split("\t", 1)[0].strip()
                if header.startswith(("a/", "b/")):
                    header = header[2:]
                headers.append(header)
        if len(headers) != 2 or any(header != expected for header in headers):
            raise RepositoryFileError("Patch must target only the validated repository file.")

    hunks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line == "@@" or line.startswith("@@ "):
            if current is not None:
                hunks.append(current)
            current = []
        elif current is not None:
            if line.startswith((" ", "+", "-")):
                current.append(line)
            elif line.startswith("\\ No newline") or line == "*** End Patch":
                continue
            elif is_agent_patch:
                raise RepositoryFileError("Patch contains an unsupported hunk line.")
    if current is not None:
        hunks.append(current)
    if not hunks:
        raise RepositoryFileError("Patch contains no update hunks.")

    original = read_file(repo_path, expected)
    output_lines = original.splitlines()
    for hunk in hunks:
        before: list[str] = []
        after: list[str] = []
        for line in hunk:
            value = line[1:]
            if line[0] in " -":
                before.append(value)
            if line[0] in " +":
                after.append(value)
        if not before:
            raise RepositoryFileError("Patch hunk must include existing context.")
        matches = [index for index in range(len(output_lines) - len(before) + 1)
                   if output_lines[index:index + len(before)] == before]
        if len(matches) != 1:
            raise RepositoryFileError("Patch context is missing or ambiguous in the current file.")
        index = matches[0]
        output_lines[index:index + len(before)] = after
    newline = "\r\n" if "\r\n" in original else "\n"
    trailing_newline = original.endswith(("\n", "\r"))
    write_file(repo_path, expected, newline.join(output_lines) + (newline if trailing_newline else ""))


def get_git_diff(repo_path: str | Path) -> dict[str, Any]:
    root = _root(repo_path)
    result = subprocess.run(["git", "diff", "--no-ext-diff", "--no-color", "--"], cwd=root,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=10, check=False)
    if result.returncode:
        return {"files_changed": [], "insertions": 0, "deletions": 0, "diff": ""}
    names = subprocess.run(["git", "diff", "--name-only", "--"], cwd=root,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, check=False).stdout.splitlines()
    diff_parts = [result.stdout]
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root,
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=10, check=False).stdout.splitlines()
    untracked = [name for name in untracked
                 if not any(part in IGNORED_NAMES for part in Path(name).parts)
                 and not name.lower().endswith((".pyc", ".pyo"))]
    names.extend(untracked)
    for name in untracked:
        try:
            content = read_file(root, name)
        except RepositoryFileError:
            continue
        diff_parts.extend((f"diff --git a/{name} b/{name}\nnew file mode 100644\n",
                           "".join(difflib.unified_diff([], content.splitlines(keepends=True),
                                                        fromfile="/dev/null", tofile=f"b/{name}"))))
    diff = "".join(diff_parts)[:1_000_000]
    stat = subprocess.run(["git", "diff", "--numstat", "--"], cwd=root,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=10, check=False).stdout.splitlines()
    added = removed = 0
    for line in stat:
        columns = line.split("\t", 2)
        try:
            added += int(columns[0]); removed += int(columns[1])
        except (ValueError, IndexError):
            continue
    for name in untracked:
        if (root / name).is_file() and not (root / name).is_symlink():
            try:
                added += len(read_file(root, name).splitlines())
            except RepositoryFileError:
                pass
    return {"files_changed": names, "insertions": added, "deletions": removed, "diff": diff}


def get_repository_tree(repo_path: str | Path, max_files: int = MAX_TREE_FILES) -> list[str]:
    root = _root(repo_path)
    files: list[str] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs
            if d not in IGNORED_NAMES
            and not (Path(current) / d).is_symlink()
        )
        for name in sorted(names):
            if name.lower().endswith(".pyc"):
                continue
            relative = (Path(current) / name).relative_to(root).as_posix()
            try:
                _safe_relative_path(relative)
            except RepositoryFileError:
                continue
            files.append(relative)
            if len(files) >= max_files:
                return files
    return files


def important_files(tree: list[str]) -> dict[str, list[str]]:
    lower = {path.lower(): path for path in tree}
    entry_names = {"main.py", "app.py", "server.py", "index.js", "index.ts"}
    entry_points = [p for p in tree if Path(p).name.lower() in entry_names]
    config_names = {
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "requirements.txt", "pyproject.toml", "pipfile", "poetry.lock",
        "dockerfile", "docker-compose.yml", "compose.yml", "tsconfig.json",
    }
    configuration = [p for p in tree if Path(p).name.lower() in config_names]
    tests = sorted({str(Path(p).parent).replace("\\", "/") + "/" for p in tree
                    if "test" in {part.lower() for part in Path(p).parts[:-1]}
                    or Path(p).name.lower().startswith(("test_", "test."))})
    documentation = [lower[name] for name in ("readme.md", "contributing.md") if name in lower]
    return {
        "entry_points": sorted(entry_points)[:30],
        "configuration_files": sorted(configuration)[:40],
        "test_directories": tests[:30],
        "documentation": documentation,
    }
