"""Unit test (T110): the Preference Agent's model was never told today's
date, so a relative time request ("made in the last 5 years") was resolved
against whatever year the model assumed -- live, it answered
`year_min: 2020` when the real answer was 2021. The current date is now
part of the system prompt the model receives on every call.
"""

from datetime import date

import pytest

from streaming_discovery.agents.preference_agent import PreferenceAgent, build_system_prompt
from streaming_discovery.contracts.preference_profile import PreferenceProfile


class _RecordingProvider:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    async def generate(self, *, system_prompt: str, user_prompt: str, output_type):
        self.system_prompts.append(system_prompt)
        return PreferenceProfile(genres=["Action"])


def test_system_prompt_states_todays_date():
    prompt = build_system_prompt(date(2026, 9, 24))

    assert "2026-09-24" in prompt


def test_system_prompt_tells_the_model_to_resolve_relative_years_against_it():
    prompt = build_system_prompt(date(2026, 9, 24))

    assert "last 5 years" in prompt
    assert "year_min" in prompt


def test_system_prompt_keeps_the_existing_rules():
    prompt = build_system_prompt(date(2026, 9, 24))

    assert "excluded_keywords" in prompt


@pytest.mark.asyncio
async def test_agent_sends_the_injected_date_to_the_model():
    provider = _RecordingProvider()
    agent = PreferenceAgent(
        provider=provider, max_additional_attempts=0, today=lambda: date(2031, 1, 2)
    )

    await agent.run(raw_user_input="an action movie", intake_answers={})

    assert "2031-01-02" in provider.system_prompts[0]


@pytest.mark.asyncio
async def test_agent_defaults_to_the_real_current_date():
    provider = _RecordingProvider()
    agent = PreferenceAgent(provider=provider, max_additional_attempts=0)

    await agent.run(raw_user_input="an action movie", intake_answers={})

    assert date.today().isoformat() in provider.system_prompts[0]
