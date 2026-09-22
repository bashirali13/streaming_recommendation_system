"""Unit tests for the RecommendationAgent's deterministic decisions: hard
re-filtering, soft-fit scoring/ranking, near-duplicate exclusion, and
weak-evidence detection (constitution Principle II, NFR-001) -- none of
this depends on a model call, and it's exercised only implicitly by the
e2e tests, so it's tested directly here too.
"""

from streaming_discovery.agents.recommendation_agent import (
    _deduplicate,
    _hard_filter,
    _has_weak_tone_evidence,
    _soft_score,
)
from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile


def _candidate(**overrides) -> CandidateMedia:
    defaults = dict(
        tmdb_id=1,
        media_type=MediaType.MOVIE,
        title="A Title",
        overview="An overview.",
        vote_average=7.0,
    )
    defaults.update(overrides)
    return CandidateMedia(**defaults)


class TestHardFilter:
    def test_excludes_wrong_media_type(self):
        profile = PreferenceProfile(media_type=MediaType.TV, genres=["Drama"])
        candidates = [_candidate(media_type=MediaType.MOVIE)]

        assert _hard_filter(profile, candidates) == []

    def test_excludes_excluded_genre(self):
        profile = PreferenceProfile(genres=["Thriller"], excluded_genres=["Horror"])
        candidates = [_candidate(genres=["Horror"]), _candidate(tmdb_id=2, genres=["Drama"])]

        result = _hard_filter(profile, candidates)

        assert [c.tmdb_id for c in result] == [2]


class TestSoftScore:
    def test_matching_genre_and_liked_title_increase_score(self):
        profile = PreferenceProfile(genres=["Drama"], liked_titles=["A Title"])
        plain = _candidate(tmdb_id=1, title="Other", genres=[], vote_average=7.0)
        matching = _candidate(tmdb_id=2, title="A Title", genres=["Drama"], vote_average=7.0)

        assert _soft_score(profile, matching) > _soft_score(profile, plain)

    def test_disliked_title_decreases_score(self):
        profile = PreferenceProfile(genres=["Drama"], disliked_titles=["A Title"])
        disliked = _candidate(title="A Title", vote_average=7.0)

        assert _soft_score(profile, disliked) < disliked.vote_average

    def test_candidate_thematically_similar_to_a_disliked_title_is_deprioritized(self):
        """A candidate is never named after the disliked title (Discovery
        already hard-excludes an exact match), but shares its name as a
        keyword/reference in its overview -- the soft, thematic-similarity
        case User Story 3 asks for, distinct from the exact-match case
        above. RecommendationAgent cannot call TMDB to learn the disliked
        title's own genres (contracts/recommendation-agent.md), so this
        uses the same text-overlap heuristic already used for tone
        descriptors, deliberately weaker than the exact-match penalty.
        """
        profile = PreferenceProfile(genres=["Drama"], disliked_titles=["Bleak City"])
        similar_to_disliked = _candidate(
            title="Different Title", overview="A spiritual successor to Bleak City."
        )
        unrelated = _candidate(tmdb_id=2, title="Other Title", overview="Nothing related.")

        assert _soft_score(profile, similar_to_disliked) < _soft_score(profile, unrelated)


class TestWeakToneEvidence:
    def test_no_descriptors_stated_is_never_weak(self):
        profile = PreferenceProfile(genres=["Drama"])
        candidate = _candidate(overview="Nothing relevant here.")

        assert _has_weak_tone_evidence(profile, candidate) is False

    def test_descriptor_present_in_overview_is_not_weak(self):
        profile = PreferenceProfile(tone_descriptors=["dark"])
        candidate = _candidate(overview="A dark and moody tale.")

        assert _has_weak_tone_evidence(profile, candidate) is False

    def test_descriptor_absent_from_overview_and_keywords_is_weak(self):
        profile = PreferenceProfile(tone_descriptors=["dark"])
        candidate = _candidate(overview="A cheerful romp.", thematic_keywords=["comedy"])

        assert _has_weak_tone_evidence(profile, candidate) is True


class TestDeduplicate:
    def test_keeps_the_first_higher_ranked_occurrence_of_a_duplicate_title(self):
        ranked = [
            _candidate(tmdb_id=1, title="Same Title", vote_average=8.0),
            _candidate(tmdb_id=2, title="same title", vote_average=6.0),  # near-dupe, lower rank
            _candidate(tmdb_id=3, title="Different", vote_average=7.0),
        ]

        result = _deduplicate(ranked)

        assert [c.tmdb_id for c in result] == [1, 3]
