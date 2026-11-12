---
id: BUG-SCENARIO-BC1F
title: "Pydantic ValidationError returned as 500 in task API"
status: verified
severity: medium
project: "General"
related_fix_id: "FIX-SCENARIO-99E2"
related_task_id: ""
---

# BUG-SCENARIO-BC1F: Pydantic ValidationError returned as 500 in task API

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `medium`
**Tags**: #bug #medium #bug/verified

## Symptoms and Reproduction
Invalid payload returns internal server error instead of 422 Unprocessable Content

## Root Cause
FastAPI handler missing custom exception mapping

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-SCENARIO-99E2|FIX-SCENARIO-99E2]]