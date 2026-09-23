"""TmdbClient: the shared interface for TMDB access, plus its real,
httpx-based implementation.

See specs/001-streaming-discovery-assistant/contracts/discovery-agent.md.

Both this real implementation and the fixture-backed `FakeTmdbClient`
(tmdb/fake_client.py) honor the `TmdbClient` Protocol, so the Discovery
Agent never depends on which one is wired in (research.md Section 5).

Return values are raw TMDB-shaped dicts, not a project contract -- this
package is the only place raw TMDB shape is allowed to leak into; the rest
of the application only ever sees `normalize.py`'s output (FR-008).
"""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from streaming_discovery.contracts.candidate_pool import TmdbErrorInfo
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.normalize import genre_ids_for_names

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_PAGES_PER_CALL = 10
"""Absolute ceiling on pages fetched per call, independent of
result_limit -- a second, defensive guard against unbounded pagination
(NFR-003) if result_limit is ever misconfigured to something very large.
"""

_IMPOSSIBLE_PROVIDER_ID = -1
"""Sent as `with_watch_providers` when none of a non-empty
`provider_names` list resolves to a real TMDB provider id (T086).
`providers` is always a hard constraint (FR-010): a name TMDB can't be
asked about must make the query fail closed (guaranteed zero results),
never silently drop the filter and search every provider instead.
"""

_MAX_VIBE_KEYWORD_IDS = 10
"""Ceiling on resolved TMDB keyword ids per discover() call (T087) --
tone/setting/theme descriptors are unbounded user input; this keeps
`with_keywords` from growing without bound."""

_VIBE_SEARCH_STOPWORDS = {"and", "the", "with", "that", "this", "from", "your"}
"""Skipped during the per-word fallback in `_resolve_vibe_keyword_ids`
(T087) -- common connective words that would waste a keyword-search call
and never usefully match a TMDB keyword."""


def _match_language(name: str, table: dict[str, str]) -> str | None:
    """Resolve one user/LLM-given language name against TMDB's own
    language list (T104), the same exact-then-substring approach
    `_match_provider` uses -- "Spanish" must exact-match "Spanish"
    outright, while a looser phrase like "Mandarin Chinese" should still
    resolve via substring against TMDB's "Chinese" entry. Among
    substring matches, the shortest name is preferred as the more
    likely canonical entry.
    """
    lowered = name.lower()
    for language_name, code in table.items():
        if language_name.lower() == lowered:
            return code
    candidates = [
        (language_name, code)
        for language_name, code in table.items()
        if lowered in language_name.lower() or language_name.lower() in lowered
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda pair: len(pair[0]))
    return candidates[0][1]


def _match_provider(name: str, table: dict[str, int]) -> int | None:
    """Resolve one user/LLM-given provider name against TMDB's live
    provider list (T086). Exact case-insensitive match first -- "Apple
    TV" and "Apple TV Plus" are two distinct real TMDB providers, so an
    exact hit must win outright. Falls back to a substring match (either
    direction) so a casual name like "Prime" still resolves to "Amazon
    Prime Video"; among substring matches, the shortest provider name is
    preferred as the more likely canonical entry over a niche bundled-
    channel variant.
    """
    lowered = name.lower()
    for provider_name, provider_id in table.items():
        if provider_name.lower() == lowered:
            return provider_id
    candidates = [
        (provider_name, provider_id)
        for provider_name, provider_id in table.items()
        if lowered in provider_name.lower() or provider_name.lower() in lowered
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda pair: len(pair[0]))
    return candidates[0][1]


class TmdbAdapterError(Exception):
    """Raised by both `RealTmdbClient` and `FakeTmdbClient` on a genuine
    TMDB failure (timeout, HTTP error, or malformed response) -- a single,
    uniform error boundary regardless of which implementation is wired in.
    Carries the same `TmdbErrorInfo` shape a `CandidatePool.error` field
    expects (FR-027), so a caller can wrap it directly:
    ``CandidatePool(candidates=[], error=exc.error)``.
    """

    def __init__(self, error: TmdbErrorInfo) -> None:
        super().__init__(error.detail)
        self.error = error


