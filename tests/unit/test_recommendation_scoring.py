"""Unit tests for the RecommendationAgent's deterministic decisions: hard
re-filtering, soft-fit scoring/ranking, near-duplicate exclusion, and
weak-evidence detection (constitution Principle II, NFR-001) -- none of
this depends on a model call, and it's exercised only implicitly by the
e2e tests, so it's tested directly here too.
"""

from streaming_discovery.agents.recommendation_agent import (
    _deduplicate,
    _effective_rating,
    _hard_filter,
    _has_weak_tone_evidence,
    _rank_candidates,
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

    def test_matching_every_stated_theme_outranks_a_more_popular_partial_match(self):
        """T102: T100 made it possible to actually discover a candidate
        that satisfies every named theme (e.g. "road trip and found
        family"), but a flat per-hit bonus wasn't enough to make that
        discovery worth anything once ranked against a more popular
        title that only matches one of the two -- confirmed live: a
        real TMDB title tagged with both themes never won a slot
        against three well-known titles honestly flagged as only
        partial matches. A realistic vote_average gap (2 points) must
        not be enough to overcome full theme completeness.
        """
        profile = PreferenceProfile(theme_descriptors=["road trip", "found family"])
        full_match = _candidate(
            tmdb_id=1,
            title="Starguy",
            overview="A road trip that turns into found family along the way.",
            vote_average=5.5,
        )
        partial_match = _candidate(
            tmdb_id=2,
            title="Popular Show",
            overview="A found family grows close over time.",
            vote_average=7.5,
        )

        assert _soft_score(profile, full_match) > _soft_score(profile, partial_match)

    def test_theme_completeness_bonus_requires_every_theme_not_just_more_hits(self):
        """Guards against the bonus being satisfied by hit *count* alone
        -- two hits on the same repeated theme must not count as
        "every theme" when a different theme was also stated and missed.
        """
        profile = PreferenceProfile(theme_descriptors=["road trip", "found family"])
        one_theme_twice = _candidate(
            title="Road Movie",
            overview="A road trip. Just a road trip, entirely about the road trip.",
        )
        both_themes_once = _candidate(
            tmdb_id=2,
            title="Starguy",
            overview="A road trip that turns into found family.",
        )

        assert _soft_score(profile, both_themes_once) > _soft_score(profile, one_theme_twice)

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


class TestEffectiveRating:
    """T108: raw TMDB `vote_average` is unreliable at low vote counts --
    confirmed live, an animated Batman film with 373 votes (9.16) was
    ranked above "Project Hail Mary" with 7,938 votes (8.64), because
    nothing weighed how much evidence backed each rating. A Bayesian
    (IMDb-style) weighted rating shrinks a thinly-evidenced score toward
    the catalog-wide mean.
    """

    def test_a_thinly_voted_high_rating_is_pulled_below_a_well_established_one(self):
        thin = _candidate(tmdb_id=1, title="Thin", vote_average=9.16, vote_count=373)
        established = _candidate(
            tmdb_id=2, title="Established", vote_average=8.639, vote_count=7938
        )

        assert _effective_rating(established) > _effective_rating(thin)

    def test_with_overwhelming_votes_the_rating_is_essentially_unchanged(self):
        candidate = _candidate(vote_average=8.2, vote_count=1_000_000)

        assert abs(_effective_rating(candidate) - 8.2) < 0.01

    def test_with_no_votes_the_rating_falls_back_to_the_catalog_mean_not_zero(self):
        """A brand-new title's 0.0 means "nobody has rated it", not "it is
        terrible" -- it must not be treated as the worst possible score."""
        candidate = _candidate(vote_average=0.0, vote_count=0)

        assert 5.0 < _effective_rating(candidate) < 8.0

    def test_unknown_vote_count_uses_the_raw_rating(self):
        """Fixture/demo data and any source without a count keep working."""
        candidate = _candidate(vote_average=7.9)

        assert _effective_rating(candidate) == 7.9


class TestRankCandidates:
    def test_full_theme_match_always_outranks_a_more_popular_partial_match(self):
        """T103: T102's flat +4.0 `_soft_score` bonus for full theme
        completeness assumed realistic vote_average gaps (~2 points).
        Live-verifying against the real "road trip and found family"
        request found a far larger gap: a genuinely full-matching but
        obscure candidate with vote_average 0.0 (TMDB's real value for
        "Starguy") lost every time to popular partial matches around
        8.5-8.7 (TMDB's real values, e.g. "LEGO Monkie Kid") -- a gap no
        fixed additive bonus can be safely tuned to always beat without
        eventually overcorrecting the opposite way. Fix: rank by full
        theme completeness as a tier first, `_soft_score` only as the
        tiebreaker within a tier -- this is what actually delivers "the
        whole catalog is a candidate, not just what's already popular."
        """
        profile = PreferenceProfile(theme_descriptors=["road trip", "found family"])
        obscure_full_match = _candidate(
            tmdb_id=1,
            title="Starguy",
            overview="A road trip that turns into found family.",
            vote_average=0.0,
        )
        popular_partial_match = _candidate(
            tmdb_id=2,
            title="LEGO Monkie Kid",
            overview="Found family and adventure in modern-day China.",
            vote_average=8.662,
        )

        ranked = _rank_candidates(profile, [popular_partial_match, obscure_full_match])

        assert ranked[0].title == "Starguy"

    def test_within_a_tier_soft_score_still_breaks_the_tie(self):
        profile = PreferenceProfile(genres=["Drama"])
        higher = _candidate(tmdb_id=1, title="Higher", genres=["Drama"], vote_average=7.0)
        lower = _candidate(tmdb_id=2, title="Lower", genres=[], vote_average=7.0)

        ranked = _rank_candidates(profile, [lower, higher])

        assert ranked[0].title == "Higher"

    def test_a_well_established_title_outranks_a_thinly_voted_higher_rating(self):
        profile = PreferenceProfile(genres=["Science Fiction"])
        thin = _candidate(
            tmdb_id=1,
            title="Knightfall",
            genres=["Science Fiction"],
            vote_average=9.16,
            vote_count=373,
        )
        established = _candidate(
            tmdb_id=2,
            title="Project Hail Mary",
            genres=["Science Fiction"],
            vote_average=8.639,
            vote_count=7938,
        )

        ranked = _rank_candidates(profile, [thin, established])

        assert ranked[0].title == "Project Hail Mary"


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

    def test_a_direct_sequel_in_the_same_collection_is_treated_as_a_near_duplicate(self):
        """T105/FR-016: "the same title, or a direct sequel/prequel/
        alternate-cut of an already-selected title" -- exact-title
        matching alone can't catch two differently-titled entries in
        the same franchise (e.g. "The Bad Guys" and "The Bad Guys 2",
        both real TMDB titles sharing one real `collection_id`)."""
        ranked = [
            _candidate(tmdb_id=1, title="The Bad Guys 2", vote_average=8.0, collection_id=1231053),
            _candidate(tmdb_id=2, title="The Bad Guys", vote_average=7.5, collection_id=1231053),
            _candidate(tmdb_id=3, title="Chicken Run", vote_average=7.0, collection_id=None),
        ]

        result = _deduplicate(ranked)

        assert [c.tmdb_id for c in result] == [1, 3]

    def test_candidates_with_no_collection_are_never_treated_as_duplicates_of_each_other(self):
        """collection_id is None for the vast majority of titles
        (standalone films, and always for TV) -- two unrelated None
        values must never collapse into a false-positive duplicate."""
        ranked = [
            _candidate(tmdb_id=1, title="First", vote_average=8.0, collection_id=None),
            _candidate(tmdb_id=2, title="Second", vote_average=7.0, collection_id=None),
        ]

        result = _deduplicate(ranked)

        assert [c.tmdb_id for c in result] == [1, 2]
