"""Adapter test: the real TmdbClient enforces a bounded result_limit and
never paginates beyond it (NFR-003). Written before the real client exists
-- it must fail for the right reason (ImportError) first.
"""

import httpx
import pytest

from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.client import RealTmdbClient


def _page_response(page: int, total_pages: int, items_per_page: int = 20) -> dict:
    start = (page - 1) * items_per_page
    return {
        "page": page,
        "total_pages": total_pages,
        "total_results": total_pages * items_per_page,
        "results": [
            {"id": start + i, "title": f"Title {start + i}", "vote_average": 7.0}
            for i in range(items_per_page)
        ],
    }


def _many_pages_transport(total_pages: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=_page_response(page, total_pages))

    return httpx.MockTransport(handler)


def _client_with(total_pages: int) -> RealTmdbClient:
    http_client = httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3",
        transport=_many_pages_transport(total_pages),
    )
    return RealTmdbClient(http_client=http_client)


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_never_returns_more_than_result_limit():
    client = _client_with(total_pages=10)

    results = await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=25,
    )

    assert len(results) == 25


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_stops_when_fewer_pages_available_than_the_limit():
    client = _client_with(total_pages=1)

    results = await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=100,
    )

    assert len(results) == 20  # one page's worth, never padded to the limit
