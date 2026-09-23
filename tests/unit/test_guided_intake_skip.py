"""Unit tests: which guided-intake questions to skip, and what
"already noted" preview to show, given a partial `PreferenceProfile`
already interpreted from free text alone (T085; spec.md line 308 --
"the system may skip asking about a field it can already infer as
unnecessary").

The three single-field questions (format, services, exclusions) map
1:1 to one PreferenceProfile field each, so they can be skipped
outright once that field is populated. The two compound questions
(mood_and_interests, optional_constraints) each cover several fields
at once; skipping them outright could silently drop whichever of
those fields free text didn't cover, so they are never reported as
"already answered" -- only previewed.
"""

from streaming_discovery.cli.intake import _already_answered, _already_noted_note
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


class TestAlreadyAnswered:
    def test_format_is_answered_when_media_type_is_set(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE)
        assert _already_answered("format", profile) is True

    def test_format_is_not_answered_when_media_type_is_unset(self):
        profile = PreferenceProfile(tone_descriptors=["dark"])
        assert _already_answered("format", profile) is False

    def test_services_is_answered_when_providers_is_set(self):
        profile = PreferenceProfile(providers=["Netflix"])
        assert _already_answered("services", profile) is True

    def test_exclusions_is_answered_when_excluded_genres_is_set(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE, excluded_genres=["Romance"])
        assert _already_answered("exclusions", profile) is True

    def test_mood_and_interests_is_never_reported_as_fully_answered(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["dark", "gritty"])
        assert _already_answered("mood_and_interests", profile) is False

    def test_optional_constraints_is_never_reported_as_fully_answered(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE, year_min=1990, year_max=2010)
        assert _already_answered("optional_constraints", profile) is False


class TestAlreadyNotedNote:
    def test_mood_note_combines_genre_and_tone_descriptors(self):
        profile = PreferenceProfile(
            media_type=MediaType.MOVIE, genres=["Thriller"], tone_descriptors=["dark", "gritty"]
        )
        note = _already_noted_note("mood_and_interests", profile)
        assert note is not None
        assert "Thriller" in note
        assert "dark" in note
        assert "gritty" in note

    def test_mood_note_is_none_when_nothing_to_show(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE, providers=["Netflix"])
        assert _already_noted_note("mood_and_interests", profile) is None

    def test_optional_constraints_note_combines_year_range_and_runtime(self):
        profile = PreferenceProfile(
            media_type=MediaType.MOVIE, year_min=1990, year_max=2010, runtime_max_minutes=140
        )
        note = _already_noted_note("optional_constraints", profile)
        assert note is not None
        assert "1990" in note
        assert "2010" in note
        assert "140" in note

    def test_optional_constraints_note_is_none_when_nothing_to_show(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE)
        assert _already_noted_note("optional_constraints", profile) is None

    def test_format_and_services_never_get_a_note(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE, providers=["Netflix"])
        assert _already_noted_note("format", profile) is None
        assert _already_noted_note("services", profile) is None
