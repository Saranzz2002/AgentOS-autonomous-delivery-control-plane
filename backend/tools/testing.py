from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.tools.sandbox import DEFAULT_TIMEOUT, PYTHON_IMAGE, run_in_sandbox


def detect_test_command(repo_path: str | Path) -> tuple[str, list[str], str] | None:
    root = Path(repo_path)
    if (root / "package.json").is_file():
        try:
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(package.get("scripts"), dict) and package["scripts"].get("test"):
            # The project-owned script executes only inside the isolated container.
            return "node", ["npm", "test"], "node:22-bookworm-slim"
    has_python_tests = any((root / name).is_dir() for name in ("tests", "test"))
    if not has_python_tests:
        ignored = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if name not in ignored]
            if any(name.lower().startswith(("test_", "test.")) and name.lower().endswith(".py") for name in files):
                has_python_tests = True
                break
    pytest_config = any((root / name).is_file() for name in ("pytest.ini", "pyproject.toml", "tox.ini"))
    if (root / "requirements.txt").is_file() or pytest_config or has_python_tests:
        if has_python_tests or pytest_config:
            return "python", ["python", "-m", "pytest", "-q"], PYTHON_IMAGE
    return None


def run_tests(repo_path: str | Path, *, timeout: int = DEFAULT_TIMEOUT,
              runner=run_in_sandbox) -> dict[str, Any]:
    detected = detect_test_command(repo_path)
    if detected is None:
        return {"status": "no_tests_detected", "exit_code": None, "duration": 0.0,
                "stdout": "", "stderr": "", "summary": "No supported test framework detected"}
    _kind, command, image = detected
    return runner(repo_path, command, image=image, timeout=timeout)
