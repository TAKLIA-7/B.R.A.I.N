---
id: FIX-TDD-A23A54
bug_id: BUG-TDD-0A0B3B
commit: "abc1234"
fixed_by: fixer-agent
created_at: "2026-11-13 12:58:26.170921+00:00"
files_changed: ['core/db/session.py']
---

# Fix FIX-TDD-A23A54 for [BUG-TDD-0A0B3B](../bugs/BUG-TDD-0A0B3B.md)

## Summary
Added async timeout to pool acquire and enforced try-finally release

## Files Changed
- `core/db/session.py`

## Verification Evidence
- **Tests Executed**: `pytest tests/integration/test_infrastructure.py`
- **Result**: `passed`
- **Run ID**: `run-99`

