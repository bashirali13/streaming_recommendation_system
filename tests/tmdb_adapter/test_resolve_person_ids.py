"""Adapter test (T107): resolving a free-text person name (actor,
director) to a TMDB person id via /search/person, for the actor/
person-exclusion enforcement path -- TMDB's /discover endpoints have no
without_people equivalent (confirmed live), so this can't be a discover()
query param the way excluded_keywords/excluded_genres are; it's a
separate resolution the Discovery Agent uses to check finalist
candidates' credits instead.
"""

import httpx
import pytest

from streaming_discovery.tmdb.client import RealTmdbClient


def _client_with_handler(handler) -> RealTmdbClient:
    http_client = httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(handler)
    )
    return RealTmdbClient(http_client=http_client)


_PERSON_RESPONSES = {
    "Jason Statham": {"results": [{"id": 976, "name": "Jason Statham"}]},
    "Christopher Nolan": {"results": [{"id": 525, "name": "Christopher Nolan"}]},
}


def _person_handler(request: httpx.Request) -> httpx.Response:
    query = request.url.params.get("query", "")
    return httpx.Response(200, json=_PERSON_RESPONSES.get(query, {"results": []}))


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_resolve_person_ids_resolves_a_known_name():
    client = _client_with_handler(_person_handler)

    ids = await client.resolve_person_ids(["Jason Statham"])

    assert ids == [976]


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_resolve_person_ids_resolves_multiple_names():
    client = _client_with_handler(_person_handler)

    ids = await client.resolve_person_ids(["Jason Statham", "Christopher Nolan"])

    assert set(ids) == {976, 525}


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_resolve_person_ids_drops_an_unresolvable_name():
    """Soft, like the other excluded_keywords resolution layers
    (T091/T106) -- an unresolvable name doesn't fail closed here, since
    the Discovery Agent's text-match check is the layer of last resort
    for a hard exclusion that can't be resolved."""
    client = _client_with_handler(_person_handler)

    ids = await client.resolve_person_ids(["Jason Statham", "Not A Real Person"])

    assert ids == [976]


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_resolve_person_ids_caches_searches_across_calls():
    search_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_count
        search_count += 1
        return _person_handler(request)

    client = _client_with_handler(handler)

    for _ in range(3):
        await client.resolve_person_ids(["Jason Statham"])

    assert search_count == 1


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_resolve_person_ids_with_empty_input_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make any request for empty input")

    client = _client_with_handler(handler)

    ids = await client.resolve_person_ids([])

    assert ids == []
