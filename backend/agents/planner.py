from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from backend.llm.client import LLMClient, LLMNotConfigured
from backend.models.schemas import Plan

PLANNER_SYSTEM_PROMPT = """You are the planning agent inside AgentOS, an autonomous software delivery system. Your job is NOT to write code. Understand the engineering task and the repository context, then produce a precise plan for another coding agent. Use ONLY facts supported by the provided repository context. Do not invent files, functions, APIs, dependencies, or architecture. Prefer existing code patterns and the smallest safe change set. Return structured JSON matching these fields exactly: goal (string), assumptions (string[]), files_to_inspect/files_to_modify/files_to_create (arrays of {path, reason}), implementation_steps (array of {step: positive integer, description}), testing_strategy (string[]), risks (string[]), dependencies (string[]). Every file recommendation needs a reason. Paths must be relative repository paths without traversal. If a file does not exist yet, place it in files_to_create. The plan must be actionable. Do not include secrets or environment values."""


class PlannerError(ValueError):
    pass


def _json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Planner response did not contain a JSON object.")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Planner response must be a JSON object.")
    return value


def _validate_plan_paths(plan: Plan) -> Plan:
    for group in (plan.files_to_inspect, plan.files_to_modify, plan.files_to_create):
        for item in group:
            normalized = item.path.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or any(part in {"..", "."} for part in path.parts) or (path.parts and ":" in path.parts[0]):
                raise PlannerError("Planner returned a path outside the repository.")
            if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in path.parts):
                raise PlannerError("Planner returned a secret-file path.")
            item.path = path.as_posix()
    return plan


def generate_plan(state: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
    client = llm or LLMClient()
    prompt = state.get("context") or ""
    try:
        raw = client.generate(prompt, system_prompt=PLANNER_SYSTEM_PROMPT, json_mode=True)
        try:
            plan = Plan.model_validate(_json_object(raw))
        except (ValueError, ValidationError) as first_error:
            correction = (
                "Your previous response did not match the required JSON plan schema. "
                "Return a corrected JSON object only. Validation error: " + str(first_error)[:1200]
                + "\nPrevious response:\n" + raw[:8_000]
            )
            corrected = client.generate(correction, system_prompt=PLANNER_SYSTEM_PROMPT, json_mode=True)
            plan = Plan.model_validate(_json_object(corrected))
        plan = _validate_plan_paths(plan)
    except LLMNotConfigured:
        raise
    except Exception as exc:
        if isinstance(exc, PlannerError):
            raise
        raise PlannerError("Planner temporarily unavailable or returned an invalid plan.") from exc
    return {"plan": plan.model_dump(), "status": "planned"}
