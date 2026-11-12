import pytest
from core.bugs.manager import BugManager

def test_fix_requires_verification_evidence_to_become_verified():
    bm = BugManager()
    
    # 1. Unverified fix (no test results or passing exit code)
    status_unverified = bm.evaluate_fix_status(
        verification={"notes": "looks good to me, should work"}
    )
    assert status_unverified == "fixed"
    assert status_unverified != "verified"

    # 2. Verified fix with automated test evidence
    status_verified = bm.evaluate_fix_status(
        verification={"tests": "pytest tests/", "result": "passed", "run_id": "run-42"}
    )
    assert status_verified == "verified"

    # 3. Verified fix with explicit human sign-off
    status_human = bm.evaluate_fix_status(
        verification={"notes": "reviewed manually"},
        human_approval=True
    )
    assert status_human == "verified"

def test_duplicate_and_regression_detection():
    bm = BugManager()
    
    existing_bugs = [
        {"bug_id": "BUG-001", "signature": "sig_pg_timeout", "status": "verified", "location": {"files": ["db.py"]}},
        {"bug_id": "BUG-002", "signature": "sig_null_pointer", "status": "open", "location": {"files": ["api.py"]}}
    ]

    # Matching signature with an open bug -> duplicate
    rel1 = bm.detect_relationship(signature="sig_null_pointer", location={"files": ["api.py"]}, existing_bugs=existing_bugs)
    assert rel1 is not None
    assert rel1["relation_type"] == "duplicate_of"
    assert rel1["target_bug_id"] == "BUG-002"

    # Matching signature with a previously verified bug -> regression
    rel2 = bm.detect_relationship(signature="sig_pg_timeout", location={"files": ["db.py"]}, existing_bugs=existing_bugs)
    assert rel2 is not None
    assert rel2["relation_type"] == "regression_of"
    assert rel2["target_bug_id"] == "BUG-001"

