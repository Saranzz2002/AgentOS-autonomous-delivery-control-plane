from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agents.context import retrieve_context
from backend.agents.planner import generate_plan
from backend.models.state import AgentState
from backend.services.repository_service import repository_service
from backend.agents.coder import generate_code, regenerate_patch, CodingOutput, ProposedChange, validate_changes
from backend.agents.debugger import analyze_failure
from backend.agents.runner import _apply_changes, MAX_ITERATIONS
from backend.tools.filesystem import get_git_diff, apply_patch, create_file, write_file, RepositoryFileError
from backend.tools.testing import run_tests
from backend.agents.reviewer import review_changes, MAX_REVIEW_ITERATIONS


def analyze_node(state: AgentState) -> dict[str, Any]:
    metadata = state.get("repository_metadata")
    if metadata:
        return {"status": "analyzed"}
    metadata = repository_service.analyze(state["repo_path"], state.get("repository_url"))
    return {
        "repository_metadata": metadata,
        "repository_tree": metadata["tree"],
        "important_files": metadata["important_files"],
        "status": "analyzed",
    }


def context_node(state: AgentState) -> dict[str, Any]:
    return retrieve_context(state)


def planner_node(state: AgentState) -> dict[str, Any]:
    return generate_plan(state)


def build_workflow():
    graph = StateGraph(AgentState)
    graph.add_node("analyze_repository", analyze_node)
    graph.add_node("retrieve_context", context_node)
    graph.add_node("generate_plan", planner_node)
    graph.add_edge(START, "analyze_repository")
    graph.add_edge("analyze_repository", "retrieve_context")
    graph.add_edge("retrieve_context", "generate_plan")
    graph.add_edge("generate_plan", END)
    return graph.compile()


planning_workflow = build_workflow()


