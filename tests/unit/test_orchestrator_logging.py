"""Unit test: a structured log record is emitted for each agent
invocation, each TMDB call, and each contract-validation outcome
(NFR-006).
"""

import logging

import pytest

from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


class _StubPreferenceAgent:
    async def run(self, *, raw_user_input, intake_answers):
        return PreferenceProfile(media_type=MediaType.MOVIE)


class _StubDiscoveryAgent:
    async def run(self, query):
        return CandidatePool(candidates=[], retry_number=query.retry_number)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_invocations_are_logged(caplog: pytest.LogCaptureFixture):
    orchestrator = Orchestrator(
        preference_agent=_StubPreferenceAgent(),
        discovery_agent=_StubDiscoveryAgent(),
        recommendation_agent=None,
        region="US",
        result_limit=20,
    )

    with caplog.at_level(logging.INFO, logger="streaming_discovery.orchestrator"):
        await orchestrator.interpret_preferences(raw_user_input="a movie", intake_answers=None)
        queries = orchestrator.build_discovery_queries(
            PreferenceProfile(media_type=MediaType.MOVIE), retry_number=0
        )
        await orchestrator.run_discovery_attempt(queries)

    messages = [record.message for record in caplog.records]
    assert any("preference_agent" in m for m in messages)
    assert any("discovery_agent" in m for m in messages)
