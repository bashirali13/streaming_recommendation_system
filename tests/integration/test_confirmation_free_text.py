"""Integration test: for a free-text request (no guided intake involved),
the CLI renders the PreferenceProfile confirmation summary and accepts a
terminal correction before Discovery is invoked, and that correction is
reflected in the profile actually used (FR-006).
"""

import pytest

from streaming_discovery.cli.output import default_confirm


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirmation_summary_is_shown_before_any_correction():
    from streaming_discovery.contracts.enums import MediaType
    from streaming_discovery.contracts.preference_profile import PreferenceProfile

    profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Drama"])
    printed: list[str] = []
    inputs = iter([""])  # accept as-is, no correction

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=printed.append
    )

    assert correction is None
    joined = "\n".join(printed)
    assert "Format: movie" in joined
    assert "Drama" in joined


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_typed_correction_is_parsed_and_applied():
    from streaming_discovery.agents.orchestrator import apply_correction
    from streaming_discovery.contracts.enums import MediaType
    from streaming_discovery.contracts.preference_profile import PreferenceProfile

    profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Drama"])
    inputs = iter(["media_type=tv"])

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=lambda _line: None
    )

    assert correction == {"media_type": "tv"}
    corrected_profile = apply_correction(profile, correction)
    assert corrected_profile.media_type is MediaType.TV
    assert corrected_profile.genres == ["Drama"]  # untouched field survives


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_list_field_correction_uses_pipe_separated_values():
    profile = _minimal_profile()
    inputs = iter(["providers=Netflix|Hulu"])

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=lambda _line: None
    )

    assert correction == {"providers": ["Netflix", "Hulu"]}


def _minimal_profile():
    from streaming_discovery.contracts.preference_profile import PreferenceProfile

    return PreferenceProfile(genres=["Comedy"])
