---
id: BUG-SCENARIO-17D7
title: "Pydantic ValidationError returned as 500 in task API"
status: verified
severity: medium
reported_by: agent-B
first_seen: "2026-11-13 13:01:36.714674+00:00"
files: ['api.py']
symbols: ['create_task_checkpoint']
---

# BUG-SCENARIO-17D7: Pydantic ValidationError returned as 500 in task API

## Symptoms and Reproduction
Invalid payload returns internal server error instead of 422 Unprocessable Content

## Root Cause
FastAPI handler missing custom exception mapping

## Investigation Attempts
### Attempt 1 [FAILED] - agent-B
- **Hypothesis**: Try catching broad Exception in endpoint
- **Action Taken**: Wrapped in generic try/except
- **Learned / Next Steps**: Must catch RequestValidationError specifically

### Attempt 2 [PARTIAL] - agent-B
- **Hypothesis**: Add RequestValidationError handler
- **Action Taken**: Added handler to FastAPI app
- **Learned / Next Steps**: 

## Resolution and Verification
- **Status**: `verified`

### Related Fixes
- [FIX-SCENARIO-E2E7](../fixes/FIX-SCENARIO-E2E7.md) by `agent-B`: Registered FastAPI validation error handler returning 422 with detailed errors (Result: `passed`)
