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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_valid_correction_echoes_the_updated_profile_before_returning():
    """T096: after a non-blank, successfully-applied correction, the
    updated preferences are shown back to the user -- not just silently
    carried forward to discovery -- so they can see it actually took.
    """
    profile = _minimal_profile()
    inputs = iter(["providers=Netflix|Hulu"])
    printed: list[str] = []

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=printed.append
    )

    assert correction == {"providers": ["Netflix", "Hulu"]}
    joined = "\n".join(printed)
    assert "Netflix" in joined
    assert "Hulu" in joined


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_unrecognized_correction_is_reported_not_silently_dropped():
    """T096: typing something that doesn't match the field=value syntax
    (e.g. forgetting the field name) used to silently do nothing, with
    no feedback -- the user couldn't tell their correction was ignored.
    """
    profile = _minimal_profile()
    inputs = iter(["Hulu"])  # missing "providers=" -- not valid syntax
    printed: list[str] = []

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=printed.append
    )

    assert correction is None
    joined = "\n".join(printed).lower()
    assert "didn't recognize" in joined or "unrecognized" in joined


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_correction_producing_an_invalid_profile_is_reported_not_crashed():
    """T096: a correction that parses syntactically but produces an
    invalid profile (e.g. an inverted year range) used to raise
    ContractValidationError uncaught here, crashing the whole session --
    it must be a controlled, reported failure instead.
    """
    from streaming_discovery.contracts.preference_profile import PreferenceProfile

    profile = PreferenceProfile(genres=["Comedy"], year_min=2000, year_max=2010)
    inputs = iter(["year_min=2020"])  # now inverted: 2020 > 2010
    printed: list[str] = []

    correction = await default_confirm(
        profile, input_func=lambda _prompt: next(inputs), print_func=printed.append
    )

    assert correction is None
    joined = "\n".join(printed).lower()
    assert "valid" in joined or "didn't" in joined or "couldn't" in joined


def _minimal_profile():
    from streaming_discovery.contracts.preference_profile import PreferenceProfile

    return PreferenceProfile(genres=["Comedy"])
