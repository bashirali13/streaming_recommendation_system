"""Adapter test (T086): `RealTmdbClient.discover()` must send TMDB the
query parameters it actually understands -- numeric genre and provider
ids, not the names carried on `DiscoveryQuery` (FR-009/FR-010/FR-029).
Passing names straight through (the previous behavior) silently
returned zero real candidates for any request naming a provider or a
genre, since TMDB's discover endpoint does not match on name strings.
"""

import httpx
import pytest

from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.client import RealTmdbClient

_PROVIDERS_RESPONSE = {
    "results": [
        {"provider_id": 8, "provider_name": "Netflix"},
        {"provider_id": 9, "provider_name": "Amazon Prime Video"},
        {"provider_id": 350, "provider_name": "Apple TV Plus"},
        {"provider_id": 2, "provider_name": "Apple TV"},
    ]
}


def _client_with_handler(handler) -> RealTmdbClient:
    http_client = httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(handler)
    )
    return RealTmdbClient(http_client=http_client)


def _empty_discover_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"page": 1, "total_pages": 1, "results": []})


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_sends_numeric_genre_ids_not_names():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/watch/providers/" in str(request.url):
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=["Comedy"],
        excluded_genres=["Horror"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_genres"] == "35"
    assert captured_params["without_genres"] == "27"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_drops_an_unrecognized_genre_name_rather_than_sending_it():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/watch/providers/" in str(request.url):
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=["Not A Real Genre"],
        excluded_genres=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "with_genres" not in captured_params


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_resolves_provider_names_to_ids_via_the_watch_providers_endpoint():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/watch/providers/" in str(request.url):
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=["Netflix", "Prime"],
        included_genres=[],
        excluded_genres=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    ids = set(captured_params["with_watch_providers"].split("|"))
    assert ids == {"8", "9"}


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_apple_tv_resolves_via_substring_match():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/watch/providers/" in str(request.url):
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=["Apple TV"],
        included_genres=[],
        excluded_genres=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    # Exact match ("Apple TV") wins over the substring match ("Apple TV Plus").
    assert captured_params["with_watch_providers"] == "2"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_fails_closed_when_no_provider_name_resolves():
    """FR-010: a hard constraint (providers) that can't be verified must
    never be silently dropped -- an unresolvable provider name must
    still guarantee zero results, not an unfiltered query.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/watch/providers/" in str(request.url):
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=["Some Totally Unknown Service"],
        included_genres=[],
        excluded_genres=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "with_watch_providers" in captured_params
    assert captured_params["with_watch_providers"] not in ("", "8", "9", "350", "2")


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_caches_the_provider_list_across_calls():
    provider_fetch_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_fetch_count
        if "/watch/providers/" in str(request.url):
            provider_fetch_count += 1
            return httpx.Response(200, json=_PROVIDERS_RESPONSE)
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    for _ in range(3):
        await client.discover(
            media_type=MediaType.MOVIE,
            region="US",
            provider_names=["Netflix"],
            included_genres=[],
            excluded_genres=[],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=20,
        )

    assert provider_fetch_count == 1
