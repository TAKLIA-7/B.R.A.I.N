# Knowledge Brain Autonomous Agent Directives

You are equipped with the **Knowledge Brain** MCP server (`knowledge-brain`).
Operate **autonomously in the background** during normal software development conversations without requiring the user to explicitly name MCP tools or file formats.

### 1. New Project & Feature Requests (e.g. "Create a todo app using React and Node.js")
- Automatically register or check the project using `project_register` or `project_context`.
- Formulate the feature specification and log it via `requirement_propose` (and `requirement_approve` if clear).
- Save architectural decisions (framework choices, libraries, database models) via `memory_store`.
- After generating code or completing milestones, call `task_checkpoint` to save progress, completed steps, and pending steps.

### 2. Resuming & Continuing Work (e.g. "Continue where we left off", "What's next?")
- Automatically call `task_resume` to retrieve the latest checkpoint, decisions, and pending steps.
- Inspect whether any requirement changed (`is_stale`) and advise the user accordingly.

### 3. Debugging & Error Fixing (e.g. "Why is this failing?", "Fix this error")
- Before debugging, call `bug_search` to check if a fix for this error already exists in memory.
- If it is a new bug, file it via `bug_report`.
- Once resolved, record the verified fix using `bug_record_fix` so future agents benefit.

### 4. Scope Changes (e.g. "Now add priorities and due dates to our todos")
- Treat this as requirement evolution: call `requirement_propose` to record the delta as Version 2.
- Check if active tasks are affected using `requirement_check_staleness`.
