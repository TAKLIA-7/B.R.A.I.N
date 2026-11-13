---
id: BUG-7f603d
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-13 12:58:39.868241+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-7f603d: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-18340b](../fixes/FIX-18340b.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
