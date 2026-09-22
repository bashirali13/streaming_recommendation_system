"""Unit test: PreferenceAgent's plumbing correctly carries through a
season_count_max value (always classified hard, per SYSTEM_PROMPT and
data-model.md) for a request naming a season cap (User Story 5). The
system prompt's instruction to do this was already written during User
Story 1, alongside the rest of PreferenceAgent's contract; this confirms
it via a fixture, the same pattern used for the other PreferenceAgent
tests, since it had no dedicated test until now.
"""

import pytest

from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider

REQUEST = "Recommend a mystery series with no more than three seasons."

_EXPECTED_PROFILE = PreferenceProfile(
    genres=["Mystery"],
    season_count_max=3,
    hard_override_fields=["season_count_max"],
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_season_count_cap_is_carried_through_as_hard():
    provider = FakeModelProvider(responses={REQUEST: _EXPECTED_PROFILE})
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    profile = await agent.run(raw_user_input=REQUEST, intake_answers={})

    assert profile.season_count_max == 3
    assert "season_count_max" in profile.hard_override_fields
