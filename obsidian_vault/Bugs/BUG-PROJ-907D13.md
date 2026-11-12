---
id: BUG-PROJ-907D13
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
project: "General"
related_fix_id: "FIX-PROJ-6BFE47"
related_task_id: ""
---

# BUG-PROJ-907D13: Uncaught ValidationError on invalid payload

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `medium`
**Tags**: #bug #medium #bug/verified

## Symptoms and Reproduction
500 Internal Server Error instead of 422

## Root Cause
Missing FastAPI exception handler for Pydantic ValidationError

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-PROJ-6BFE47|FIX-PROJ-6BFE47]]