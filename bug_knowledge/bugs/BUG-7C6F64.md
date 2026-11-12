---
id: BUG-7C6F64
title: "Postgres connection pool exhaustion under load"
status: investigating
severity: high
reported_by: qa-agent
first_seen: "2026-11-12 21:34:36.688300+00:00"
files: ['core/adapters/postgres.py']
symbols: ['get_connection']
---

# BUG-7C6F64: Postgres connection pool exhaustion under load

## Symptoms and Reproduction
Timeout connecting to database

## Root Cause
Missing pool recycling

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `investigating`

_No fixes recorded yet._
