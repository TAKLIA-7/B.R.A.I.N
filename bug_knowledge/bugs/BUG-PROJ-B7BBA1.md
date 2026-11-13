---
id: BUG-PROJ-B7BBA1
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
reported_by: qa-agent
first_seen: "2026-11-13 12:58:26.404910+00:00"
files: ['api.py']
symbols: []
---

# BUG-PROJ-B7BBA1: Uncaught ValidationError on invalid payload

## Symptoms and Reproduction
500 Internal Server Error instead of 422

## Root Cause
Missing FastAPI exception handler for Pydantic ValidationError

## Investigation Attempts
### Attempt 1 [FAILED] - qa-agent
- **Hypothesis**: FastAPI default handler disabled
- **Action Taken**: Inspected middleware stack
- **Learned / Next Steps**: 

## Resolution and Verification
- **Status**: `verified`

### Related Fixes
- [FIX-PROJ-8829A9](../fixes/FIX-PROJ-8829A9.md) by `qa-agent`: Added explicit RequestValidationError exception handler (Result: `passed`)
