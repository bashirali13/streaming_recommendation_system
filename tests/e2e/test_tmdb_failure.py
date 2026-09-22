"""E2E test: a FakeTmdbClient failure on the first call ends the session
with a controlled, user-visible error and no fabricated candidates
(FR-027; quickstart.md scenario 7).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "Something fun to watch tonight."
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["timeout", "http_error", "malformed_response"])
async def test_tmdb_failure_ends_the_session_with_a_controlled_error(failure_mode):
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient(failure_mode=failure_mode)),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    # No fabricated candidates -- every role stays empty, never a crash.
    assert package.best_match is None
    assert package.safe_pick is None
    assert package.wildcard_pick is None
    assert package.unresolved_notes is not None
    assert "unavailable" in package.unresolved_notes.lower()
    # Never a second attempt after a genuine TMDB error (distinct from
    # the zero-candidate retry path, FR-027 vs FR-011).
    assert package.relaxed_constraint is None
