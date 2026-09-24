"""Unit tests (T084): `Orchestrator.run_single_attempt` reports which
pipeline phase is currently running via an optional `on_step` callback,
so the CLI can show live progress instead of a single static message
for the whole pipeline. Purely a UI notification hook -- it makes no
decision and calls no model itself, so it doesn't touch the
Orchestrator's "no model call" boundary (constitution Principle II).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import (
    STEP_CURATING_PICKS,
    STEP_INTERPRETING,
    STEP_SEARCHING_TMDB,
    Orchestrator,
)
from streaming_discovery.agents.preference_agent import PreferenceAgent, build_preference_prompt
from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

REQUEST = "A dark, gritty thriller."
_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE, genres=["Thriller"], runtime_max_minutes=100
)
_RAW_MOVIE = {
    "id": 1,
    "title": "Night Shift",
    "overview": "A dark, gritty thriller.",
    "genre_ids": [53],
    "release_date": "2015-01-01",
    "vote_average": 7.0,
}
_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 53, "name": "Thriller"}],
        "runtime": 100,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": [{"id": 1, "name": "dark"}]},
    }
}


def _orchestrator(*, discover_sequence=None, discover_results=None) -> Orchestrator:
    preference_provider = FakeModelProvider(responses={REQUEST: _PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _PROFILE, title="Night Shift", overview=_RAW_MOVIE["overview"], weak_evidence=False
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        for_title="Night Shift", text="Night Shift matches your dark, gritty request."
    )
    return Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_sequence=discover_sequence,
                discover_results=discover_results,
                detail_results=_DETAILS,
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_step_reports_each_phase_in_order_on_the_happy_path():
    orchestrator = _orchestrator(discover_results={"movie": [_RAW_MOVIE]})
    steps: list[str] = []

    await orchestrator.run_single_attempt(raw_user_input=REQUEST, on_step=steps.append)

    assert steps == [STEP_INTERPRETING, STEP_SEARCHING_TMDB, STEP_CURATING_PICKS]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_step_reports_the_retry_with_the_relaxed_constraint_named():
    orchestrator = _orchestrator(discover_sequence={"movie": [[], [_RAW_MOVIE]]})
    steps: list[str] = []

    await orchestrator.run_single_attempt(raw_user_input=REQUEST, on_step=steps.append)

    assert steps[0] == STEP_INTERPRETING
    assert steps[1] == STEP_SEARCHING_TMDB
    assert "runtime" in steps[2].lower()
    assert "relax" in steps[2].lower()
    assert steps[3] == STEP_CURATING_PICKS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_step_is_optional_and_defaults_to_no_callback():
    orchestrator = _orchestrator(discover_results={"movie": [_RAW_MOVIE]})

    package = await orchestrator.run_single_attempt(raw_user_input=REQUEST)

    assert package.best_match is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_step_is_not_called_for_curating_when_there_is_no_match():
    orchestrator = _orchestrator(discover_results={"movie": []})
    steps: list[str] = []

    await orchestrator.run_single_attempt(raw_user_input=REQUEST, on_step=steps.append)

    assert STEP_CURATING_PICKS not in steps


def test_build_preference_prompt_matches_the_fixture_request():
    # Guards the fixture above against silent drift from build_preference_prompt's
    # own contract (a pure free-text call must key on the raw text alone).
    assert build_preference_prompt(REQUEST, {}) == REQUEST