class TmdbClient(Protocol):
    """Structural interface both `RealTmdbClient` and `FakeTmdbClient`
    satisfy. Every method accepts (or is otherwise bounded by) a
    `result_limit` and must never return more items than that bound.
    """

    async def discover(
        self,
        *,
        media_type: MediaType,
        region: str,
        provider_names: list[str],
        included_genres: list[str],
        excluded_genres: list[str],
        excluded_keywords: list[str],
        vibe_keywords: list[str],
        languages: list[str],
        year_min: int | None,
        year_max: int | None,
        runtime_max_minutes: int | None,
        result_limit: int,
    ) -> list[dict]:
        """Bulk candidate search. Filters are expressed as TMDB query
        parameters wherever TMDB supports them server-side (FR-029) --
        genre, year range, provider/region, (for movies) runtime, (T087)
        setting/theme descriptors resolved to TMDB keyword ids, (T091)
        excluded_keywords (franchise/studio/etc. exclusions) resolved the
        same way but applied as an exclusion, and (T104) `languages`
        (original-language names, e.g. "Korean") resolved to a single
        ISO 639-1 code via TMDB's own language list -- `with_original_
        language` only accepts one value, unlike genre/keyword/company
        params, so only the first name that resolves is used; this is a
        soft signal like vibe_keywords, not a hard constraint, so an
        unresolvable name is dropped rather than failing the query closed.
        """
        ...

    async def search_title(self, *, media_type: MediaType, title: str) -> int | None:
        """Resolve a title to a TMDB id (for liked/disliked title
        resolution), or None if no match is found.
        """
        ...

    async def similar(
        self, *, media_type: MediaType, tmdb_id: int, result_limit: int
    ) -> list[dict]:
        """Titles similar to the given seed id (User Story 3)."""
        ...

    async def details(self, *, media_type: MediaType, tmdb_id: int) -> dict:
        """Detail-level data not present in bulk results: runtime (movie)
        or episode run time / season count (tv), watch/providers, and
        keywords. Called only for finalist candidates, except for a TV
        hard runtime/season-count constraint -- see the Discovery Agent
        contract's hard-filter exception.
        """
        ...


