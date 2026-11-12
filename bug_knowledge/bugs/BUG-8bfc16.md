---
id: BUG-8bfc16
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-12 22:15:07.355522+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-8bfc16: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-0aa4f1](../fixes/FIX-0aa4f1.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
