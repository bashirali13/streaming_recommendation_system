"""Unit test: the relaxation-priority helper picks the first eligible
constraint in the fixed order (tone -> runtime -> year_range) present on
the profile, and never returns excluded_genres, media_type, or any
hard_override_fields entry as relaxable (FR-011, FR-010).
"""

from streaming_discovery.agents.orchestrator import select_relaxation_constraint
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile


def test_tone_is_picked_first_when_present():
    profile = PreferenceProfile(
        genres=["Comedy"], tone_descriptors=["dark"], runtime_max_minutes=100, year_min=2010
    )

    assert select_relaxation_constraint(profile) is RelaxableConstraint.TONE


def test_runtime_is_picked_when_tone_absent():
    profile = PreferenceProfile(genres=["Comedy"], runtime_max_minutes=100, year_min=2010)

    assert select_relaxation_constraint(profile) is RelaxableConstraint.RUNTIME


def test_year_range_is_picked_when_tone_and_runtime_absent():
    profile = PreferenceProfile(genres=["Comedy"], year_min=2010)

    assert select_relaxation_constraint(profile) is RelaxableConstraint.YEAR_RANGE


def test_none_eligible_returns_none():
    profile = PreferenceProfile(genres=["Comedy"])

    assert select_relaxation_constraint(profile) is None


def test_hard_overridden_runtime_is_skipped_in_favor_of_the_next_constraint():
    profile = PreferenceProfile(
        genres=["Comedy"],
        runtime_max_minutes=100,
        hard_override_fields=["runtime_max_minutes"],
        year_min=2010,
    )

    assert select_relaxation_constraint(profile) is RelaxableConstraint.YEAR_RANGE


def test_hard_overridden_year_range_is_never_selected():
    profile = PreferenceProfile(
        genres=["Comedy"],
        year_min=2010,
        year_max=2020,
        hard_override_fields=["year_min", "year_max"],
    )

    assert select_relaxation_constraint(profile) is None


def test_excluded_genres_and_media_type_are_never_returned_as_relaxable():
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE, excluded_genres=["Horror"], genres=["Comedy"]
    )

    result = select_relaxation_constraint(profile)

    # There is no soft constraint stated here at all, so the only
    # correct outcome is None -- specifically never
    # RelaxableConstraint values that don't exist for media_type/
    # excluded_genres, since RelaxableConstraint's own closed enum
    # (tone/runtime/year_range) makes returning either structurally
    # impossible, not just a convention.
    assert result is None
