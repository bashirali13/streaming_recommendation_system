"""E2E test: when only 1 or 2 candidates qualify, the pipeline returns
that many roles -- never broadening a constraint or reusing a candidate
to force a third pick (FR-015, SC-008, resolved Clarification Q1;
quickstart.md scenario 1b).
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
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "A quiet, thoughtful drama about grief."
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["quiet", "thoughtful"])


def _raw_candidate(tmdb_id: int, title: str) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": f"{title} is a quiet, thoughtful meditation on grief.",
        "genre_ids": [18],
        "release_date": "2018-01-01",
        "vote_average": 7.0,
    }


def _raw_details(tmdb_id: int, title: str) -> dict:
    return {
        **_raw_candidate(tmdb_id, title),
        "genres": [{"id": 18, "name": "Drama"}],
        "runtime": 100,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }


async def _silent_confirm(profile):
    return None


def _build_orchestrator(raw_movies: list[dict], detail_results: dict) -> Orchestrator:
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    for raw in raw_movies:
        detail = detail_results[raw["id"]]
        prompt = build_rationale_prompt(
            _PROFILE, title=raw["title"], overview=detail["overview"], weak_evidence=False
        )
        recommendation_provider._responses[prompt] = _RationaleOutput(
            for_title=raw["title"], text=f"{raw['title']} matches your quiet, thoughtful mood."
        )
    return Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"movie": raw_movies}, detail_results=detail_results
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_exactly_one_qualifying_candidate_yields_only_best_match():
    raw_movies = [_raw_candidate(1, "Quiet Grief")]
    orchestrator = _build_orchestrator(raw_movies, {1: _raw_details(1, "Quiet Grief")})

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    assert package.best_match is not None
    assert package.best_match.candidate.tmdb_id == 1
    assert package.safe_pick is None
    assert package.wildcard_pick is None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_exactly_two_qualifying_candidates_yields_best_match_and_safe_pick_only():
    raw_movies = [_raw_candidate(1, "Quiet Grief"), _raw_candidate(2, "Still Waters")]
    detail_results = {1: _raw_details(1, "Quiet Grief"), 2: _raw_details(2, "Still Waters")}
    orchestrator = _build_orchestrator(raw_movies, detail_results)

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST, confirm=_silent_confirm)

    assert package.best_match is not None
    assert package.safe_pick is not None
    assert package.wildcard_pick is None
    assert package.best_match.candidate.tmdb_id != package.safe_pick.candidate.tmdb_id
