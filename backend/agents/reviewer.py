from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from backend.llm.client import LLMClient
from backend.models.review import ReviewResult

MAX_REVIEW_ITERATIONS = 2

REVIEWER_SYSTEM_PROMPT = """You are the Code Reviewer Agent inside AgentOS. Review an AI generated change before a human can approve it. Inspect the original task, plan, relevant context, changed files, complete git diff, and actual test result. Evaluate task compliance, correctness, code quality, test sufficiency, security, maintainability, unnecessary changes, and regressions. Passing tests do not prove correctness. Do not modify code. Do not invent issues without evidence. Never request or infer environment variables, API keys, .env contents, credentials, or SSH keys. Return JSON matching the ReviewResult schema: recommendation (APPROVE, CHANGES_REQUESTED, REJECT), summary, four integer scores 0..10, findings (severity critical/high/medium/low/info; category correctness/security/testing/quality/maintainability/scope; file nullable; line nullable positive integer; description; recommendation), strengths, risks. Use CHANGES_REQUESTED for actionable fixable issues; REJECT for unsafe or fundamentally unsuitable changes; APPROVE only when no blocking concern remains."""


def _json_object(raw: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Reviewer response did not contain a JSON object.")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Reviewer response must be an object.")
    return value


def review_changes(state: dict[str, Any], llm: LLMClient | None = None) -> dict[str, Any]:
    result = state.get("test_result") or {}
    if state.get("test_status") != "passed" or result.get("exit_code") != 0:
        raise ValueError("Reviewer requires a real passing test result.")
    prompt = json.dumps({
        "task": state.get("task"),
        "plan": state.get("plan"),
        "repository": {key: (state.get("repository_metadata") or {}).get(key)
                       for key in ("name", "language", "framework", "test_framework")},
        "relevant_context": state.get("context", "")[:16_000],
        "changed_files": (state.get("diff_result") or {}).get("files_changed", []),
        "git_diff": (state.get("git_diff") or "")[:80_000],
        "test_result": {key: result.get(key) for key in
                        ("status", "exit_code", "duration", "summary", "stdout", "stderr")},
        "test_iterations": state.get("iteration", 0),
        "review_iteration": state.get("review_iteration", 0) + 1,
        "coding_decisions": [{"file": item.get("file"), "action": item.get("action"),
                               "reason": item.get("reason")}
                              for item in state.get("code_changes", [])],
        "revision_feedback": state.get("review_feedback"),
        "required_response_schema": ReviewResult.model_json_schema(),
    }, ensure_ascii=False)
    client = llm or LLMClient()
    raw = client.generate(prompt, system_prompt=REVIEWER_SYSTEM_PROMPT, json_mode=True)
    parsed: ReviewResult | None = None
    for attempt in range(3):
        try:
            parsed = ReviewResult.model_validate(_json_object(raw))
            break
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            if attempt == 2:
                raise ValueError(f"Reviewer returned invalid structured output: {str(exc)[:800]}") from exc
            raw = client.generate(
                "Correct the previous review into one valid JSON object. Preserve its evidence-based findings, "
                "but satisfy every required key and constraint. Required keys: recommendation, summary, "
                "task_compliance_score, code_quality_score, test_quality_score, security_score, findings, "
                "strengths, risks. All four scores must be integers from 0 through 10. Finding severity and "
                "category must use the allowed enums from the schema. Validation errors: " + str(exc)[:1600]
                + "\nPrevious response:\n" + raw[:8_000],
                system_prompt=REVIEWER_SYSTEM_PROMPT, json_mode=True,
            )
    assert parsed is not None
    changed_files = set((state.get("diff_result") or {}).get("files_changed", []))
    for finding in parsed.findings:
        if finding.file is not None and finding.file not in changed_files:
            raise ValueError("Reviewer finding refers to a file outside the changed-file list.")
    if any(item.severity == "critical" for item in parsed.findings):
        parsed.recommendation = "REJECT"
    elif any(item.severity == "high" for item in parsed.findings) and parsed.recommendation == "APPROVE":
        parsed.recommendation = "CHANGES_REQUESTED"
    return parsed.model_dump()
