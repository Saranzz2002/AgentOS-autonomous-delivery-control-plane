from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.llm.client import LLMClient
from backend.tools.filesystem import RepositoryFileError, resolve_repository_file

CODER_SYSTEM_PROMPT = """You are the Coding Agent inside AgentOS. Implement the provided engineering plan using only repository context supplied. Follow existing conventions, make the smallest safe changes, and do not invent APIs, files, dependencies, or frameworks. Never modify .env files, credentials, SSH keys, or system files. Do not provide shell commands. Do not claim tests pass. Return JSON {\"changes\":[{\"file\":\"relative/path\",\"action\":\"create|modify|patch\",\"reason\":\"...\",\"content\":\"complete file text for create/modify, unified diff text for patch\"}]}. Prefer precise, non-empty unified diffs for existing files, with exactly '--- a/relative/path' and '+++ b/relative/path' headers. Complete file text is allowed for action modify when a precise patch is unsuitable. Never return an empty patch. Do not modify unrelated files."""


class ProposedChange(BaseModel):
    file: str
    action: str
    reason: str = Field(min_length=1)
    content: str


class CodingOutput(BaseModel):
    changes: list[ProposedChange] = Field(min_length=1, max_length=20)


def _json_object(raw: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


def validate_changes(repo_path: str, output: CodingOutput) -> list[dict[str, Any]]:
    cleaned = []
    for change in output.changes:
        if change.action not in {"create", "modify", "patch"}:
            raise ValueError("Unsupported file change action.")
        path = PurePosixPath(change.file.replace("\\", "/"))
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RepositoryFileError("Generated path must stay inside the repository.")
        # Resolver also rejects secrets and symlink escapes.
        resolved = resolve_repository_file(repo_path, path.as_posix(), must_exist=change.action != "create")
        if change.action == "create" and resolved.exists():
            raise RepositoryFileError("Create action targets an existing file.")
        cleaned.append({"file": path.as_posix(), "action": change.action,
                        "reason": change.reason, "content": change.content})
    return cleaned


def generate_code(state: dict[str, Any], llm: LLMClient | None = None) -> list[dict[str, Any]]:
    client = llm or LLMClient()
    prompt = json.dumps({"task": state.get("task"), "context": state.get("context"),
                         "plan": state.get("plan"), "relevant_files": state.get("relevant_files"),
                         "debug_result": state.get("debug_result"),
                         "review_feedback": state.get("review_feedback")}, ensure_ascii=False)
    raw = client.generate(prompt, system_prompt=CODER_SYSTEM_PROMPT, json_mode=True)
    parsed: CodingOutput | None = None
    for attempt in range(2):
        try:
            parsed = CodingOutput.model_validate(_json_object(raw))
            break
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            if attempt:
                raise ValueError("Coding Agent returned invalid structured changes after one correction attempt.") from exc
            raw = client.generate(
                "Correct the previous response into exactly this JSON shape: "
                "{\"changes\":[{\"file\":\"relative/path\",\"action\":\"create|modify|patch\","
                "\"reason\":\"...\",\"content\":\"...\"}]}. Include at least one valid change, "
                "and preserve the requested implementation. Validation error: " + str(exc)[:1200]
                + "\nPrevious response:\n" + raw[:8_000],
                system_prompt=CODER_SYSTEM_PROMPT, json_mode=True,
            )
    assert parsed is not None
    return validate_changes(str(state["repo_path"]), parsed)


def regenerate_patch(state: dict[str, Any], change: dict[str, Any], error: str,
                     llm: LLMClient | None = None) -> dict[str, Any]:
    """Ask once for a fresh patch using the current target contents after apply failure."""
    from backend.tools.filesystem import read_file

    path = change["file"]
    current = read_file(str(state["repo_path"]), path)
    prompt = json.dumps({"task": state.get("task"), "plan": state.get("plan"),
                         "file": path, "current_file_content": current,
                         "previous_patch": change.get("content"), "application_error": error}, ensure_ascii=False)
    raw = (llm or LLMClient()).generate(
        prompt,
        system_prompt=("Return one corrected, non-empty unified diff for exactly the supplied file. "
                       "Use headers '--- a/relative/path' and '+++ b/relative/path'. "
                       "Do not return apply_patch markers, another file, or a full file replacement. JSON only: "
                       "{\"changes\":[{\"file\":\"same path\",\"action\":\"patch\",\"reason\":\"...\",\"content\":\"diff\"}]}."),
        json_mode=True,
    )
    try:
        parsed = CodingOutput.model_validate(_json_object(raw))
        if len(parsed.changes) != 1 or parsed.changes[0].file.replace("\\", "/") != path or parsed.changes[0].action != "patch" or not parsed.changes[0].content.strip():
            raise ValueError("Patch regeneration must return one non-empty patch for the same file.")
        return validate_changes(str(state["repo_path"]), parsed)[0]
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise ValueError("Coding Agent could not regenerate a valid patch.") from exc
