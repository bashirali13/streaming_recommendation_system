"""normalize.py: raw TMDB payload -> CandidateMedia.

See specs/001-streaming-discovery-assistant/contracts/discovery-agent.md
and spec.md's Domain Model Minimization Rationale.

Genre ids are resolved to names here, once, from TMDB's static genre
list -- raw ids never travel downstream (FR-030). Release dates are
narrowed to a year. Watch-provider data is scoped to the configured
region and flatrate offers only (FR-019); rent/buy offers and other
regions' data are discarded here, not merely hidden later.
"""

from __future__ import annotations

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.enums import MediaType

# TMDB's static genre list (https://developer.themoviedb.org/reference/genre-movie-list
# and /genre-tv-list). Resolved once, here, so no raw genre id ever crosses
# into an internal contract (spec.md's Domain Model Minimization Rationale).
MOVIE_GENRES: dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}

TV_GENRES: dict[int, str] = {
    10759: "Action & Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    10762: "Kids",
    9648: "Mystery",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
    37: "Western",
}


def _genre_names(genre_ids: list[int], media_type: MediaType) -> list[str]:
    table = MOVIE_GENRES if media_type is MediaType.MOVIE else TV_GENRES
    return [table[gid] for gid in genre_ids if gid in table]


def genre_ids_for_names(genre_names: list[str], media_type: MediaType) -> list[int]:
    """The inverse of `_genre_names` (T086): TMDB's discover endpoint
    requires numeric genre ids for `with_genres`/`without_genres`, not
    names -- resolved here, case-insensitively, against the same static
    table `_genre_names` uses, so the two directions can never drift
    apart. A name that isn't one of TMDB's known genres for this media
    type is dropped rather than sent through as meaningless noise.
    """
    table = MOVIE_GENRES if media_type is MediaType.MOVIE else TV_GENRES
    name_to_id = {name.lower(): gid for gid, name in table.items()}
    return [name_to_id[name.lower()] for name in genre_names if name.lower() in name_to_id]


def _release_year(raw: dict, media_type: MediaType) -> int | None:
    date_field = "release_date" if media_type is MediaType.MOVIE else "first_air_date"
    date_value = raw.get(date_field)
    if not date_value:
        return None
    try:
        return int(str(date_value)[:4])
    except ValueError:
        return None


def _flatrate_provider_names(raw: dict, region: str) -> list[str]:
    """Scope to the configured region and flatrate (subscription) offers
    only -- rent/buy offers and other regions' data never reach this
    return value (FR-019).
    """
    watch_providers = raw.get("watch/providers") or raw.get("watch_providers") or {}
    region_data = watch_providers.get("results", {}).get(region, {})
    return [entry["provider_name"] for entry in region_data.get("flatrate", [])]


def _thematic_keywords(raw: dict, media_type: MediaType) -> list[str]:
    keywords_payload = raw.get("keywords") or {}
    key = "keywords" if media_type is MediaType.MOVIE else "results"
    return [entry["name"] for entry in keywords_payload.get(key, [])]


def _collection_id(raw: dict, media_type: MediaType) -> int | None:
    """TMDB collections are a movie-only concept -- no `/tv/{id}` field
    is an equivalent (T105), so this is always None for TV. Already
    present on the base `/movie/{id}` details response (confirmed
    live), unlike keywords/watch-providers, which need
    `append_to_response`.
    """
    if media_type is not MediaType.MOVIE:
        return None
    collection = raw.get("belongs_to_collection")
    return collection["id"] if collection else None


def normalize_candidate(
    raw: dict,
    *,
    media_type: MediaType,
    region: str,
    include_enrichment: bool = False,
) -> CandidateMedia:
    """Convert one raw TMDB item into a `CandidateMedia`.

    `raw` may be a bulk discover/search/similar list item, or that same
    item merged with a `details()` response. `include_enrichment` gates
    `runtime_minutes`/`season_count`/`provider_names`/`thematic_keywords`
    -- these are only meaningful once a `details()` call has actually been
    made for this candidate (FR-029); pass `False` for a raw bulk-list
    item that hasn't been enriched.
    """
    title = raw.get("title") or raw.get("name") or ""
    genre_ids = raw.get("genre_ids") or [g["id"] for g in raw.get("genres", [])]

    fields: dict = {
        "tmdb_id": raw["id"],
        "media_type": media_type,
        "title": title,
        "overview": raw.get("overview", ""),
        "genres": _genre_names(genre_ids, media_type),
        "release_year": _release_year(raw, media_type),
        "vote_average": raw.get("vote_average", 0.0),
    }

    if include_enrichment:
        runtime_minutes = raw.get("runtime")
        if runtime_minutes is None and media_type is MediaType.TV:
            episode_run_time = raw.get("episode_run_time") or []
            runtime_minutes = episode_run_time[0] if episode_run_time else None
        fields.update(
            runtime_minutes=runtime_minutes,
            season_count=raw.get("number_of_seasons"),
            provider_names=_flatrate_provider_names(raw, region),
            thematic_keywords=_thematic_keywords(raw, media_type),
            collection_id=_collection_id(raw, media_type),
        )

    return CandidateMedia(**fields)