def build_real_tmdb_client(
    api_token: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> RealTmdbClient:
    """Production wiring: a `RealTmdbClient` backed by a real httpx
    `AsyncClient`. Tests construct `RealTmdbClient` directly with a
    mock-transport client instead of using this factory.
    """
    http_client = httpx.AsyncClient(
        base_url=TMDB_BASE_URL,
        headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
        timeout=timeout_seconds,
    )
    return RealTmdbClient(http_client=http_client)


class RealTmdbClient:
    """httpx-based TMDB adapter. Every network call goes through
    `self._http`, which callers may construct with a mock transport for
    testing (see tests/tmdb_adapter/test_pagination_bound.py).
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._provider_table_cache: dict[tuple[MediaType, str], dict[str, int]] = {}
        self._keyword_id_cache: dict[str, list[int]] = {}
        self._language_table_cache: dict[str, str] | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _provider_table(self, media_type: MediaType, region: str) -> dict[str, int]:
        """Provider name -> id, fetched from TMDB's own provider list and
        cached per (media_type, region) for this client's lifetime (T086)
        -- one extra call per session at most, not one per discover() call.
        """
        cache_key = (media_type, region)
        if cache_key not in self._provider_table_cache:
            prefix = "movie" if media_type is MediaType.MOVIE else "tv"
            payload = await self._get_json(f"/watch/providers/{prefix}", {"watch_region": region})
            self._provider_table_cache[cache_key] = {
                entry["provider_name"]: entry["provider_id"] for entry in payload.get("results", [])
            }
        return self._provider_table_cache[cache_key]

    async def _resolve_provider_ids(
        self, provider_names: list[str], media_type: MediaType, region: str
    ) -> list[int]:
        table = await self._provider_table(media_type, region)
        resolved = [
            pid
            for pid in (_match_provider(name, table) for name in provider_names)
            if pid is not None
        ]
        return resolved or [_IMPOSSIBLE_PROVIDER_ID]

    async def _search_keyword_ids(self, text: str) -> list[int]:
        """TMDB keyword ids matching a free-text search, cached per exact
        query string for this client's lifetime (T087) -- avoids
        re-searching the same descriptor across the movie/tv dual query
        or a retry that doesn't relax tone.
        """
        if text not in self._keyword_id_cache:
            payload = await self._get_json("/search/keyword", {"query": text})
            self._keyword_id_cache[text] = [entry["id"] for entry in payload.get("results", [])]
        return self._keyword_id_cache[text]

    async def _resolve_keyword_ids(self, phrases: list[str]) -> list[int]:
        """One TMDB keyword id per phrase, at most (T087, reused by T091
        for excluded_keywords): search the phrase whole first (TMDB's
        keyword search already does fuzzy/substring matching); on a
        miss, fall back to searching its individual words, since a
        multi-word phrase like "beautiful European architecture" is
        unlikely to match a TMDB keyword's name exactly but
        "architecture" alone might. A phrase with no match at all is
        simply dropped, not sent through as noise -- for `vibe_keywords`
        this is correct because setting/theme descriptors are soft
        (data-model.md); for `excluded_keywords` (hard) it's still
        correct because dropping it here doesn't drop the exclusion
        itself, only this one (best-effort) enforcement layer -- the
        defense-in-depth text-match checks in the Discovery Agent and
        Recommendation Agent don't depend on this resolution succeeding.
        """
        resolved: list[int] = []
        for phrase in phrases:
            ids = await self._search_keyword_ids(phrase)
            if not ids:
                for word in phrase.split():
                    cleaned = word.strip(".,!?\"'").lower()
                    if len(cleaned) <= 3 or cleaned in _VIBE_SEARCH_STOPWORDS:
                        continue
                    ids = await self._search_keyword_ids(cleaned)
                    if ids:
                        break
            if ids:
                resolved.append(ids[0])
            if len(resolved) >= _MAX_VIBE_KEYWORD_IDS:
                break
        return resolved

    async def _language_table(self) -> dict[str, str]:
        """English language name -> ISO 639-1 code, fetched from TMDB's
        own language list and cached for this client's lifetime (T104,
        mirroring `_provider_table`'s caching pattern) -- one extra call
        per session at most. `/configuration/languages` returns a bare
        JSON array rather than an object, so this goes through
        `_get_json_list` rather than `_get_json`.
        """
        if self._language_table_cache is None:
            payload = await self._get_json_list("/configuration/languages", {})
            self._language_table_cache = {
                entry["english_name"]: entry["iso_639_1"]
                for entry in payload
                if entry.get("english_name") and entry.get("iso_639_1")
            }
        return self._language_table_cache

    async def _resolve_language_code(self, languages: list[str]) -> str | None:
        """`with_original_language` only accepts a single ISO 639-1 code
        (T104, confirmed live -- unlike with_genres/with_keywords/
        with_companies, it does not support comma/pipe multi-value
        syntax), so this returns at most one code: the first stated
        language that resolves. `languages` is a soft signal like
        vibe_keywords, not a hard constraint (data-model.md), so a name
        TMDB's list doesn't recognize is simply skipped, not failed
        closed.
        """
        table = await self._language_table()
        for name in languages:
            code = _match_language(name, table)
            if code is not None:
                return code
        return None

    async def discover(
        self,
        *,
        media_type: MediaType,
        region: str,
        provider_names: list[str],
        included_genres: list[str],
        excluded_genres: list[str],
        excluded_keywords: list[str],
        vibe_keywords: list[str],
        languages: list[str],
        year_min: int | None,
        year_max: int | None,
        runtime_max_minutes: int | None,
        result_limit: int,
    ) -> list[dict]:
        endpoint = "/discover/movie" if media_type is MediaType.MOVIE else "/discover/tv"
        date_field = "primary_release_date" if media_type is MediaType.MOVIE else "first_air_date"

        params: dict[str, str] = {"watch_region": region}
        if provider_names:
            provider_ids = await self._resolve_provider_ids(provider_names, media_type, region)
            params["with_watch_providers"] = "|".join(str(pid) for pid in provider_ids)
        if included_genres:
            genre_ids = genre_ids_for_names(included_genres, media_type)
            if genre_ids:
                params["with_genres"] = ",".join(str(gid) for gid in genre_ids)
        if excluded_genres:
            excluded_ids = genre_ids_for_names(excluded_genres, media_type)
            if excluded_ids:
                params["without_genres"] = ",".join(str(gid) for gid in excluded_ids)
        if excluded_keywords:
            excluded_keyword_ids = await self._resolve_keyword_ids(excluded_keywords)
            if excluded_keyword_ids:
                params["without_keywords"] = "|".join(str(kid) for kid in excluded_keyword_ids)
        if year_min is not None:
            params[f"{date_field}.gte"] = f"{year_min}-01-01"
        if year_max is not None:
            params[f"{date_field}.lte"] = f"{year_max}-12-31"
        if runtime_max_minutes is not None and media_type is MediaType.MOVIE:
            params["with_runtime.lte"] = str(runtime_max_minutes)
        if languages:
            language_code = await self._resolve_language_code(languages)
            if language_code is not None:
                params["with_original_language"] = language_code

        if vibe_keywords:
            keyword_ids = await self._resolve_keyword_ids(vibe_keywords)
            if keyword_ids:
                return await self._discover_with_keyword_fallback(
                    endpoint, params, keyword_ids, result_limit=result_limit
                )

        return await self._paginate(endpoint, params, result_limit=result_limit)

    async def _discover_with_keyword_fallback(
        self,
        endpoint: str,
        base_params: dict[str, str],
        keyword_ids: list[int],
        *,
        result_limit: int,
    ) -> list[dict]:
        """T100/T101: AND semantics first -- a candidate must match every
        resolved `vibe_keywords` id (theme, setting, and tone together),
        since a compound request ("road trip and found family") should
        require all of what was named, not just one. Falls back to OR
        (matching any) only if AND finds nothing at all, and only within
        this one `discover()` call -- TMDB's `with_keywords` supports only
        one separator per call, so this can't be a single mixed
        expression, and it never consumes the Orchestrator's one
        disclosed bounded retry (FR-011), since it isn't a constraint
        relaxation, just a query-construction detail -- consistent with
        an unresolved keyword already being dropped silently rather than
        disclosed (data-model.md).
        """
        if len(keyword_ids) == 1:
            params = {**base_params, "with_keywords": str(keyword_ids[0])}
            return await self._paginate(endpoint, params, result_limit=result_limit)

        and_params = {**base_params, "with_keywords": ",".join(str(k) for k in keyword_ids)}
        results = await self._paginate(endpoint, and_params, result_limit=result_limit)
        if results:
            return results

        or_params = {**base_params, "with_keywords": "|".join(str(k) for k in keyword_ids)}
        return await self._paginate(endpoint, or_params, result_limit=result_limit)

    async def search_title(self, *, media_type: MediaType, title: str) -> int | None:
        endpoint = "/search/movie" if media_type is MediaType.MOVIE else "/search/tv"
        payload = await self._get_json(endpoint, {"query": title, "page": 1})
        results = payload.get("results", [])
        return results[0]["id"] if results else None

    async def similar(
        self, *, media_type: MediaType, tmdb_id: int, result_limit: int
    ) -> list[dict]:
        prefix = "movie" if media_type is MediaType.MOVIE else "tv"
        endpoint = f"/{prefix}/{tmdb_id}/similar"
        return await self._paginate(endpoint, {}, result_limit=result_limit)

    async def details(self, *, media_type: MediaType, tmdb_id: int) -> dict:
        prefix = "movie" if media_type is MediaType.MOVIE else "tv"
        return await self._get_json(
            f"/{prefix}/{tmdb_id}",
            {"append_to_response": "watch/providers,keywords"},
        )

    async def _paginate(
        self, endpoint: str, base_params: dict[str, str], *, result_limit: int
    ) -> list[dict]:
        collected: list[dict] = []
        page = 1
        while len(collected) < result_limit and page <= MAX_PAGES_PER_CALL:
            payload = await self._get_json(endpoint, {**base_params, "page": page})
            collected.extend(payload.get("results", []))
            total_pages = payload.get("total_pages", page)
            if page >= total_pages:
                break
            page += 1
        return collected[:result_limit]

    async def _request(self, endpoint: str, params: dict) -> object:
        """A single request, with every failure mode translated into a
        `TmdbAdapterError` carrying a `TmdbErrorInfo` -- never a raw httpx
        exception or an unhandled parse error leaking past this adapter
        (FR-027). Returns the parsed JSON body, whatever its shape --
        `_get_json`/`_get_json_list` narrow it to the shape a given
        endpoint is expected to return.
        """
        try:
            response = await self._http.get(endpoint, params=params)
        except httpx.TimeoutException as exc:
            raise TmdbAdapterError(
                TmdbErrorInfo(kind="timeout", detail=f"TMDB request timed out: {exc}")
            ) from exc
        except httpx.HTTPError as exc:
            raise TmdbAdapterError(
                TmdbErrorInfo(kind="http_error", detail=f"TMDB request failed: {exc}")
            ) from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="http_error",
                    detail=f"TMDB returned HTTP {response.status_code}",
                )
            ) from exc

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="malformed_response",
                    detail=f"TMDB response was not valid JSON: {exc}",
                )
            ) from exc

    async def _get_json(self, endpoint: str, params: dict) -> dict:
        """Most TMDB endpoints (discover, details, search) return a JSON
        object."""
        payload = await self._request(endpoint, params)
        if not isinstance(payload, dict):
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="malformed_response",
                    detail=f"Expected a JSON object from TMDB, got {type(payload).__name__}",
                )
            )
        return payload

    async def _get_json_list(self, endpoint: str, params: dict) -> list[dict]:
        """A handful of TMDB endpoints (e.g. /configuration/languages,
        T104) return a bare JSON array rather than an object."""
        payload = await self._request(endpoint, params)
        if not isinstance(payload, list):
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="malformed_response",
                    detail=f"Expected a JSON array from TMDB, got {type(payload).__name__}",
                )
            )
        return payload
