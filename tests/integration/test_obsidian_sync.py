import os
import shutil
import pytest
import psycopg2
from core.config import settings
from core.adapters.postgres import PostgresAdapter
from core.consolidation.obsidian import ObsidianVaultExporter

@pytest.fixture
def temp_vault_dir(tmp_path):
    vault = tmp_path / "integration_vault"
    vault.mkdir()
    yield str(vault)
    if os.path.exists(vault):
        shutil.rmtree(vault, ignore_errors=True)

def test_obsidian_sync_from_real_postgres(temp_vault_dir):
    """
    Verify ObsidianVaultExporter reads canonical records from PostgreSQL,
    generates structured Markdown files with wiki-links, and updates Home.md.
    """
    pg = PostgresAdapter()
    exporter = ObsidianVaultExporter(vault_path=temp_vault_dir, postgres_adapter=pg)

    # Ingest a test memory into PostgreSQL
    with pg.get_connection() as conn:
        with conn.cursor() as cur:
            # Source
            cur.execute("""
                INSERT INTO sources (id, type, actor, trust_level)
                VALUES ('a0000000-0000-0000-0000-000000000001', 'system', 'tester', 0.95)
                ON CONFLICT (id) DO NOTHING;
            """)
            # Memory
            cur.execute("""
                INSERT INTO memories (id, source_id, type, subject, text, epistemic_state, status)
                VALUES ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'decision', 'ObsidianIntegration', 'Vault projection must be idempotent', 'confirmed', 'active')
                ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text;
            """)
            # Task
            cur.execute("""
                INSERT INTO tasks (id, goal, created_by)
                VALUES ('task-obsidian-sync', 'Verify Obsidian integration', 'test-runner')
                ON CONFLICT (id) DO UPDATE SET goal = EXCLUDED.goal;
            """)
            # Bug
            cur.execute("""
                INSERT INTO bugs (bug_id, title, status, severity, symptom, root_cause, location)
                VALUES ('BUG-999', 'Vault sync missing file', 'fixed', 'low', 'File not created', 'Directory missing', '{"project": "ObsidianIntegration"}'::jsonb)
                ON CONFLICT (bug_id) DO UPDATE SET status = EXCLUDED.status;
            """)
            # Fix
            cur.execute("""
                INSERT INTO fixes (fix_id, bug_id, summary, fixed_by, verification)
                VALUES ('FIX-999', 'BUG-999', 'Create parent directory on write', 'Agent-A', '{"result": "passed", "output": "Directory auto-created"}'::jsonb)
                ON CONFLICT (fix_id) DO NOTHING;
            """)

    # Run sync
    sync_result = exporter.sync_from_postgres()
    assert sync_result["status"] == "success"
    assert sync_result["counts"]["memories"] >= 1
    assert sync_result["counts"]["bugs"] >= 1
    assert sync_result["counts"]["fixes"] >= 1
    assert sync_result["counts"]["tasks"] >= 1

    # Verify generated files exist
    assert os.path.exists(os.path.join(temp_vault_dir, "Home.md"))
    mem_file = os.path.join(temp_vault_dir, "Memories", "b0000000-0000-0000-0000-000000000001.md")
    bug_file = os.path.join(temp_vault_dir, "Bugs", "BUG-999.md")
    fix_file = os.path.join(temp_vault_dir, "Fixes", "FIX-999.md")
    task_file = os.path.join(temp_vault_dir, "Tasks", "task-obsidian-sync.md")

    assert os.path.exists(mem_file)
    assert os.path.exists(bug_file)
    assert os.path.exists(fix_file)
    assert os.path.exists(task_file)

    # Check content and wiki-links
    with open(bug_file, "r", encoding="utf-8") as f:
        bug_content = f.read()
        assert "BUG-999" in bug_content
        assert "[[Fixes/FIX-999|FIX-999]]" in bug_content

    with open(fix_file, "r", encoding="utf-8") as f:
        fix_content = f.read()
        assert "FIX-999" in fix_content
        assert "[[Bugs/BUG-999|BUG-999]]" in fix_content
        assert "Directory auto-created" in fix_content

    # Re-syncing should succeed and be idempotent
    resync_result = exporter.sync_from_postgres()
    assert resync_result["status"] == "success"

def test_backend_operates_when_obsidian_fails():
    """
    Verify that if the vault path is invalid or unwritable,
    the exporter catches the error, logs it, and does not crash or raise exceptions.
    """
    invalid_path = "Z:\\non_existent_drive_or_unreachable_dir_xyz"
    exporter = ObsidianVaultExporter(vault_path=invalid_path)
    result = exporter.sync_from_postgres()
    assert result["status"] == "error"
    assert "error" in result
