---
id: BUG-TDD-FCA5B4
title: "Async dead-lock in connection pool acquire"
status: verified
severity: high
reported_by: tester-agent
first_seen: "2026-11-12 21:33:00.466750+00:00"
files: ['core/db/session.py']
symbols: ['get_db_session']
---

# BUG-TDD-FCA5B4: Async dead-lock in connection pool acquire

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
- [FIX-TDD-121868](../fixes/FIX-TDD-121868.md) by `fixer-agent`: Added async timeout to pool acquire and enforced try-finally release (Result: `passed`)
