---
id: BUG-TDD-BE1A63
title: "Async dead-lock in connection pool acquire"
status: verified
severity: high
project: "General"
related_fix_id: "FIX-TDD-594474"
related_task_id: ""
---

# BUG-TDD-BE1A63: Async dead-lock in connection pool acquire

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `high`
**Tags**: #bug #high #bug/verified

## Symptoms and Reproduction
Requests hang indefinitely under concurrent load

## Root Cause
Missing timeout on pool lock acquire

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-TDD-594474|FIX-TDD-594474]]