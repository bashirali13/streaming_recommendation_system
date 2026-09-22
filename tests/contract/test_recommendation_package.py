"""Contract tests for RecommendationPackage (data-model.md 'RecommendationPackage')."""

import pytest
from pydantic import ValidationError

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType, RecommendationRole
from streaming_discovery.contracts.recommendation_package import (
    Recommendation,
    RecommendationPackage,
)


def _candidate(tmdb_id: int = 1) -> CandidateMedia:
    return CandidateMedia(
        tmdb_id=tmdb_id,
        media_type=MediaType.MOVIE,
        title=f"Title {tmdb_id}",
        overview="An overview.",
        vote_average=7.0,
    )


def _pick(role: RecommendationRole, tmdb_id: int = 1) -> Recommendation:
    return Recommendation(role=role, candidate=_candidate(tmdb_id), rationale="Matches your taste.")


@pytest.mark.contract
class TestRecommendationPackageValid:
    def test_only_best_match_set_is_valid_partial_fill(self):
        package = RecommendationPackage(best_match=_pick(RecommendationRole.BEST_MATCH))
        assert package.safe_pick is None
        assert package.wildcard_pick is None

    def test_all_three_roles_filled(self):
        package = RecommendationPackage(
            best_match=_pick(RecommendationRole.BEST_MATCH, tmdb_id=1),
            safe_pick=_pick(RecommendationRole.SAFE_PICK, tmdb_id=2),
            wildcard_pick=_pick(RecommendationRole.WILDCARD_PICK, tmdb_id=3),
        )
        assert package.wildcard_pick.candidate.tmdb_id == 3

    def test_zero_roles_filled_is_valid_no_match_case(self):
        package = RecommendationPackage(unresolved_notes="No candidates satisfied the runtime cap.")
        assert package.best_match is None


@pytest.mark.contract
class TestRecommendationPackageInvalid:
    def test_safe_pick_without_best_match_rejected(self):
        with pytest.raises(ValidationError):
            RecommendationPackage(safe_pick=_pick(RecommendationRole.SAFE_PICK))

    def test_wildcard_pick_without_safe_pick_rejected(self):
        with pytest.raises(ValidationError):
            RecommendationPackage(
                best_match=_pick(RecommendationRole.BEST_MATCH, tmdb_id=1),
                wildcard_pick=_pick(RecommendationRole.WILDCARD_PICK, tmdb_id=2),
            )

    def test_duplicate_tmdb_id_across_roles_rejected(self):
        with pytest.raises(ValidationError):
            RecommendationPackage(
                best_match=_pick(RecommendationRole.BEST_MATCH, tmdb_id=1),
                safe_pick=_pick(RecommendationRole.SAFE_PICK, tmdb_id=1),
            )
