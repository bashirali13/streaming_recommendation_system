"""Unit test: the relaxation-priority helper picks the first eligible
constraint in the fixed order (runtime -> year_range) present on the
profile, and never returns excluded_genres, media_type, genres, or any
hard_override_fields entry as relaxable (FR-011, FR-010).

Mood/tone words are not a relaxable constraint: they are never sent to TMDB
as filters in the first place (T111), so there is nothing to relax.
"""

import pytest

from streaming_discovery.agents.orchestrator import Orchestrator, select_relaxation_constraint
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile


def test_runtime_is_picked_first_when_present():
    profile = PreferenceProfile(genres=["Comedy"], runtime_max_minutes=100, year_min=2010)

    assert select_relaxation_constraint(profile) is RelaxableConstraint.RUNTIME


def test_year_range_is_picked_when_runtime_absent():
    profile = PreferenceProfile(genres=["Comedy"], year_min=2010)

    assert select_relaxation_constraint(profile) is RelaxableConstraint.YEAR_RANGE


def test_none_eligible_returns_none():
    profile = PreferenceProfile(genres=["Comedy"])

    assert select_relaxation_constraint(profile) is None


def test_mood_words_alone_are_never_relaxable():
    """A request with only genre + mood has nothing legitimate to relax:
    dropping the genre would return unrelated titles (T111)."""
    profile = PreferenceProfile(genres=["Romance"], tone_descriptors=["sweet", "passionate"])

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

    # No soft constraint is stated, so the only correct outcome is None;
    # RelaxableConstraint's closed enum (runtime/year_range) makes returning
    # media_type or excluded_genres structurally impossible.
    assert select_relaxation_constraint(profile) is None


def _orchestrator() -> Orchestrator:
    class _Unused:
        async def run(self, *args, **kwargs):
            raise NotImplementedError

    return Orchestrator(
        preference_agent=_Unused(), discovery_agent=_Unused(), region="US", result_limit=20
    )


@pytest.mark.parametrize("relaxed", [RelaxableConstraint.RUNTIME, RelaxableConstraint.YEAR_RANGE])
def test_no_relaxation_ever_drops_the_genre(relaxed):
    """A stated genre is a fact about what the user wants. Relaxing a
    constraint to find matches must never widen the search to other genres
    (a romance request that fell back to "any popular title" returned
    Spider-Man, T111)."""
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE,
        genres=["Romance"],
        runtime_max_minutes=100,
        year_min=2010,
    )
    orchestrator = _orchestrator()

    [retried_query] = orchestrator.build_discovery_queries(
        profile, retry_number=1, relaxed_constraint=relaxed
    )

    assert retried_query.included_genres == ["Romance"]


def test_vibe_keywords_are_built_from_setting_and_theme_only():
    """Concrete subject matter (a theme like "heist", a setting like
    "winter") can be searched on TMDB's keyword catalog. Mood/tone words
    never are (T111): TMDB tags "sweet" on 27 movies and "passionate" on 7
    in its whole catalog, so requiring them wiped out valid answers. Mood is
    used for ranking instead."""
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE,
        tone_descriptors=["quirky humor", "sweet"],
        setting_descriptors=["European architecture"],
        theme_descriptors=["fairy tale"],
    )
    orchestrator = _orchestrator()

    [query] = orchestrator.build_discovery_queries(profile, retry_number=0)

    assert query.vibe_keywords == ["European architecture", "fairy tale"]


def test_a_mood_only_request_sends_no_keywords_at_all():
    profile = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["cozy", "slow"])
    orchestrator = _orchestrator()

    [query] = orchestrator.build_discovery_queries(profile, retry_number=0)

    assert query.vibe_keywords == []


def test_excluded_keywords_are_passed_through_and_never_relaxed():
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE,
        theme_descriptors=["superhero"],
        excluded_keywords=["Marvel", "DC"],
        runtime_max_minutes=100,
    )
    orchestrator = _orchestrator()

    [initial_query] = orchestrator.build_discovery_queries(profile, retry_number=0)
    [retried_query] = orchestrator.build_discovery_queries(
        profile, retry_number=1, relaxed_constraint=RelaxableConstraint.RUNTIME
    )

    assert initial_query.excluded_keywords == ["Marvel", "DC"]
    assert retried_query.excluded_keywords == ["Marvel", "DC"]


def test_relaxing_runtime_leaves_vibe_keywords_untouched():
    profile = PreferenceProfile(
        media_type=MediaType.MOVIE,
        tone_descriptors=["cozy"],
        theme_descriptors=["heist"],
        runtime_max_minutes=100,
    )
    orchestrator = _orchestrator()

    [retried_query] = orchestrator.build_discovery_queries(
        profile, retry_number=1, relaxed_constraint=RelaxableConstraint.RUNTIME
    )

    assert retried_query.vibe_keywords == ["heist"]
