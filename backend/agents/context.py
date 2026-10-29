from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.llm.client import LLMClient
from backend.tools.filesystem import RepositoryFileError, read_file
from backend.tools.search import search_code_many

STOP_WORDS = {
    "about", "after", "also", "and", "add", "all", "any", "are", "based", "build",
    "create", "does", "for", "from", "have", "into", "make", "need", "only", "should",
    "that", "the", "their", "this", "through", "with", "within", "your", "test", "tests",
}
CONTEXT_SYSTEM_PROMPT = """You are the repository context selector for AgentOS. Choose the smallest useful set of files for the engineering task. Use only the candidate file paths and summaries provided. Return JSON only in this shape: {\"relevant_files\":[\"relative/path\"]}. Never invent paths. Do not request secrets, environment files, credentials, or unrelated host files."""


def _task_terms(task: str) -> list[str]:
    terms = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", task.lower())
    return list(dict.fromkeys(term for term in terms if term not in STOP_WORDS))[:18]


def _candidate_paths(repo_path: str, task: str, metadata: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for path in metadata.get("important_files", {}).get("entry_points", []):
        candidates.append(path)
    for path in metadata.get("important_files", {}).get("configuration_files", []):
        candidates.append(path)
    for path in metadata.get("important_files", {}).get("documentation", []):
        candidates.append(path)
    terms = _task_terms(task)
    for hit in search_code_many(repo_path, terms, limit=120):
        candidates.append(str(hit["file"]))
    tree = metadata.get("tree", [])
    candidates.extend(path for path in tree if "test" in Path(path).name.lower() or "test" in {p.lower() for p in Path(path).parts[:-1]})
    return list(dict.fromkeys(candidates))[:40]


def retrieve_context(state: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
    repo_path = str(state["repo_path"])
    task = str(state["task"])
    metadata = state.get("repository_metadata") or {}
    candidates = _candidate_paths(repo_path, task, metadata)
    summaries: list[dict[str, str]] = []
    deterministic_order: list[str] = []
    terms = _task_terms(task)
    for path in candidates:
        try:
            content = read_file(repo_path, path, max_bytes=32_000)
        except RepositoryFileError:
            continue
        score = sum(term in path.lower() for term in terms) * 4 + sum(term in content.lower() for term in terms)
        deterministic_order.append(path)
        summaries.append({"path": path, "summary": " ".join(content.split())[:800], "score": str(score)})
    summaries.sort(key=lambda item: (int(item["score"]), item["path"]), reverse=True)
    candidates = [item["path"] for item in summaries]
    if not candidates:
        selected = []
    else:
        selector = llm or LLMClient()
        prompt = json.dumps({
            "task": task,
            "repository": {key: value for key, value in metadata.items() if key not in {"tree", "repository_url"}},
            "candidates": [{"path": item["path"], "summary": item["summary"]} for item in summaries[:20]],
        }, ensure_ascii=False)
        try:
            raw = selector.generate(prompt, system_prompt=CONTEXT_SYSTEM_PROMPT, json_mode=True)
            payload = json.loads(raw)
            ranked = payload.get("relevant_files", []) if isinstance(payload, dict) else []
            selected = [path for path in ranked if isinstance(path, str) and path in candidates][:8]
        except (ValueError, TypeError, AttributeError):
            selected = []
        if not selected:
            selected = candidates[:8]

    sections = [
        f"Task: {task}",
        "Repository facts: " + json.dumps({key: value for key, value in metadata.items() if key not in {"tree", "repository_url"}}, ensure_ascii=False),
        "Relevant repository files:",
    ]
    total_chars = 0
    for path in selected:
        try:
            content = read_file(repo_path, path, max_bytes=24_000)
        except RepositoryFileError:
            continue
        clipped = content[:8_000]
        if total_chars + len(clipped) > 28_000:
            break
        sections.append(f"\n--- {path} ---\n{clipped}")
        total_chars += len(clipped)
    return {
        "relevant_files": selected,
        "context": "\n".join(sections),
        "context_summary": {"candidate_count": len(candidates), "selected_files": selected},
    }
