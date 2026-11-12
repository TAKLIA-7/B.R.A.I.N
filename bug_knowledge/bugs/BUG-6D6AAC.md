---
id: BUG-6D6AAC
title: "Postgres connection pool exhaustion under load"
status: investigating
severity: high
reported_by: qa-agent
first_seen: "2026-11-12 18:07:27.315437+00:00"
files: ['core/adapters/postgres.py']
symbols: ['get_connection']
---

# BUG-6D6AAC: Postgres connection pool exhaustion under load

## Symptoms and Reproduction
Timeout connecting to database

## Root Cause
Missing pool recycling

## Investigation Attempts
_No investigation attempts recorded yet._

## Resolution and Verification
- **Status**: `investigating`

_No fixes recorded yet._
