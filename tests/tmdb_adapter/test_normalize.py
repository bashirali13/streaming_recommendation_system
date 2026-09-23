"""Adapter test: normalize.py never carries a TMDB-mirrored field forward
and correctly scopes provider data to one region + flatrate offers only
(spec.md's Domain Model Minimization Rationale, FR-019).
"""

import pytest

from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.normalize import genre_ids_for_names, normalize_candidate

_RAW_MOVIE_LIST_ITEM = {
    "id": 550,
    "title": "Fight Club",
    "original_title": "Fight Club",
    "overview": "An insomniac office worker and a soap salesman build a global organization.",
    "genre_ids": [18, 53],
    "release_date": "1999-10-15",
    "vote_average": 8.4,
    "vote_count": 26280,
    "popularity": 61.416,
    "poster_path": "/poster.jpg",
    "backdrop_path": "/backdrop.jpg",
    "adult": False,
    "video": False,
    "original_language": "en",
}

_RAW_MOVIE_DETAILS = {
    **_RAW_MOVIE_LIST_ITEM,
    "runtime": 139,
    "budget": 63000000,
    "revenue": 100853753,
    "imdb_id": "tt0137523",
    "homepage": "https://example.com",
    "tagline": "Mischief. Mayhem. Soap.",
    "status": "Released",
    "belongs_to_collection": None,
    "production_companies": [{"id": 1, "name": "Fox"}],
    "watch/providers": {
        "results": {
            "US": {
                "link": "https://example.com",
                "flatrate": [{"provider_id": 8, "provider_name": "Netflix"}],
                "rent": [{"provider_id": 2, "provider_name": "Apple TV"}],
                "buy": [{"provider_id": 2, "provider_name": "Apple TV"}],
            },
            "GB": {
                "flatrate": [{"provider_id": 9, "provider_name": "Amazon Prime Video"}],
            },
        }
    },
    "keywords": {"keywords": [{"id": 818, "name": "insomnia"}]},
}

_RAW_SEQUEL_DETAILS = {
    **_RAW_MOVIE_DETAILS,
    "id": 551,
    "title": "Fight Club 2",
    "belongs_to_collection": {
        "id": 999,
        "name": "Fight Club Collection",
        "poster_path": None,
        "backdrop_path": None,
    },
}

_EXCLUDED_FIELD_NAMES = {
    "genre_ids",
    "popularity",
    "vote_count",
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


@pytest.mark.tmdb_adapter
def test_normalize_bulk_item_has_no_tmdb_mirrored_fields():
    candidate = normalize_candidate(_RAW_MOVIE_LIST_ITEM, media_type=MediaType.MOVIE, region="US")

    assert candidate.tmdb_id == 550
    assert candidate.genres == ["Drama", "Thriller"]
    assert candidate.release_year == 1999
    assert not (_EXCLUDED_FIELD_NAMES & set(type(candidate).model_fields.keys()))


@pytest.mark.tmdb_adapter
def test_normalize_scopes_providers_to_region_and_flatrate_only():
    candidate = normalize_candidate(
        _RAW_MOVIE_DETAILS, media_type=MediaType.MOVIE, region="US", include_enrichment=True
    )

    assert candidate.provider_names == ["Netflix"]  # not Apple TV (rent/buy), not GB's provider


@pytest.mark.tmdb_adapter
def test_normalize_without_enrichment_leaves_enrichment_fields_unset():
    candidate = normalize_candidate(_RAW_MOVIE_LIST_ITEM, media_type=MediaType.MOVIE, region="US")

    assert candidate.runtime_minutes is None
    assert candidate.provider_names == []
    assert candidate.thematic_keywords == []
    assert candidate.collection_id is None


@pytest.mark.tmdb_adapter
def test_normalize_with_enrichment_populates_runtime_and_keywords():
    candidate = normalize_candidate(
        _RAW_MOVIE_DETAILS, media_type=MediaType.MOVIE, region="US", include_enrichment=True
    )

    assert candidate.runtime_minutes == 139
    assert candidate.thematic_keywords == ["insomnia"]


@pytest.mark.tmdb_adapter
def test_normalize_leaves_collection_id_unset_when_not_part_of_a_collection():
    """`belongs_to_collection` is `None` on TMDB's own response for a
    standalone movie (T105) -- must not be confused with "not yet
    enriched"."""
    candidate = normalize_candidate(
        _RAW_MOVIE_DETAILS, media_type=MediaType.MOVIE, region="US", include_enrichment=True
    )

    assert candidate.collection_id is None


@pytest.mark.tmdb_adapter
def test_normalize_populates_collection_id_for_a_franchise_entry():
    """T105: `belongs_to_collection` is already present on TMDB's base
    `/movie/{id}` details response (confirmed live) -- no extra API call
    needed, just extraction, unlike keywords/watch-providers which
    require `append_to_response`."""
    candidate = normalize_candidate(
        _RAW_SEQUEL_DETAILS, media_type=MediaType.MOVIE, region="US", include_enrichment=True
    )

    assert candidate.collection_id == 999


@pytest.mark.tmdb_adapter
def test_normalize_tv_item_never_has_a_collection_id():
    """TMDB collections are a movie-only concept -- no `/tv/{id}` field
    provides an equivalent, so this must always be None for TV
    regardless of enrichment."""
    raw_tv = {
        "id": 700,
        "name": "Some Show",
        "overview": "n/a",
        "genre_ids": [],
        "first_air_date": "2020-01-01",
        "vote_average": 7.0,
    }
    candidate = normalize_candidate(
        raw_tv, media_type=MediaType.TV, region="US", include_enrichment=True
    )

    assert candidate.collection_id is None


@pytest.mark.tmdb_adapter
class TestGenreIdsForNames:
    """T086: TMDB's discover endpoint requires numeric genre ids for
    with_genres/without_genres, not names -- these resolve against the
    same static genre tables normalize_candidate already uses in the
    other direction (id -> name), so the two stay in sync by
    construction.
    """

    def test_resolves_known_movie_genre_names_case_insensitively(self):
        ids = genre_ids_for_names(["comedy", "Science Fiction"], MediaType.MOVIE)

        assert sorted(ids) == sorted([35, 878])

    def test_resolves_known_tv_genre_names(self):
        ids = genre_ids_for_names(["Sci-Fi & Fantasy"], MediaType.TV)

        assert ids == [10765]

    def test_unknown_genre_name_is_dropped_not_erroring(self):
        ids = genre_ids_for_names(["Comedy", "Not A Real Genre"], MediaType.MOVIE)

        assert ids == [35]

    def test_empty_input_returns_empty_list(self):
        assert genre_ids_for_names([], MediaType.MOVIE) == []
