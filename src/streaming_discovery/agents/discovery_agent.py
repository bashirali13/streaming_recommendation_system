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
            candidates.append(candidate)

        return CandidatePool(
            candidates=candidates,
            retry_number=query.retry_number,
            relaxed_constraint=query.relaxed_constraint,
        )
