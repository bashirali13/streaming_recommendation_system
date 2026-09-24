"""Contract tests for CandidateMedia (data-model.md 'CandidateMedia')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType


def _make(**overrides):
    defaults = dict(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="Arrival",
        overview="A linguist deciphers an alien language.",
        vote_average=7.9,
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


@pytest.mark.contract
class TestCandidateMediaValid:
    def test_minimal_valid_candidate(self):
        candidate = _make()
        assert candidate.tmdb_id == 1
        assert candidate.provider_names == []
        assert candidate.runtime_minutes is None
        assert candidate.season_count is None

    def test_boundary_vote_averages_accepted(self):
        assert _make(vote_average=0.0).vote_average == 0.0
        assert _make(vote_average=10.0).vote_average == 10.0


@pytest.mark.contract
class TestCandidateMediaInvalid:
    def test_negative_vote_average_rejected(self):
        with pytest.raises(ValidationError):
            _make(vote_average=-1.0)

    def test_vote_average_above_ten_rejected(self):
        with pytest.raises(ValidationError):
            _make(vote_average=10.1)

    def test_either_media_type_rejected(self):
        with pytest.raises(ValidationError):
            _make(media_type=MediaType.EITHER)


@pytest.mark.contract
class TestCandidateMediaHasNoTmdbMirroredFields:
    """Guards spec.md's Domain Model Minimization Rationale: these TMDB
    fields were deliberately excluded and must never reappear.
    """

    def test_no_excluded_fields_present(self):
        candidate = _make()
        excluded_field_names = {
            "genre_ids",
            "popularity",
            "language",
            "poster_path",
            "backdrop_path",
            "adult",
            "video",
            "original_title",
            "belongs_to_collection",
            "production_companies",
            "budget",
            "revenue",
            "homepage",
            "imdb_id",
            "tagline",
            "status",
            "source_status",
        }
        model_field_names = set(type(candidate).model_fields.keys())
        assert not (excluded_field_names & model_field_names)
