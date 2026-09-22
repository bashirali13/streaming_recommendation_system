"""E2E test: a FakeModelProvider configured to fail 1-2 times succeeds
via the bounded retry; configured to fail past the bound, the session
ends with a controlled error rather than a crash (FR-028; quickstart.md
scenario 8). Covers both the agent-level retry (PreferenceAgent) and the
CLI-level controlled handling once ModelCallError propagates all the
way up.
"""

import pytest

from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.cli.intake import run_guided_cli
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.llm.provider import ModelCallError

REQUEST = "Something fun to watch tonight."
_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Comedy"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_agent_succeeds_when_failures_stay_within_the_bound():
    provider = FakeModelProvider(responses={REQUEST: _PROFILE}, fail_times=2)
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    profile = await agent.run(raw_user_input=REQUEST, intake_answers={})

    assert profile.media_type is MediaType.MOVIE
    assert provider.call_count == 3  # 1 initial + 2 retries


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_agent_raises_after_exhausting_the_bound():
    provider = FakeModelProvider(always_fail=True)
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    with pytest.raises(ModelCallError):
        await agent.run(raw_user_input=REQUEST, intake_answers={})


def _fake_orchestrator(provider: FakeModelProvider):
    from streaming_discovery.agents.discovery_agent import DiscoveryAgent
    from streaming_discovery.agents.orchestrator import Orchestrator
    from streaming_discovery.agents.recommendation_agent import RecommendationAgent
    from streaming_discovery.tmdb.fake_client import FakeTmdbClient

    return Orchestrator(
        preference_agent=PreferenceAgent(provider=provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(tmdb_client=FakeTmdbClient()),
        recommendation_agent=RecommendationAgent(
            provider=FakeModelProvider(), max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cli_prints_a_controlled_error_instead_of_crashing():
    provider = FakeModelProvider(always_fail=True)
    orchestrator = _fake_orchestrator(provider)
    printed: list[str] = []
    inputs = iter([REQUEST])

    await run_guided_cli(
        orchestrator, input_func=lambda _p="": next(inputs, ""), print_func=printed.append
    )

    joined = "\n".join(printed)
    assert "interpretation step failed" in joined.lower()