def build_autonomous_workflow(*, emit, llm=None, tester=run_tests, reviewer=review_changes):
    """Create the bounded code/test/debug/review graph; human approval is resumed through the API."""
    def analyze(state):
        emit("repository.analyzing", "Analyzing cloned repository", 0)
        metadata = state.get("repository_metadata") or repository_service.analyze(state["repo_path"], state.get("repository_url"))
        emit("repository.analyzed", f"Detected {metadata['language']} / {metadata['framework']}", 0)
        return {"repository_metadata": metadata, "repository_tree": metadata["tree"],
                "important_files": metadata["important_files"]}

    def context(state):
        if state.get("context") and state.get("relevant_files"):
            return {"context": state["context"], "relevant_files": state["relevant_files"]}
        emit("context.searching", "Retrieving task relevant code")
        result = retrieve_context(state, llm)
        emit("context.selected", f"Selected {len(result.get('relevant_files', []))} files")
        return result

    def plan(state):
        if state.get("plan"):
            return {"plan": state["plan"]}
        emit("planner.started", "Generating structured implementation plan")
        result = generate_plan(state, llm)
        emit("planner.completed", "Implementation plan generated")
        return result

    def code(state):
        emit("coder.started", "Generating structured file changes", state.get("review_iteration", 0) + 1)
        changes = generate_code(state, llm)
        emit("coder.completed", f"Proposed {len(changes)} file change(s)", state.get("review_iteration", 0) + 1)
        return {"code_changes": changes, "iteration": 0, "test_status": "pending", "test_result": {}}

    def apply(state):
        emit("changes.applying", "Applying validated file changes", state.get("iteration", 0) + 1)
        applied = []
        for change in state["code_changes"]:
            if change["action"] == "patch":
                try:
                    apply_patch(state["repo_path"], change["file"], change["content"])
                except RepositoryFileError as exc:
                    repaired = regenerate_patch(state, change, str(exc), llm)
                    apply_patch(state["repo_path"], repaired["file"], repaired["content"])
                    change = repaired
            elif change["action"] == "create":
                create_file(state["repo_path"], change["file"], change["content"])
            else:
                write_file(state["repo_path"], change["file"], change["content"])
            applied.append(change)
        paths = [change["file"] for change in applied]
        emit("changes.applied", "Applied: " + ", ".join(paths), state.get("iteration", 0) + 1)
        return {"code_changes": applied, "git_diff": get_git_diff(state["repo_path"])["diff"]}

    def test(state):
        iteration = state.get("iteration", 0) + 1
        emit("tests.started", f"Running tests in Docker (attempt {iteration}/{MAX_ITERATIONS})", iteration)
        result = tester(state["repo_path"])
        output = (result.get("stdout", "") + "\n" + result.get("stderr", ""))[-40_000:]
        diff = get_git_diff(state["repo_path"])
        emit("tests.passed" if result.get("status") == "passed" and result.get("exit_code") == 0 else "tests.failed",
             result.get("summary", result.get("status", "Unknown test result")), iteration)
        return {"iteration": iteration, "test_output": output, "test_status": result.get("status"),
                "test_result": result, "git_diff": diff["diff"], "diff_result": diff}

    def debug(state):
        emit("debugger.started", "Analyzing actual test output", state["iteration"])
        diagnosis = analyze_failure(state, llm)
        emit("debugger.completed", diagnosis["root_cause"], state["iteration"])
        fixes = diagnosis["recommended_changes"]
        if fixes:
            validated = validate_changes(state["repo_path"], CodingOutput(
                changes=[ProposedChange.model_validate(item) for item in fixes]))
            if validated:
                return {"debug_result": diagnosis, "code_changes": validated}
        return {"debug_result": diagnosis, "code_changes": []}

    def fix(state):
        if not state.get("code_changes"):
            return {"status": "failed", "error": "Debugger produced no actionable fix"}
        emit("fix.applying", state["debug_result"]["fix_description"], state["iteration"])
        applied = []
        for change in state["code_changes"]:
            if change["action"] == "patch":
                try:
                    apply_patch(state["repo_path"], change["file"], change["content"])
                except RepositoryFileError as exc:
                    repaired = regenerate_patch(state, change, str(exc), llm)
                    apply_patch(state["repo_path"], repaired["file"], repaired["content"])
                    change = repaired
            elif change["action"] == "create":
                create_file(state["repo_path"], change["file"], change["content"])
            else:
                write_file(state["repo_path"], change["file"], change["content"])
            applied.append(change)
        paths = [change["file"] for change in applied]
        emit("fix.applied", "Applied debugger fix: " + ", ".join(paths), state["iteration"])
        return {"code_changes": applied, "git_diff": get_git_diff(state["repo_path"])["diff"]}

    def review(state):
        emit("review.started", "Reviewer examining the task, plan, diff, context, and actual test result",
             state.get("review_iteration", 0) + 1)
        result = reviewer(state, llm)
        review_iteration = state.get("review_iteration", 0) + 1
        recommendation = result["recommendation"]
        emit("review.completed", result["summary"], review_iteration)
        if recommendation == "APPROVE":
            emit("review.approved", result["summary"], review_iteration)
            emit("approval.requested", "Review passed; waiting for human approval", review_iteration)
            return {"review_result": result, "review_iteration": review_iteration,
                    "status": "WAITING_FOR_HUMAN_APPROVAL", "error": None}
        if recommendation == "CHANGES_REQUESTED" and review_iteration < MAX_REVIEW_ITERATIONS:
            feedback = json.dumps({"summary": result["summary"], "findings": result["findings"]}, ensure_ascii=False)
            emit("review.changes_requested", result["summary"], review_iteration)
            return {"review_result": result, "review_iteration": review_iteration,
                    "review_feedback": feedback, "status": "CHANGES_REQUESTED"}
        message = result["summary"] if recommendation == "REJECT" else "Review iteration limit reached"
        emit("review.rejected", message, review_iteration)
        return {"review_result": result, "review_iteration": review_iteration,
                "status": "REJECTED", "error": message}

    def test_route(state):
        if state.get("test_status") == "passed" and (state.get("test_result") or {}).get("exit_code") == 0:
            return "review"
        if state.get("test_status") in {"passed", "no_tests_detected", "unavailable"}:
            return "done"
        return "debug" if state.get("iteration", 0) < MAX_ITERATIONS else "done"

    def debug_route(state):
        return "apply_fix" if state.get("code_changes") else "done"

    def review_route(state):
        if state.get("status") == "CHANGES_REQUESTED" and state.get("review_iteration", 0) < MAX_REVIEW_ITERATIONS:
            return "coder"
        return "done"

    graph = StateGraph(AgentState)
    for name, node in (("analyze_repository", analyze), ("retrieve_context", context),
                       ("generate_plan", plan), ("coding_agent", code), ("apply_changes", apply),
                       ("run_tests", test), ("debugger_agent", debug), ("apply_fix", fix),
                       ("reviewer_agent", review)):
        graph.add_node(name, node)
    graph.add_edge(START, "analyze_repository")
    graph.add_edge("analyze_repository", "retrieve_context")
    graph.add_edge("retrieve_context", "generate_plan")
    graph.add_edge("generate_plan", "coding_agent")
    graph.add_edge("coding_agent", "apply_changes")
    graph.add_edge("apply_changes", "run_tests")
    graph.add_conditional_edges("run_tests", test_route, {"done": END, "debug": "debugger_agent", "review": "reviewer_agent"})
    graph.add_conditional_edges("debugger_agent", debug_route, {"done": END, "apply_fix": "apply_fix"})
    graph.add_edge("apply_fix", "run_tests")
    graph.add_conditional_edges("reviewer_agent", review_route, {"done": END, "coder": "coding_agent"})
    return graph.compile()
