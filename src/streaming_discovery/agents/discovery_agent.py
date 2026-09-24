"""DiscoveryAgent: uses TMDB to produce a bounded, normalized candidate
pool for one discovery attempt.

See specs/001-streaming-discovery-assistant/contracts/discovery-agent.md.

Deterministic (NFR-008): no language-model call anywhere in this module.
"""

from __future__ import annotations

import asyncio

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.tmdb.client import TmdbAdapterError, TmdbClient
from streaming_discovery.tmdb.normalize import MOVIE_GENRES, TV_GENRES, normalize_candidate

_MAX_CONCURRENT_DETAIL_LOOKUPS = 8


def _mentions_excluded_person(detail: dict, excluded_person_ids: list[int]) -> bool:
    """T107: rejects a candidate whose cast OR crew includes an excluded
    person (actor or director) -- TMDB's `/discover` endpoints have no
    `without_people` equivalent (confirmed live), so this is the only
    enforcement path for a person exclusion, the same shape as T095's
    `_mentions_excluded_company` but against `credits` instead of
    `production_companies`. `excluded_person_ids` is resolved once per
    `run()` call via `resolve_person_ids`, not recomputed per candidate.
    """
    if not excluded_person_ids:
        return False
    credits_payload = detail.get("credits", {})
    people = credits_payload.get("cast", []) + credits_payload.get("crew", [])
    person_ids_in_credits = {person["id"] for person in people}
    return bool(person_ids_in_credits & set(excluded_person_ids))


def _mentions_excluded_company(detail: dict, query: DiscoveryQuery) -> bool:
    """Defensive re-check against TMDB's `production_companies` (T095),
    applied after the detail() call. Neither the title/overview text
    match nor TMDB's own `without_keywords` filter can be relied on for
    a franchise/studio exclusion: a real TMDB overview almost never
    names the parent studio/publisher, and TMDB's own keyword tagging
    for something like "Marvel" is inconsistent -- confirmed
    empirically, "Spider-Man: Into the Spider-Verse"'s real TMDB
    keywords are ["superhero", "based on comic", "aftercreditsstinger",
    "alternate universe"], no "marvel" at all, while its real
    `production_companies` includes "Marvel Entertainment".
    `production_companies` is the reliably-populated signal for this.
    """
    if not query.excluded_keywords:
        return False
    company_names = " ".join(
        company.get("name", "") for company in detail.get("production_companies", [])
    ).lower()
    return any(term.lower() in company_names for term in query.excluded_keywords)


def _survives_hard_filter(raw_item: dict, query: DiscoveryQuery) -> bool:
    """Client-side hard filtering, applied to the bulk (un-enriched) item
    *before* spending a detail-level call on it -- exact-match
    exclude_titles (FR-010), a defensive excluded_genres re-check using
    the bulk item's own genre_ids, and (T091) a defensive
    excluded_keywords text-match re-check against the item's own
    title/overview. TMDB's with_genres/without_genres/without_keywords
    query params already apply these server-side where TMDB's own
    tagging covers them; this is belt-and-suspenders so a detail() call
    is never wasted on a candidate that was always going to be excluded
    -- and, for excluded_keywords specifically, the only enforcement
    that doesn't depend on TMDB's keyword tagging being complete for the
    excluded concept (FR-010: a hard exclusion is never silently
    dropped just because the primary, TMDB-side mechanism missed it).
    """
    title = raw_item.get("title") or raw_item.get("name") or ""
    if title in query.exclude_titles:
        return False
    genre_table = MOVIE_GENRES if query.media_type.value == "movie" else TV_GENRES
    genre_names = {genre_table[gid] for gid in raw_item.get("genre_ids", []) if gid in genre_table}
    if genre_names & set(query.excluded_genres):
        return False
    if query.excluded_keywords:
        haystack = f"{title} {raw_item.get('overview', '')}".lower()
        if any(term.lower() in haystack for term in query.excluded_keywords):
            return False
    return True


def _states_facts_similar_cannot_honor(query: DiscoveryQuery) -> bool:
    return bool(
        query.provider_names
        or query.year_min is not None
        or query.year_max is not None
        or query.runtime_max_minutes is not None
        or query.languages
    )


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
                raw_items = await self._discover(query, query.included_genres)
        except TmdbAdapterError as exc:
            return CandidatePool(candidates=[], retry_number=query.retry_number, error=exc.error)

        survivors = [item for item in raw_items if _survives_hard_filter(item, query)]

        excluded_person_ids = (
            await self._tmdb.resolve_person_ids(query.excluded_keywords)
            if query.excluded_keywords
            else []
        )

        try:
            details = await self._fetch_details(query, survivors)
        except TmdbAdapterError as exc:
            return CandidatePool(candidates=[], retry_number=query.retry_number, error=exc.error)

        candidates: list[CandidateMedia] = []
        for item, detail in zip(survivors, details, strict=True):
            if _mentions_excluded_company(detail, query):
                continue
            if _mentions_excluded_person(detail, excluded_person_ids):
                continue
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

    async def _fetch_details(self, query: DiscoveryQuery, items: list[dict]) -> list[dict]:
        """Detail lookups for every survivor, a few at a time (T114), in the
        survivors' own order. The first TMDB failure is raised."""
        limit = asyncio.Semaphore(_MAX_CONCURRENT_DETAIL_LOOKUPS)

        async def one(item: dict) -> dict:
            async with limit:
                return await self._tmdb.details(media_type=query.media_type, tmdb_id=item["id"])

        return list(await asyncio.gather(*(one(item) for item in items)))

    async def _discover(self, query: DiscoveryQuery, included_genres: list[str]) -> list[dict]:
        return await self._tmdb.discover(
            media_type=query.media_type,
            region=query.region,
            provider_names=query.provider_names,
            included_genres=included_genres,
            excluded_genres=query.excluded_genres,
            excluded_keywords=query.excluded_keywords,
            vibe_keywords=query.vibe_keywords,
            languages=query.languages,
            year_min=query.year_min,
            year_max=query.year_max,
            runtime_max_minutes=query.runtime_max_minutes,
            result_limit=query.result_limit,
        )

    async def _discover_via_similarity(self, query: DiscoveryQuery) -> list[dict]:
        """When the user named liked titles (User Story 3), source
        candidates from TMDB's similar-title lookups for those titles --
        title -> id resolution, then similar(), merged and de-duplicated
        by id. TMDB's similar list is unfiltered, so when the user also
        stated facts it cannot honor (a service, years, a runtime, a
        language) a filtered discover query, built from the seed's own
        genres unless the user named some, is added after it (T115).
        """
        seen_ids: set[int] = set()
        merged: list[dict] = []
        seed_genres: list[str] = []
        wants_filters = _states_facts_similar_cannot_honor(query)
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
            if wants_filters and not query.included_genres:
                seed = await self._tmdb.details(media_type=query.media_type, tmdb_id=seed_id)
                for genre in seed.get("genres", []):
                    if genre["name"] not in seed_genres:
                        seed_genres.append(genre["name"])
        merged = merged[: query.result_limit]
        if wants_filters:
            filtered = await self._discover(query, query.included_genres or seed_genres[:2])
            merged.extend(item for item in filtered if item["id"] not in seen_ids)
        return merged
