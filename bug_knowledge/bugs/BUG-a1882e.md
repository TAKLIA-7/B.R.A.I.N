---
id: BUG-a1882e
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-13 12:10:42.425313+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-a1882e: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-919ad5](../fixes/FIX-919ad5.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
