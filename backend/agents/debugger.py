from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.agents.coder import ProposedChange
from backend.llm.client import LLMClient

DEBUGGER_SYSTEM_PROMPT = """You are the Debugger Agent inside AgentOS. Diagnose the actual test output and supplied repository context. Do not guess beyond evidence or rewrite unrelated code. Return JSON with root_cause, affected_files (relative paths), fix_description, and recommended_changes (same structured file change objects as the Coding Agent). Never claim tests pass."""


class DebugOutput(BaseModel):
    root_cause: str = Field(min_length=1)
    affected_files: list[str]
    fix_description: str = Field(min_length=1)
    recommended_changes: list[ProposedChange]


def analyze_failure(state: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
    prompt = json.dumps({key: state.get(key) for key in (
        "task", "plan", "context", "git_diff", "test_output", "test_status", "iteration"
    )}, ensure_ascii=False)
    client = llm or LLMClient()
    raw = client.generate(prompt, system_prompt=DEBUGGER_SYSTEM_PROMPT, json_mode=True)
    for attempt in range(2):
        try:
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
            payload = json.loads(text[text.find("{"):text.rfind("}") + 1])
            if "recommended_changes" not in payload and isinstance(payload.get("changes"), list):
                payload["recommended_changes"] = payload.pop("changes")
            data = DebugOutput.model_validate(payload)
            return data.model_dump()
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            if attempt:
                raise ValueError("Debugger returned invalid structured diagnosis.") from exc
            raw = client.generate(
                "Correct this response to match the required JSON schema exactly. Each recommended_changes item "
                "must contain file, action (create/modify/patch), reason, and content. Preserve the evidence-based "
                "diagnosis and do not invent changes. Validation error: " + str(exc)[:1000]
                + "\nPrevious response:\n" + raw[:6000],
                system_prompt=DEBUGGER_SYSTEM_PROMPT, json_mode=True,
            )
    raise ValueError("Debugger returned invalid structured diagnosis.")
