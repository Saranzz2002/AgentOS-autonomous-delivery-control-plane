from __future__ import annotations

import subprocess
import time
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 120
PYTHON_IMAGE = "agentos-python-sandbox:latest"
OMIT_DIRS = {".git", ".ssh", ".aws", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build", "coverage"}
OMIT_FILES = {"id_rsa", "id_ed25519", "known_hosts", "credentials", "credentials.json", "secrets.json"}


def _copy_safe_workspace(source: Path, destination: Path) -> None:
    """Copy repository source while excluding credentials, caches, and links."""
    for current, dirs, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        omitted_dirs = {name.lower() for name in OMIT_DIRS}
        dirs[:] = [name for name in dirs
                   if name.lower() not in omitted_dirs and not (current_path / name).is_symlink()
                   and not ((current_path / name).is_junction() if hasattr((current_path / name), "is_junction") else False)]
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            source_file = current_path / name
            lower = name.lower()
            if source_file.is_symlink() or (hasattr(source_file, "is_junction") and source_file.is_junction()):
                continue
            if (lower in OMIT_FILES or lower.startswith(("id_rsa", "id_ed25519", "credentials", "credential", "secret"))
                    or lower in {".npmrc", ".pypirc", ".netrc", ".git-credentials", "service-account.json"}
                    or lower == ".env" or lower.startswith(".env.")):
                continue
            if Path(lower).suffix in {".pem", ".key", ".p12", ".pfx", ".pyc", ".pyo"}:
                continue
            shutil.copy2(source_file, target_dir / name)


def _ensure_python_image() -> None:
    inspected = subprocess.run(["docker", "image", "inspect", PYTHON_IMAGE],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=20, check=False)
    if inspected.returncode == 0:
        return
    dockerfile = Path(__file__).resolve().parents[2] / "sandbox"
    built = subprocess.run(["docker", "build", "--tag", PYTHON_IMAGE, str(dockerfile)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=240, check=False)
    if built.returncode:
        raise RuntimeError("Could not build AgentOS test image: " + built.stderr[-1000:])


def run_in_sandbox(repo_path: str | Path, command: list[str], *, image: str,
                   timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a fixed, detected test command with Docker isolation and no network."""
    started = time.monotonic()
    root = Path(repo_path).resolve()
    if not root.is_dir():
        return {"status": "failed", "exit_code": None, "duration": 0.0,
                "stdout": "", "stderr": "Repository workspace does not exist.", "summary": "Sandbox setup failed"}
    if image == PYTHON_IMAGE:
        try:
            _ensure_python_image()
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return {"status": "unavailable", "exit_code": None, "duration": round(time.monotonic() - started, 2),
                    "stdout": "", "stderr": str(exc)[:1000], "summary": "Could not prepare Docker test image"}
    try:
        staging_context = tempfile.TemporaryDirectory(prefix="agentos-sandbox-", dir=root.parent)
        staged_root = Path(staging_context.name)
        _copy_safe_workspace(root, staged_root)
    except OSError as exc:
        return {"status": "unavailable", "exit_code": None, "duration": round(time.monotonic() - started, 2),
                "stdout": "", "stderr": str(exc)[:1000], "summary": "Could not prepare safe sandbox workspace"}
    docker_command = [
        "docker", "run", "--rm", "--network", "none", "--cpus", "1", "--memory", "1g",
        "--pids-limit", "128", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        "--mount", f"type=bind,source={staged_root},target=/workspace", "--workdir", "/workspace",
        image, *command,
    ]
    try:
        result = subprocess.run(docker_command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=timeout, check=False)
        duration = round(time.monotonic() - started, 2)
        output = (result.stdout + "\n" + result.stderr).strip()
        status = "passed" if result.returncode == 0 else "failed"
        summary = "Tests passed" if status == "passed" else (output[-500:] or f"Container exited {result.returncode}")
        staging_context.cleanup()
        return {"status": status, "exit_code": result.returncode, "duration": duration,
                "stdout": result.stdout[-20_000:], "stderr": result.stderr[-20_000:], "summary": summary}
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 2)
        staging_context.cleanup()
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {"status": "timeout", "exit_code": None, "duration": duration,
                "stdout": stdout[-20_000:], "stderr": stderr[-20_000:],
                "summary": f"Test execution exceeded {timeout} seconds"}
    except FileNotFoundError:
        staging_context.cleanup()
        return {"status": "unavailable", "exit_code": None, "duration": 0.0,
                "stdout": "", "stderr": "Docker CLI is unavailable.", "summary": "Docker sandbox unavailable"}
    except OSError as exc:
        staging_context.cleanup()
        return {"status": "unavailable", "exit_code": None, "duration": 0.0,
                "stdout": "", "stderr": str(exc)[:1000], "summary": "Docker sandbox unavailable"}
