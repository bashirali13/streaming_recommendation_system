"""E2E test: a mystery-series request excluding a sub-genre and capping
season count at three keeps both constraints enforced in the initial
search and, when an unrelated soft constraint (year) triggers a retry,
in the retried search too (spec.md US5 Acceptance Scenarios 1-2;
quickstart.md scenario 5).

TMDB has no official "police procedural" genre, so this uses "Crime" (a
real TMDB TV genre) as the excluded sub-genre -- otherwise the exclusion
assertion would be vacuous, since excluded_genres only ever matches
candidates against TMDB's actual genre names.
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

REQUEST = (
    "Recommend a mystery series, but no crime procedurals and nothing with more than three seasons."
)

_PROFILE = PreferenceProfile(
    media_type=MediaType.TV,
    genres=["Mystery"],
    excluded_genres=["Crime"],
    season_count_max=3,
    hard_override_fields=["season_count_max"],
    year_min=2015,  # the "unrelated soft constraint" that triggers the retry
)


def _raw_item(tmdb_id: int, name: str, genre_ids: list[int]) -> dict:
    return {
        "id": tmdb_id,
        "name": name,
        "overview": f"{name} is an intriguing mystery series.",
        "genre_ids": genre_ids,
        "first_air_date": "2018-01-01",
        "vote_average": 7.3,
    }


def _raw_details(tmdb_id: int, name: str, genres: list[dict], number_of_seasons: int) -> dict:
    return {
        **_raw_item(tmdb_id, name, [g["id"] for g in genres]),
        "genres": genres,
        "number_of_seasons": number_of_seasons,
        "watch/providers": {"results": {}},
        "keywords": {"results": []},
    }


_QUALIFIES = _raw_item(1, "Deep Waters", [9648])  # Mystery only, 2 seasons -- should qualify
_WRONG_GENRE = _raw_item(2, "Beat Cop Files", [9648, 80])  # Mystery + Crime -- excluded
_TOO_MANY_SEASONS = _raw_item(3, "Long Runner", [9648])  # Mystery only, 5 seasons -- excluded

_DETAILS = {
    1: _raw_details(1, "Deep Waters", [{"id": 9648, "name": "Mystery"}], number_of_seasons=2),
    2: _raw_details(
        2,
        "Beat Cop Files",
        [{"id": 9648, "name": "Mystery"}, {"id": 80, "name": "Crime"}],
        number_of_seasons=2,
    ),
    3: _raw_details(3, "Long Runner", [{"id": 9648, "name": "Mystery"}], number_of_seasons=5),
}


async def _silent_confirm(profile):
    return None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_exclusion_and_season_cap_hold_across_the_retry():
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    prompt = build_rationale_prompt(
        _PROFILE, title="Deep Waters", overview=_DETAILS[1]["overview"], weak_evidence=False
    )
    recommendation_provider._responses[prompt] = _RationaleOutput(
        for_title="Deep Waters", text="Deep Waters is a mystery series that fits your request."
    )

    fake_client = FakeTmdbClient(
        # Initial (year>=2015): nothing qualifies. Retry (year relaxed):
        # all three raw items come back, but only one should survive the
        # still-enforced exclusion + season cap.
        discover_sequence={"tv": [[], [_QUALIFIES, _WRONG_GENRE, _TOO_MANY_SEASONS]]},
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

    assert package.relaxed_constraint is RelaxableConstraint.YEAR_RANGE
    assert package.best_match is not None
    assert package.best_match.candidate.title == "Deep Waters"
    assert package.safe_pick is None  # the other two were hard-excluded, not just ranked lower
