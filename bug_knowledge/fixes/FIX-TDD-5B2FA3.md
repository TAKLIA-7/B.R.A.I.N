---
id: FIX-TDD-5B2FA3
bug_id: BUG-TDD-6CF6D1
commit: "abc1234"
fixed_by: fixer-agent
created_at: "2026-11-12 21:30:28.056349+00:00"
files_changed: ['core/db/session.py']
---

# Fix FIX-TDD-5B2FA3 for [BUG-TDD-6CF6D1](../bugs/BUG-TDD-6CF6D1.md)

## Summary
Added async timeout to pool acquire and enforced try-finally release

## Files Changed
- `core/db/session.py`

## Verification Evidence
- **Tests Executed**: `pytest tests/integration/test_infrastructure.py`
- **Result**: `passed`
- **Run ID**: `run-99`

