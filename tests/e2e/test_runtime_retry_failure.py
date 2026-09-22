"""E2E test: when the retried search also returns zero candidates, the
session stops without a second retry and explains which constraints
blocked a match (spec.md US4 Acceptance Scenario 3; quickstart.md
scenario 4b).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "I need something funny under 100 minutes for tonight."

_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"], runtime_max_minutes=100)


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_retry_also_zero_stops_without_a_second_retry_and_explains_why():
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    fake_client = FakeTmdbClient(discover_sequence={"movie": [[], []]})  # zero both times
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(tmdb_client=fake_client),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    assert package.best_match is None
    assert package.safe_pick is None
    assert package.wildcard_pick is None
    assert package.relaxed_constraint is RelaxableConstraint.RUNTIME
    assert package.unresolved_notes is not None
    assert "Comedy" in package.unresolved_notes or "comedy" in package.unresolved_notes.lower()
    # Exactly one retry -- never a third discover() call.
    assert fake_client._discover_call_counts["movie"] == 2
