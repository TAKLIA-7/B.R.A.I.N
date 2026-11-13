---
id: FIX-TDD-E5AA17
bug_id: BUG-TDD-BCDCD9
commit: "abc1234"
fixed_by: fixer-agent
created_at: "2026-11-13 12:51:25.509513+00:00"
files_changed: ['core/db/session.py']
---

# Fix FIX-TDD-E5AA17 for [BUG-TDD-BCDCD9](../bugs/BUG-TDD-BCDCD9.md)

## Summary
Added async timeout to pool acquire and enforced try-finally release

## Files Changed
- `core/db/session.py`

## Verification Evidence
- **Tests Executed**: `pytest tests/integration/test_infrastructure.py`
- **Result**: `passed`
- **Run ID**: `run-99`

