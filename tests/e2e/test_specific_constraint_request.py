"""E2E test: the full pipeline for the specific-constraint request returns
exactly three distinct titles, none in the excluded genre, with no raw
JSON anywhere in the rendered output (spec.md US1 Acceptance Scenarios
2-3; quickstart.md scenario 1).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.cli.output import render_package
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = (
    "I have Netflix and Hulu. I want a movie after 2010 with a powerful "
    "female lead that is not a superhero movie."
)

_EXPECTED_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE,
    providers=["Netflix", "Hulu"],
    excluded_genres=["Superhero"],
    tone_descriptors=["powerful female lead"],
    year_min=2010,
)


def _raw_candidate(tmdb_id: int, title: str, genres: list[int], vote_average: float) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": f"{title} follows a powerful female lead confronting the past.",
        "genre_ids": genres,
        "release_date": "2015-05-01",
        "vote_average": vote_average,
    }


def _raw_details(tmdb_id: int, title: str, genres: list[dict]) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": f"{title} follows a powerful female lead confronting the past.",
        "genres": genres,
        "release_date": "2015-05-01",
        "vote_average": 7.5,
        "runtime": 118,
        "watch/providers": {"results": {"US": {"flatrate": [{"provider_name": "Netflix"}]}}},
        "keywords": {"keywords": [{"id": 1, "name": "powerful female lead"}]},
    }


# 18 = Drama, 53 = Thriller, 28 = Action (all valid, non-excluded genres).
_RAW_MOVIES = [
    _raw_candidate(1, "Steel Resolve", [18, 53], 7.9),
    _raw_candidate(2, "Quiet Storm", [18], 7.2),
    _raw_candidate(3, "Iron Will", [28], 6.8),
    _raw_candidate(4, "Broken Glass", [53], 6.5),
]

_DETAILS_BY_ID = {
    1: _raw_details(
        1, "Steel Resolve", [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}]
    ),
    2: _raw_details(2, "Quiet Storm", [{"id": 18, "name": "Drama"}]),
    3: _raw_details(3, "Iron Will", [{"id": 28, "name": "Action"}]),
    4: _raw_details(4, "Broken Glass", [{"id": 53, "name": "Thriller"}]),
}


async def _silent_confirm(profile):
    return None  # accept the interpreted profile as-is, no correction


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_specific_constraint_request_returns_three_distinct_non_excluded_picks():
    preference_provider = FakeModelProvider(responses={REQUEST: _EXPECTED_PROFILE})
    recommendation_provider = FakeModelProvider()  # rationale text: default canned response below
    # Rationale prompts are keyed per-candidate; configure a response per finalist.
    from streaming_discovery.agents.recommendation_agent import (
        _RationaleOutput,
        build_rationale_prompt,
    )

    for candidate_id, title in ((1, "Steel Resolve"), (2, "Quiet Storm"), (3, "Iron Will")):
        detail = _DETAILS_BY_ID[candidate_id]
        prompt = build_rationale_prompt(
            _EXPECTED_PROFILE,
            title=title,
            overview=detail["overview"],
            weak_evidence=False,
        )
        recommendation_provider._responses[prompt] = _RationaleOutput(
            text=f"{title} matches your request for a powerful female lead drama."
        )

    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"movie": _RAW_MOVIES},
                detail_results=_DETAILS_BY_ID,
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    assert package.best_match is not None
    assert package.safe_pick is not None
    assert package.wildcard_pick is not None
    picked_ids = {
        package.best_match.candidate.tmdb_id,
        package.safe_pick.candidate.tmdb_id,
        package.wildcard_pick.candidate.tmdb_id,
    }
    assert len(picked_ids) == 3  # three distinct titles
    assert 4 not in picked_ids  # "Broken Glass" wasn't enriched/selected; not asserted on directly

    for role_pick in (package.best_match, package.safe_pick, package.wildcard_pick):
        assert "Superhero" not in role_pick.candidate.genres

    rendered = render_package(package)
    assert "{" not in rendered  # no raw JSON/dict leaking into the rendered text
    assert "tmdb_id" not in rendered
