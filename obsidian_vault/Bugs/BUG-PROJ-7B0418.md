---
id: BUG-PROJ-7B0418
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
project: "General"
related_fix_id: "FIX-PROJ-9CBCDF"
related_task_id: ""
---

# BUG-PROJ-7B0418: Uncaught ValidationError on invalid payload

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `medium`
**Tags**: #bug #medium #bug/verified

## Symptoms and Reproduction
500 Internal Server Error instead of 422

## Root Cause
Missing FastAPI exception handler for Pydantic ValidationError

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-PROJ-9CBCDF|FIX-PROJ-9CBCDF]]