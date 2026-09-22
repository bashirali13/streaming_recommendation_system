"""Integration test: an agent output that fails its contract's validation
is surfaced as a controlled failure by the Orchestrator, never silently
coerced or passed downstream (FR-022, NFR-002).
"""

import pytest

from streaming_discovery.agents.orchestrator import ContractValidationError, Orchestrator
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


class _ReturnsInvalidPreferenceProfile:
    async def run(self, *, raw_user_input, intake_answers):
        return {}  # entirely empty -> fails PreferenceProfile's own validation


class _ReturnsValidPreferenceProfile:
    async def run(self, *, raw_user_input, intake_answers):
        return PreferenceProfile(media_type=MediaType.MOVIE)


class _ReturnsValidCandidatePool:
    async def run(self, query):
        return CandidatePool(candidates=[], retry_number=query.retry_number)


class _ReturnsWrongType:
    async def run(self, query):
        return "not a candidate pool at all"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_preference_agent_output_is_a_controlled_failure():
    orchestrator = Orchestrator(
        preference_agent=_ReturnsInvalidPreferenceProfile(),
        discovery_agent=_ReturnsValidCandidatePool(),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        await orchestrator.interpret_preferences(raw_user_input=None, intake_answers=None)

    assert exc_info.value.contract is PreferenceProfile


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_preference_agent_output_passes_through():
    orchestrator = Orchestrator(
        preference_agent=_ReturnsValidPreferenceProfile(),
        discovery_agent=_ReturnsValidCandidatePool(),
    )

    profile = await orchestrator.interpret_preferences(
        raw_user_input="a movie", intake_answers=None
    )

    assert profile.media_type is MediaType.MOVIE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_agent_returning_the_wrong_type_is_a_controlled_failure():
    orchestrator = Orchestrator(
        preference_agent=_ReturnsValidPreferenceProfile(),
        discovery_agent=_ReturnsWrongType(),
    )
    query = DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=0)

    with pytest.raises(ContractValidationError) as exc_info:
        await orchestrator.discover_once(query)

    assert exc_info.value.contract is CandidatePool


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_discovery_agent_output_passes_through():
    orchestrator = Orchestrator(
        preference_agent=_ReturnsValidPreferenceProfile(),
        discovery_agent=_ReturnsValidCandidatePool(),
    )
    query = DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=0)

    pool = await orchestrator.discover_once(query)

    assert pool.candidates == []
    assert pool.retry_number == 0
