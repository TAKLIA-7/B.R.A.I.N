---
id: BUG-PROJ-6FBC22
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
project: "General"
related_fix_id: "FIX-PROJ-71D9CB"
related_task_id: ""
---

# BUG-PROJ-6FBC22: Uncaught ValidationError on invalid payload

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `medium`
**Tags**: #bug #medium #bug/verified

## Symptoms and Reproduction
500 Internal Server Error instead of 422

## Root Cause
Missing FastAPI exception handler for Pydantic ValidationError

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-PROJ-71D9CB|FIX-PROJ-71D9CB]]