"""E2E test: a comedy-with-runtime-ceiling request that returns zero
candidates initially triggers exactly one retry with the runtime
constraint relaxed (not the genre), and the final output discloses the
relaxed constraint (spec.md US4 Acceptance Scenarios 1-2; quickstart.md
scenario 4).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "I need something funny under 100 minutes for tonight."

_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"], runtime_max_minutes=100)

_RAW_MOVIE = {
    "id": 1,
    "title": "Quick Laughs",
    "overview": "A fast-paced comedy that runs a little long.",
    "genre_ids": [35],
    "release_date": "2021-01-01",
    "vote_average": 7.1,
}

_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 35, "name": "Comedy"}],
        "runtime": 118,  # over the stated 100-minute ceiling -- only found via the relaxed retry
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }
}


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_zero_results_triggers_exactly_one_retry_with_runtime_relaxed():
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    prompt = build_rationale_prompt(
        _PROFILE, title="Quick Laughs", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[prompt] = _RationaleOutput(
        text="Quick Laughs matches your request for a comedy, once the runtime cap was relaxed."
    )

    fake_client = FakeTmdbClient(
        # First call (retry_number=0, runtime<=100): nothing qualifies.
        # Second call (retry_number=1, runtime relaxed): the movie shows up.
        discover_sequence={"movie": [[], [_RAW_MOVIE]]},
        detail_results=_DETAILS,
    )
    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(tmdb_client=fake_client),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    assert package.best_match is not None
    assert package.best_match.candidate.title == "Quick Laughs"
    assert package.relaxed_constraint is RelaxableConstraint.RUNTIME
    assert fake_client._discover_call_counts["movie"] == 2  # exactly one retry, not more
