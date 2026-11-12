import os
import shutil
import pytest
from core.consolidation.obsidian import ObsidianVaultExporter

@pytest.fixture
def temp_vault_dir(tmp_path):
    vault = tmp_path / "test_vault"
    vault.mkdir()
    yield str(vault)
    if os.path.exists(vault):
        shutil.rmtree(vault, ignore_errors=True)

def test_format_memory_note():
    exporter = ObsidianVaultExporter(vault_path="dummy")
    memory = {
        "memory_id": "mem-12345",
        "memory_type": "decision",
        "title": "Use PostgreSQL with pgvector",
        "content": "PostgreSQL with pgvector selected as primary canonical store.",
        "epistemic_state": "confirmed",
        "trust_score": 0.95,
        "tags": ["architecture", "storage"],
        "project": "KnowledgeBrain",
        "source_id": "src-001"
    }
    
    note_content = exporter.format_memory_note(memory)
    assert "---" in note_content
    assert "id: mem-12345" in note_content
    assert "type: decision" in note_content
    assert "epistemic_state: confirmed" in note_content
    assert "#decision" in note_content
    assert "[[Projects/KnowledgeBrain|KnowledgeBrain]]" in note_content
    assert "Use PostgreSQL with pgvector" in note_content

def test_format_bug_and_fix_notes():
    exporter = ObsidianVaultExporter(vault_path="dummy")
    bug = {
        "bug_id": "BUG-042",
        "title": "Database connection pool exhaustion",
        "status": "resolved",
        "severity": "high",
        "symptom": "Connection timeouts under load",
        "root_cause": "Unclosed cursors in worker threads",
        "related_fix_id": "FIX-042",
        "related_task_id": "TASK-100"
    }
    
    bug_note = exporter.format_bug_note(bug)
    assert "id: BUG-042" in bug_note
    assert "[[Fixes/FIX-042|FIX-042]]" in bug_note
    assert "[[Tasks/TASK-100|TASK-100]]" in bug_note
    assert "#bug/resolved" in bug_note

    fix = {
        "fix_id": "FIX-042",
        "bug_id": "BUG-042",
        "summary": "Implement context manager for cursors",
        "fixed_by": "Agent-A",
        "verification_result": "passed",
        "verification_output": "100 concurrent workers ran with 0 leaks"
    }
    
    fix_note = exporter.format_fix_note(fix)
    assert "id: FIX-042" in fix_note
    assert "[[Bugs/BUG-042|BUG-042]]" in fix_note
    assert "#fix/verified" in fix_note
    assert "100 concurrent workers ran with 0 leaks" in fix_note

def test_idempotent_export(temp_vault_dir):
    exporter = ObsidianVaultExporter(vault_path=temp_vault_dir)
    
    memories = [
        {
            "memory_id": "mem-001",
            "memory_type": "fact",
            "title": "Redis TTL policy",
            "content": "Redis TTL is enforced at 3600 seconds.",
            "epistemic_state": "confirmed",
            "trust_score": 0.9,
            "tags": ["redis", "ttl"],
            "project": "KnowledgeBrain"
        }
    ]
    bugs = [
        {
            "bug_id": "BUG-001",
            "title": "Stale cache read",
            "status": "resolved",
            "severity": "medium",
            "symptom": "Returned stale key after update",
            "root_cause": "Missing invalidation hook",
            "related_fix_id": "FIX-001"
        }
    ]
    fixes = [
        {
            "fix_id": "FIX-001",
            "bug_id": "BUG-001",
            "summary": "Invalidate cache on write",
            "fixed_by": "Agent-B",
            "verification_result": "passed"
        }
    ]
    tasks = [
        {
            "task_id": "TASK-001",
            "description": "Implement cache layer",
            "status": "completed",
            "project": "KnowledgeBrain"
        }
    ]

    # First export
    res1 = exporter.export_all_records(
        memories=memories,
        bugs=bugs,
        fixes=fixes,
        tasks=tasks
    )
    assert res1["exported_files"] > 0
    assert os.path.exists(os.path.join(temp_vault_dir, "Home.md"))
    assert os.path.exists(os.path.join(temp_vault_dir, "Memories", "mem-001.md"))
    assert os.path.exists(os.path.join(temp_vault_dir, "Bugs", "BUG-001.md"))
    assert os.path.exists(os.path.join(temp_vault_dir, "Fixes", "FIX-001.md"))
    assert os.path.exists(os.path.join(temp_vault_dir, "Tasks", "TASK-001.md"))
    assert os.path.exists(os.path.join(temp_vault_dir, "Projects", "KnowledgeBrain.md"))

    # Read content from first export
    with open(os.path.join(temp_vault_dir, "Memories", "mem-001.md"), "r", encoding="utf-8") as f:
        content_1 = f.read()

    # Second export (must be completely idempotent)
    res2 = exporter.export_all_records(
        memories=memories,
        bugs=bugs,
        fixes=fixes,
        tasks=tasks
    )
    assert res2["exported_files"] == res1["exported_files"]

    with open(os.path.join(temp_vault_dir, "Memories", "mem-001.md"), "r", encoding="utf-8") as f:
        content_2 = f.read()

    assert content_1 == content_2

def test_graceful_handling_when_vault_disabled():
    exporter = ObsidianVaultExporter(vault_path=None)
    result = exporter.sync_from_postgres()
    assert result["status"] == "skipped"
    assert "Vault path is not configured" in result["message"]
