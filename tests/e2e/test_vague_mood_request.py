"""E2E test: the vague-mood request leaves PreferenceProfile.media_type
and .providers unset, still returns picks when the fixture pool supports
it, and at least one pick's rationale reflects tone-based matching, with
weak-evidence candidates carrying a confidence_note (spec.md US2
Acceptance Scenarios 1-3; quickstart.md scenario 2).
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
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "Dark, moody, Eastern European vibes."

_PROFILE = PreferenceProfile(
    tone_descriptors=["dark", "moody"], setting_descriptors=["Eastern European"]
)


def _raw_candidate(tmdb_id: int, title: str, overview: str) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": overview,
        "genre_ids": [18],
        "release_date": "2019-01-01",
        "vote_average": 7.4,
    }


def _raw_details(tmdb_id: int, title: str, overview: str) -> dict:
    return {
        **_raw_candidate(tmdb_id, title, overview),
        "genres": [{"id": 18, "name": "Drama"}],
        "runtime": 105,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }


# Strong evidence: overview echoes the stated tone/setting descriptors.
_STRONG = _raw_candidate(
    1, "Winter's Edge", "A dark, moody thriller set against an Eastern European winter."
)
# Weak evidence: no overlap with the stated tone/setting at all.
_WEAK = _raw_candidate(2, "Sunny Afternoon", "A cheerful family finds joy at the beach.")

_DETAILS = {
    1: _raw_details(1, "Winter's Edge", _STRONG["overview"]),
    2: _raw_details(2, "Sunny Afternoon", _WEAK["overview"]),
}


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_vague_mood_request_leaves_format_and_providers_unset_and_flags_weak_evidence():
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    for candidate_id, weak in ((1, False), (2, True)):
        detail = _DETAILS[candidate_id]
        prompt = build_rationale_prompt(
            _PROFILE, title=detail["title"], overview=detail["overview"], weak_evidence=weak
        )
        recommendation_provider._responses[prompt] = _RationaleOutput(
            text=f"{detail['title']} rationale.",
            confidence_note="Little tone evidence in the overview." if weak else None,
        )

    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"movie": [_STRONG, _WEAK], "tv": []},
                detail_results=_DETAILS,
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    # The interpreted profile (available via applied_constraints) left
    # format/providers unset -- never defaulted (FR-003).
    assert package.applied_constraints.media_type is None
    assert package.applied_constraints.providers == []

    assert package.best_match is not None
    assert package.best_match.candidate.title == "Winter's Edge"
    assert package.best_match.confidence_note is None  # strong evidence

    assert package.safe_pick is not None
    assert package.safe_pick.candidate.title == "Sunny Afternoon"
    assert package.safe_pick.confidence_note is not None  # weak evidence, flagged
