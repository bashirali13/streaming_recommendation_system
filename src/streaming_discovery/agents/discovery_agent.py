"""DiscoveryAgent: uses TMDB to produce a bounded, normalized candidate
pool for one discovery attempt.

See specs/001-streaming-discovery-assistant/contracts/discovery-agent.md.

Deterministic (NFR-008): no language-model call anywhere in this module.
"""

from __future__ import annotations

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.tmdb.client import TmdbAdapterError, TmdbClient
from streaming_discovery.tmdb.normalize import MOVIE_GENRES, TV_GENRES, normalize_candidate


def _survives_hard_filter(raw_item: dict, query: DiscoveryQuery) -> bool:
    """Client-side hard filtering, applied to the bulk (un-enriched) item
    *before* spending a detail-level call on it -- exact-match
    exclude_titles (FR-010), and a defensive excluded_genres re-check
    using the bulk item's own genre_ids. TMDB's with_genres/
    without_genres query params already apply this server-side; this is
    belt-and-suspenders so a detail() call is never wasted on a
    candidate that was always going to be excluded.
    """
    title = raw_item.get("title") or raw_item.get("name") or ""
    if title in query.exclude_titles:
        return False
    genre_table = MOVIE_GENRES if query.media_type.value == "movie" else TV_GENRES
    genre_names = {genre_table[gid] for gid in raw_item.get("genre_ids", []) if gid in genre_table}
    if genre_names & set(query.excluded_genres):
        return False
    return True


class DiscoveryAgent:
    """Consumes a `DiscoveryQuery`, produces a `CandidatePool`. Never
    receives a `PreferenceProfile` directly, never interprets ambiguous
    intent, never ranks, never decides whether a retry is warranted
    (contracts/discovery-agent.md).
    """

    def __init__(self, *, tmdb_client: TmdbClient) -> None:
        self._tmdb = tmdb_client

    async def run(self, query: DiscoveryQuery) -> CandidatePool:
        try:
            if query.similarity_seed_titles:
                raw_items = await self._discover_via_similarity(query)
            else:
                raw_items = await self._tmdb.discover(
                    media_type=query.media_type,
                    region=query.region,
                    provider_names=query.provider_names,
                    included_genres=query.included_genres,
                    excluded_genres=query.excluded_genres,
                    year_min=query.year_min,
                    year_max=query.year_max,
                    runtime_max_minutes=query.runtime_max_minutes,
                    result_limit=query.result_limit,
                )
        except TmdbAdapterError as exc:
            return CandidatePool(candidates=[], retry_number=query.retry_number, error=exc.error)

        survivors = [item for item in raw_items if _survives_hard_filter(item, query)]

        candidates: list[CandidateMedia] = []
        for item in survivors:
            try:
                detail = await self._tmdb.details(media_type=query.media_type, tmdb_id=item["id"])
            except TmdbAdapterError as exc:
                return CandidatePool(
                    candidates=[], retry_number=query.retry_number, error=exc.error
                )
            merged = {**item, **detail}
            candidate = normalize_candidate(
                merged, media_type=query.media_type, region=query.region, include_enrichment=True
            )
            # Defensive re-check: now that full genre names are resolved,
            # confirm no excluded genre slipped through (FR-010).
            if set(candidate.genres) & set(query.excluded_genres):
                continue
            # TV season-count hard filter (User Story 5): TMDB has no
            # server-side season-count query parameter, so this can only
            # be evaluated after the details() call above -- which every
            # survivor already gets, so no extra fetch is needed beyond
            # what FR-029's finalist-only enrichment already does for
            # this candidate (contracts/discovery-agent.md's hard-filter
            # exception). A stated season_count_max is always hard
            # (data-model.md), so an over-the-cap candidate is excluded
            # outright, never merely ranked lower.
            if (
                query.season_count_max is not None
                and candidate.season_count is not None
                and candidate.season_count > query.season_count_max
            ):
                continue
            candidates.append(candidate)

        return CandidatePool(
            candidates=candidates,
            retry_number=query.retry_number,
            relaxed_constraint=query.relaxed_constraint,
        )

    async def _discover_via_similarity(self, query: DiscoveryQuery) -> list[dict]:
        """When the user named liked titles (User Story 3), source
        candidates from TMDB's similar-title lookups for those titles
        instead of a generic discover query -- title -> id resolution,
        then similar(), merged and de-duplicated by id.
        """
        seen_ids: set[int] = set()
        merged: list[dict] = []
        for title in query.similarity_seed_titles:
            seed_id = await self._tmdb.search_title(media_type=query.media_type, title=title)
            if seed_id is None:
                continue
            similar_items = await self._tmdb.similar(
                media_type=query.media_type, tmdb_id=seed_id, result_limit=query.result_limit
            )
            for item in similar_items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    merged.append(item)
        return merged[: query.result_limit]
