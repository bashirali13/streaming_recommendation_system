"""Unit tests for the confirmation-step logic (FR-006): summarizing only
populated fields, and applying/re-validating a correction. The CLI's
interactive wiring around this logic is tested separately in User Story 1
(tests/integration/test_confirmation_free_text.py).
"""

import pytest

from streaming_discovery.agents.orchestrator import (
    ContractValidationError,
    apply_correction,
    build_confirmation_summary,
)
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


@pytest.mark.unit
class TestBuildConfirmationSummary:
    def test_only_populated_fields_are_shown(self):
        profile = PreferenceProfile(tone_descriptors=["dark", "moody"])

        summary = build_confirmation_summary(profile)

        assert "dark" in summary
        assert "moody" in summary
        assert "Format" not in summary
        assert "Providers" not in summary

    def test_media_type_is_shown_when_set(self):
        profile = PreferenceProfile(media_type=MediaType.MOVIE)

        summary = build_confirmation_summary(profile)

        assert "movie" in summary.lower()


@pytest.mark.unit
class TestApplyCorrection:
    def test_correction_is_merged_and_returned(self):
        profile = PreferenceProfile(genres=["Comedy"])

        corrected = apply_correction(profile, {"media_type": MediaType.TV})

        assert corrected.media_type is MediaType.TV
        assert corrected.genres == ["Comedy"]  # untouched fields survive

    def test_correction_producing_an_invalid_profile_is_a_controlled_failure(self):
        profile = PreferenceProfile(genres=["Comedy"])

        with pytest.raises(ContractValidationError):
            apply_correction(profile, {"genres": [], "year_min": 2020, "year_max": 2010})
