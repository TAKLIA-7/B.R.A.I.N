---
id: BUG-PROJ-4D597B
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
reported_by: qa-agent
first_seen: "2026-11-12 21:41:42.527765+00:00"
files: ['api.py']
symbols: []
---

# BUG-PROJ-4D597B: Uncaught ValidationError on invalid payload

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
- [FIX-PROJ-2E954E](../fixes/FIX-PROJ-2E954E.md) by `qa-agent`: Added explicit RequestValidationError exception handler (Result: `passed`)
