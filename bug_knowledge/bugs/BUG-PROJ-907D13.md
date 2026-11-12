---
id: BUG-PROJ-907D13
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
reported_by: qa-agent
first_seen: "2026-11-12 18:29:57.618575+00:00"
files: ['api.py']
symbols: []
---

# BUG-PROJ-907D13: Uncaught ValidationError on invalid payload

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
- [FIX-PROJ-6BFE47](../fixes/FIX-PROJ-6BFE47.md) by `qa-agent`: Added explicit RequestValidationError exception handler (Result: `passed`)
