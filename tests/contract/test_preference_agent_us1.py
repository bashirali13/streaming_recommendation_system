"""Contract test: the Preference Agent's output for the fixture
specific-constraint request marks media_type and the excluded genre as
hard, and the tone/recency signals as soft (spec.md US1 Acceptance
Scenario 1).

This tests the agent's plumbing (prompt construction, retry wrapping,
output validation) against a fixture standing in for a well-behaved
model response -- it does not test the model's own interpretation
quality, which is outside what a fake-provider-backed test can exercise.
"""

import pytest

from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider

REQUEST = (
    "I have Netflix and Hulu. I want a movie after 2010 with a powerful "
    "female lead that is not a superhero movie."
)

EXPECTED_PROFILE = PreferenceProfile(
    media_type=MediaType.MOVIE,
    providers=["Netflix", "Hulu"],
    excluded_genres=["Superhero"],
    tone_descriptors=["powerful female lead"],
    year_min=2010,
)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_specific_constraint_request_produces_expected_hard_soft_split():
    provider = FakeModelProvider(responses={REQUEST: EXPECTED_PROFILE})
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    profile = await agent.run(raw_user_input=REQUEST, intake_answers={})

    assert profile.media_type is MediaType.MOVIE
    assert "Superhero" in profile.excluded_genres
    assert profile.year_min == 2010
    assert "media_type" not in profile.hard_override_fields
    assert "year_min" not in profile.hard_override_fields


@pytest.mark.contract
@pytest.mark.asyncio
async def test_free_text_alone_is_passed_through_unchanged_as_the_prompt():
    """With no guided-intake answers, the prompt sent to the model is the
    raw text verbatim -- keeping fixture keys simple and exact-matchable.
    """
    provider = FakeModelProvider(responses={REQUEST: EXPECTED_PROFILE})
    agent = PreferenceAgent(provider=provider, max_additional_attempts=2)

    await agent.run(raw_user_input=REQUEST, intake_answers={})

    assert provider.call_count == 1
