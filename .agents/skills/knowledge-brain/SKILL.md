---
name: knowledge-brain
description: Interact with Knowledge Brain persistent memory, task checkpoints, defect history, and project requirements. Trigger whenever working with task handovers, bug fixes, or project context.
---

# Knowledge Brain Skill

This skill connects the agent directly to the Knowledge Brain MCP tools for persistent memory, task resumption, defect investigation, and dynamic project evolution.

## Available MCP Tools

### 1. Memory & Decisions
- `memory_search(query, token_budget)`: Semantic search over facts, rules, and decisions in PostgreSQL / pgvector.
- `memory_store(content, type, source_actor)`: Ingest new facts or architectural decisions.

### 2. Task Resumption & Checkpoints
- `task_checkpoint(task_id, goal, steps, decisions, written_by)`: Save durable progress and decisions.
- `task_resume(task_id, requesting_agent)`: Load compact handover package and check for task staleness.

### 3. Defect Memory & Prevention
- `bug_search(query)`: Search past defects and verified fixes before debugging.
- `bug_report(bug_id, title, symptom, severity)`: File a new defect.
- `bug_log_attempt(bug_id, agent, hypothesis, action, outcome)`: Log investigation attempts.
- `bug_record_fix(fix_id, bug_id, commit, files_changed, summary, verification, fixed_by)`: Save verified fix.

### 4. Dynamic Project Evolution
- `project_register(id, name, description)`: Scaffold project knowledge base.
- `project_context(project_id, task)`: Retrieve architecture, tech stack, and active specs.
- `requirement_propose(req_id, title, proposed_description, category)`: Propose requirements.
- `requirement_approve(req_id, target_version, decision, approver)`: Approve requirements and propagate staleness.

