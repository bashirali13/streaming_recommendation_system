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

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_PAGES_PER_CALL = 10
"""Absolute ceiling on pages fetched per call, independent of
result_limit -- a second, defensive guard against unbounded pagination
(NFR-003) if result_limit is ever misconfigured to something very large.
"""


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
        year_min: int | None,
        year_max: int | None,
        runtime_max_minutes: int | None,
        result_limit: int,
    ) -> list[dict]:
        """Bulk candidate search. Filters are expressed as TMDB query
        parameters wherever TMDB supports them server-side (FR-029) --
        genre, year range, provider/region, and (for movies) runtime.
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

    async def aclose(self) -> None:
        await self._http.aclose()

    async def discover(
        self,
        *,
        media_type: MediaType,
        region: str,
        provider_names: list[str],
        included_genres: list[str],
        excluded_genres: list[str],
        year_min: int | None,
        year_max: int | None,
        runtime_max_minutes: int | None,
        result_limit: int,
    ) -> list[dict]:
        endpoint = "/discover/movie" if media_type is MediaType.MOVIE else "/discover/tv"
        date_field = "primary_release_date" if media_type is MediaType.MOVIE else "first_air_date"

        params: dict[str, str] = {"watch_region": region}
        if provider_names:
            # NOTE: TMDB's with_watch_providers expects numeric provider ids,
            # not names. Passing names through is a placeholder until
            # provider-name -> id resolution is added alongside the
            # Discovery Agent's provider-filtering wiring (tasks.md T042).
            params["with_watch_providers"] = "|".join(provider_names)
        if included_genres:
            params["with_genres"] = ",".join(included_genres)
        if excluded_genres:
            params["without_genres"] = ",".join(excluded_genres)
        if year_min is not None:
            params[f"{date_field}.gte"] = f"{year_min}-01-01"
        if year_max is not None:
            params[f"{date_field}.lte"] = f"{year_max}-12-31"
        if runtime_max_minutes is not None and media_type is MediaType.MOVIE:
            params["with_runtime.lte"] = str(runtime_max_minutes)

        return await self._paginate(endpoint, params, result_limit=result_limit)

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

    async def _get_json(self, endpoint: str, params: dict) -> dict:
        """A single request, with every failure mode translated into a
        `TmdbAdapterError` carrying a `TmdbErrorInfo` -- never a raw httpx
        exception or an unhandled parse error leaking past this adapter
        (FR-027).
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
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="malformed_response",
                    detail=f"TMDB response was not valid JSON: {exc}",
                )
            ) from exc

        if not isinstance(payload, dict):
            raise TmdbAdapterError(
                TmdbErrorInfo(
                    kind="malformed_response",
                    detail=f"Expected a JSON object from TMDB, got {type(payload).__name__}",
                )
            )
        return payload
