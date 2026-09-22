"""Contract tests for UserSessionState (data-model.md 'UserSessionState')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.session_state import UserSessionState


@pytest.mark.contract
class TestUserSessionStateValid:
    def test_fresh_session_has_all_optional_fields_blank(self):
        session = UserSessionState()
        assert session.raw_user_input is None
        assert session.intake_answers == {}
        assert session.preference_profile is None
        assert session.discovery_attempts == []
        assert session.recommendation_package is None

    def test_two_discovery_attempts_allowed(self):
        session = UserSessionState(
            discovery_attempts=[
                CandidatePool(retry_number=0),
                CandidatePool(retry_number=1),
            ]
        )
        assert len(session.discovery_attempts) == 2


@pytest.mark.contract
def test_third_discovery_attempt_rejected():
    with pytest.raises(ValidationError):
        UserSessionState(
            discovery_attempts=[
                CandidatePool(retry_number=0),
                CandidatePool(retry_number=1),
                CandidatePool(retry_number=1),
            ]
        )
