"""Contract tests for CandidatePool and TmdbErrorInfo (data-model.md 'CandidatePool')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.candidate_pool import CandidatePool, TmdbErrorInfo


@pytest.mark.contract
class TestCandidatePoolValid:
    def test_empty_pool_with_no_error_is_a_legitimate_zero_result(self):
        pool = CandidatePool(candidates=[], retry_number=0, error=None)
        assert pool.candidates == []
        assert pool.error is None

    def test_pool_with_error_set(self):
        pool = CandidatePool(
            candidates=[],
            retry_number=0,
            error=TmdbErrorInfo(kind="timeout", detail="connect timed out after 5s"),
        )
        assert pool.error.kind == "timeout"


@pytest.mark.contract
def test_invalid_error_kind_rejected():
    with pytest.raises(ValidationError):
        TmdbErrorInfo(kind="server_on_fire", detail="oops")


@pytest.mark.contract
def test_candidate_pool_has_no_total_results_or_retry_required_field():
    """Guards spec.md's Domain Model Minimization Rationale."""
    field_names = set(CandidatePool.model_fields.keys())
    assert "total_results" not in field_names
    assert "retry_required" not in field_names
