---
id: BUG-DB-1d0b22
title: "Async DB connection pool exhausted under concurrent logins"
status: investigating
severity: high
reported_by: Agent A
first_seen: "2026-11-12 21:50:20.218309+00:00"
files: ['app/auth.py', 'app/db.py']
symbols: []
---

# BUG-DB-1d0b22: Async DB connection pool exhausted under concurrent logins

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
- **Status**: `investigating`

_No fixes recorded yet._
