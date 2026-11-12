---
id: BUG-TDD-57FEDA
title: "Async dead-lock in connection pool acquire"
status: verified
severity: high
project: "General"
related_fix_id: "FIX-TDD-FD645C"
related_task_id: ""
---

# BUG-TDD-57FEDA: Async dead-lock in connection pool acquire

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `high`
**Tags**: #bug #high #bug/verified

## Symptoms and Reproduction
Requests hang indefinitely under concurrent load

## Root Cause
Missing timeout on pool lock acquire

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-TDD-FD645C|FIX-TDD-FD645C]]