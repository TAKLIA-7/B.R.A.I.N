---
id: BUG-c20c94
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-13 12:51:37.963096+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-c20c94: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-4e3270](../fixes/FIX-4e3270.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
