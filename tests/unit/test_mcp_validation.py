import pytest
from pydantic import ValidationError
from core.models.checkpoint import HandoverState

def test_checkpoint_argument_validation():
    # Attempting to construct state with missing required fields
    with pytest.raises(ValidationError):
        HandoverState.model_validate({
            "task_id": "task-test",
            # missing goal, steps, etc.
        })

