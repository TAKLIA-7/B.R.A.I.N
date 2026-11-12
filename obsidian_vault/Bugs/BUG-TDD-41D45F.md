---
id: BUG-TDD-41D45F
title: "Async dead-lock in connection pool acquire"
status: verified
severity: high
project: "General"
related_fix_id: "FIX-TDD-73A490"
related_task_id: ""
---

# BUG-TDD-41D45F: Async dead-lock in connection pool acquire

**Project**: [[Projects/General|General]]
**Status**: `verified` | **Severity**: `high`
**Tags**: #bug #high #bug/verified

## Symptoms and Reproduction
Requests hang indefinitely under concurrent load

## Root Cause
Missing timeout on pool lock acquire

## Investigation & Resolution
- Verified Fix: [[Fixes/FIX-TDD-73A490|FIX-TDD-73A490]]