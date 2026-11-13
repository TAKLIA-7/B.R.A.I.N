---
id: BUG-1c9ca5
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-13 04:38:31.149863+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-1c9ca5: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-662b2b](../fixes/FIX-662b2b.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
