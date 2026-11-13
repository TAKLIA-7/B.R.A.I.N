---
id: BUG-PROJ-906495
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
reported_by: qa-agent
first_seen: "2026-11-13 13:04:14.288562+00:00"
files: ['api.py']
symbols: []
---

# BUG-PROJ-906495: Uncaught ValidationError on invalid payload

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
- [FIX-PROJ-580BFF](../fixes/FIX-PROJ-580BFF.md) by `qa-agent`: Added explicit RequestValidationError exception handler (Result: `passed`)
