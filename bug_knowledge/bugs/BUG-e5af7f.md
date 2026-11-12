---
id: BUG-e5af7f
title: "JWT expiration off-by-one"
status: fixed
severity: high
reported_by: None
first_seen: "2026-11-12 21:49:32.371494+00:00"
files: ['app/jwt.py']
symbols: []
---

# BUG-e5af7f: JWT expiration off-by-one

## Symptoms and Reproduction
Token expires immediately

## Root Cause
Timezone UTC mismatch

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `fixed`

### Related Fixes
- [FIX-ce548d](../fixes/FIX-ce548d.md) by `Agent A`: Use datetime.now(timezone.utc) (Result: `passed`)
