"""E2E test: liked_titles is recorded distinctly from genre/tone fields,
a soft exclusion stays soft, and the candidate pool traces to the
similarity-lookup fixture rather than a generic-discover fixture
(spec.md US3 Acceptance Scenarios 1-2; quickstart.md scenario 3).
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

REQUEST = (
    "I loved Arrival, Ex Machina, and Severance. Give me something thoughtful "
    "but not extremely bleak."
)

_PROFILE = PreferenceProfile(
    liked_titles=["Arrival", "Ex Machina"],
    theme_descriptors=["thoughtful"],
    additional_notes="not extremely bleak",  # soft, not a hard exclusion
)


def _raw_item(tmdb_id: int, title: str) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": f"{title} is a thoughtful science-fiction story.",
        "genre_ids": [878],
        "release_date": "2016-01-01",
        "vote_average": 7.6,
    }


def _raw_details(tmdb_id: int, title: str) -> dict:
    return {
        **_raw_item(tmdb_id, title),
        "genres": [{"id": 878, "name": "Science Fiction"}],
        "runtime": 110,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": [{"id": 1, "name": "thoughtful"}]},
    }


# A generic-discover fixture that would be wrong to use for this request --
# its presence in discover_results proves the pipeline chose similarity
# lookup instead, not that discover() was never called by anything.
_GENERIC_DISCOVER_POOL = [_raw_item(999, "Generic Genre Match")]

_SIMILAR_TO_ARRIVAL = [_raw_item(1, "Contact")]
_SIMILAR_TO_EX_MACHINA = [_raw_item(2, "Her")]

_DETAILS = {
    1: _raw_details(1, "Contact"),
    2: _raw_details(2, "Her"),
}


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_similarity_request_sources_candidates_from_similarity_not_generic_discover():
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    for candidate_id, title in ((1, "Contact"), (2, "Her")):
        detail = _DETAILS[candidate_id]
        prompt = build_rationale_prompt(
            _PROFILE, title=title, overview=detail["overview"], weak_evidence=False
        )
        recommendation_provider._responses[prompt] = _RationaleOutput(
            text=f"{title} matches your liked titles."
        )

    fake_client = FakeTmdbClient(
        discover_results={"movie": _GENERIC_DISCOVER_POOL, "tv": []},
        title_ids={"Arrival": 100, "Ex Machina": 200},
        similar_results={100: _SIMILAR_TO_ARRIVAL, 200: _SIMILAR_TO_EX_MACHINA},
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

    # liked_titles is captured distinctly from genres/tones (it never
    # became a genre or tone descriptor).
    assert package.applied_constraints.liked_titles == ["Arrival", "Ex Machina"]
    # The bleakness exclusion stays soft -- never promoted to a hard
    # constraint (spec.md US3 Acceptance Scenario 1).
    assert "bleak" not in " ".join(package.applied_constraints.excluded_genres).lower()
    assert "excluded_genres" not in package.applied_constraints.hard_override_fields

    picked_ids = {
        pick.candidate.tmdb_id
        for pick in (package.best_match, package.safe_pick, package.wildcard_pick)
        if pick is not None
    }
    assert picked_ids == {1, 2}  # from similarity lookups
    assert 999 not in picked_ids  # never the generic-discover fixture
