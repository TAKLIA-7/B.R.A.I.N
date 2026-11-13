---
id: BUG-DB-c74c39
title: "Async DB connection pool exhausted under concurrent logins"
status: verified
severity: high
reported_by: Agent A
first_seen: "2026-11-13 04:41:07.628402+00:00"
files: ['app/auth.py', 'app/db.py']
symbols: []
---

# BUG-DB-c74c39: Async DB connection pool exhausted under concurrent logins

## Symptoms and Reproduction
psycopg2.OperationalError: connection pool exhausted

## Root Cause
Root cause not yet determined.

## Investigation Attempts
### Attempt 1 [FAILED] - Agent A
- **Hypothesis**: Increasing pool size to 50 will solve exhaustion
- **Action Taken**: pool_size = 50
- **Learned / Next Steps**: Exceeds max allowed connections in PostgreSQL

### Attempt 2 [FAILED] - Agent A
- **Hypothesis**: Disable pool and use single connection
- **Action Taken**: pool_size = 1
- **Learned / Next Steps**: Causes massive latency bottleneck under load

## Resolution and Verification
- **Status**: `verified`

### Related Fixes
- [FIX-DB-a90468](../fixes/FIX-DB-a90468.md) by `Agent A`: Implement async connection pooling with auto-recycling and context managers (Result: `passed`)
