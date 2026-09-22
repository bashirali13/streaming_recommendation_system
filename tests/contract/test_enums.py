"""Contract tests for the shared enums (data-model.md 'Shared enums')."""

import pytest

from streaming_discovery.contracts.enums import (
    MediaType,
    RecommendationRole,
    RelaxableConstraint,
)


@pytest.mark.contract
class TestMediaType:
    def test_valid_values(self):
        assert MediaType("movie") is MediaType.MOVIE
        assert MediaType("tv") is MediaType.TV
        assert MediaType("either") is MediaType.EITHER

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            MediaType("book")


@pytest.mark.contract
class TestRelaxableConstraint:
    def test_valid_values(self):
        assert RelaxableConstraint("tone") is RelaxableConstraint.TONE
        assert RelaxableConstraint("runtime") is RelaxableConstraint.RUNTIME
        assert RelaxableConstraint("year_range") is RelaxableConstraint.YEAR_RANGE

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            RelaxableConstraint("genre")


@pytest.mark.contract
class TestRecommendationRole:
    def test_valid_values(self):
        assert RecommendationRole("best_match") is RecommendationRole.BEST_MATCH
        assert RecommendationRole("safe_pick") is RecommendationRole.SAFE_PICK
        assert RecommendationRole("wildcard_pick") is RecommendationRole.WILDCARD_PICK

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            RecommendationRole("runner_up")
