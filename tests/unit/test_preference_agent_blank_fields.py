"""Unit test: given free text mentioning only tone/setting descriptors,
the PreferenceAgent leaves every unmentioned field None/empty rather than
defaulted (FR-003).
"""

import pytest

from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider

REQUEST = "Dark, moody, Eastern European vibes."

_EXPECTED_PROFILE = PreferenceProfile(
    tone_descriptors=["dark", "moody"], setting_descriptors=["Eastern European"]
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unmentioned_fields_stay_none_or_empty_not_defaulted():
    provider = FakeModelProvider(responses={REQUEST: _EXPECTED_PROFILE})
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    profile = await agent.run(raw_user_input=REQUEST, intake_answers={})

    assert profile.media_type is None
    assert profile.providers == []
    assert profile.genres == []
    assert profile.excluded_genres == []
    assert profile.year_min is None
    assert profile.year_max is None
    assert profile.runtime_max_minutes is None
    assert profile.liked_titles == []
    assert profile.disliked_titles == []
    # The fields the user actually addressed are the only ones populated.
    assert profile.tone_descriptors == ["dark", "moody"]
    assert profile.setting_descriptors == ["Eastern European"]
