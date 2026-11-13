---
id: FIX-STRIPE-002
bug_id: BUG-STRIPE-002
commit: "ff0007ca0b406ece40c7e708e51e4d772a13ad34"
fixed_by: agent_beta
created_at: "2026-11-13 05:39:44.958311+00:00"
files_changed: ['services/payment/webhook_handler.py']
---

# Fix FIX-STRIPE-002 for [BUG-STRIPE-002](../bugs/BUG-STRIPE-002.md)

## Summary
Pass raw request.body bytes directly into construct_event instead of UTF-8 decoded text

## Files Changed
- `services/payment/webhook_handler.py`

## Verification Evidence
- **Tests Executed**: `None`
- **Result**: `untested`
- **Run ID**: `N/A`

