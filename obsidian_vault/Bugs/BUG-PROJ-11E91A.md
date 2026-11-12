---
id: BUG-PROJ-11E91A
title: "Uncaught ValidationError on invalid payload"
status: verified
severity: medium
project: "General"
related_fix_id: "FIX-PROJ-EEA4D8"
related_task_id: ""
---

# BUG-PROJ-11E91A: Uncaught ValidationError on invalid payload

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `medium`
**Tags**: #bug #medium #bug/verified

## Symptoms and Reproduction
500 Internal Server Error instead of 422

## Root Cause
Missing FastAPI exception handler for Pydantic ValidationError

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-PROJ-EEA4D8|FIX-PROJ-EEA4D8]]