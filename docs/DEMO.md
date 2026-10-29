# AgentOS Hackathon Demo (3–5 minutes)

## Before the presentation

- Start Docker Desktop and confirm its Linux engine is running.
- Set `GROQ_API_KEY` in the root `.env`.
- Start the API and frontend using the commands in the root README.
- Open http://localhost:3000 and keep the dashboard visible.
- Use the public, minimal baseline `https://github.com/octocat/Hello-World`.

**Task to paste:**

> Add a small stdlib-only Python WSGI application with a GET /health endpoint returning JSON `{status: ok}`. Add pytest tests for the successful health response and a 404 for another path. Do not add external dependencies.

## Presenter script

### 0:00 — The problem

“AI coding agents can write code, but writing code is not the same as shipping reliable software. A delivery system also needs repository context, testing, review, and a responsible final decision.”

### 0:25 — AgentOS

“AgentOS is the control plane around a coding agent. It shows each stage and keeps test execution inside a constrained Docker sandbox.”

Point out the pipeline and the human approval requirement in the dashboard.

### 0:45 — Submit the task

Enter the repository URL and task above, then choose **Start autonomous run**. Explain that the baseline is intentionally small and public so the demo stays reproducible.

### 1:00 — Repository understanding and plan

Show repository analysis, selected context, and the generated plan in the activity log. The minimal baseline may have few source files to select; explain that AgentOS still maps the repository and plans the requested addition.

### 1:25 — Code and tests

Show the coding and apply events, then the actual Docker test result and captured pytest output. The example run should create the WSGI app and tests, then report the test process exit code. Never claim a test passed without a zero exit code.

If a real test failure occurs, show the failure output, debugger diagnosis, applied fix, and subsequent test attempt. Do not manufacture a failure for the presentation; if this run passes first try, explain that the retry loop is available and show its bounded-attempt indicator.

### 2:20 — Review the change

Show the changed-file list and diff, then the Reviewer recommendation, four scores, findings, strengths, and risks. Explain that the Reviewer only runs after tests pass and that an AI approval is not the final gate.

### 3:00 — Human approval

Read the review summary. Use **Reject / Request changes** with a specific comment if demonstrating revision, then show the coding, tests, and review cycle return. Otherwise choose **Approve & mark ready to ship**.

### 3:45 — Close

Show `READY_TO_SHIP` and say: “AgentOS verifies the change and keeps a human in the approval loop. Ready to ship is a gate; this demo does not deploy or merge code.”

## Reset between demos

Run records are in memory. Stop and restart the backend to clear the dashboard's run history, then refresh the frontend. Existing clones under `workspaces/` are ignored and can be left in place; a new run gets a new workspace. Do not remove a workspace while a run is using it.
