---
id: BUG-9654be
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-12 22:01:24.430515+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-9654be: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-e770c7](../fixes/FIX-e770c7.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
