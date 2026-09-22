"""Contract tests for PreferenceProfile (data-model.md 'PreferenceProfile')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


@pytest.mark.contract
class TestPreferenceProfileValid:
    def test_minimal_valid_profile_with_media_type_only(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE)
        assert profile.media_type is MediaType.MOVIE
        assert profile.providers == []
        assert profile.hard_override_fields == []

    def test_valid_profile_with_year_range(self):
        profile = PreferenceProfile(genres=["Drama"], year_min=2010, year_max=2020)
        assert profile.year_min == 2010
        assert profile.year_max == 2020

    def test_blank_optional_fields_stay_unspecified(self):
        profile = PreferenceProfile(tone_descriptors=["dark", "moody"])
        assert profile.media_type is None
        assert profile.providers == []
        assert profile.runtime_max_minutes is None
        assert profile.season_count_max is None


@pytest.mark.contract
class TestPreferenceProfileInvalid:
    def test_entirely_empty_profile_rejected(self):
        with pytest.raises(ValidationError):
            PreferenceProfile()

    def test_year_min_greater_than_year_max_rejected(self):
        with pytest.raises(ValidationError):
            PreferenceProfile(genres=["Comedy"], year_min=2020, year_max=2010)
