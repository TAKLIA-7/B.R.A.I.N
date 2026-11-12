---
id: BUG-TDD-DB72AE
title: "Async dead-lock in connection pool acquire"
status: verified
severity: high
reported_by: tester-agent
first_seen: "2026-11-12 18:29:57.114715+00:00"
files: ['core/db/session.py']
symbols: ['get_db_session']
---

# BUG-TDD-DB72AE: Async dead-lock in connection pool acquire

## Symptoms and Reproduction
Requests hang indefinitely under concurrent load

## Root Cause
Missing timeout on pool lock acquire

## Investigation Attempts
### Attempt 1 [FAILED] - debugger-agent
- **Hypothesis**: Threadpool queue full
- **Action Taken**: Increased max_workers
- **Learned / Next Steps**: Deadlock is at async lock level, not threadpool

### Attempt 2 [PARTIAL] - debugger-agent
- **Hypothesis**: Async lock not released on exception
- **Action Taken**: Wrapped in try-finally block
- **Learned / Next Steps**: Lock needs explicit timeout parameter

## Resolution and Verification
- **Status**: `verified`

### Related Fixes
- [FIX-TDD-8B30F1](../fixes/FIX-TDD-8B30F1.md) by `fixer-agent`: Added async timeout to pool acquire and enforced try-finally release (Result: `passed`)
