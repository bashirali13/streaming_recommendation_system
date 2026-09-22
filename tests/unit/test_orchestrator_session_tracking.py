"""Unit test: Orchestrator.run_single_attempt tracks a UserSessionState
as it runs (raw input, intake answers, the confirmed preference profile,
each discovery attempt, and the final package) -- the contract has
existed and been tested since Foundational, but was never actually
constructed at runtime until now. Exposed as `orchestrator.session`
rather than changing run_single_attempt's return type, so every existing
caller/test that expects a bare RecommendationPackage back is unaffected.
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.session_state import UserSessionState
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "Something fun to watch tonight."
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])


async def _silent_confirm(profile):
    return None


def _orchestrator() -> Orchestrator:
    return Orchestrator(
        preference_agent=PreferenceAgent(
            provider=FakeModelProvider(responses={REQUEST: _PROFILE}), max_additional_attempts=2
        ),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient()),  # zero candidates
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_starts_as_a_fresh_state_before_any_run():
    orchestrator = _orchestrator()

    assert isinstance(orchestrator.session, UserSessionState)
    assert orchestrator.session.raw_user_input is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_is_populated_during_a_run():
    orchestrator = _orchestrator()

    await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    session = orchestrator.session
    assert session.raw_user_input == REQUEST
    assert session.preference_profile is not None
    assert session.preference_profile.media_type is MediaType.MOVIE
    assert len(session.discovery_attempts) >= 1
    assert session.recommendation_package is not None
