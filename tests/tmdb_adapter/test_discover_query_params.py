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
        excluded_keywords=[],
        vibe_keywords=[],
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
        excluded_keywords=[],
        vibe_keywords=[],
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
        excluded_keywords=[],
        vibe_keywords=[],
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
        excluded_keywords=[],
        vibe_keywords=[],
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
        excluded_keywords=[],
        vibe_keywords=[],
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
            excluded_keywords=[],
            vibe_keywords=[],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=20,
        )

    assert provider_fetch_count == 1


_KEYWORD_RESPONSES = {
    "fairy tale": {"results": [{"id": 100, "name": "fairy tale"}]},
    "quirky humor": {"results": []},
    "quirky": {"results": [{"id": 200, "name": "quirky"}]},
    "humor": {"results": []},
    "Marvel": {"results": [{"id": 300, "name": "marvel comic"}]},
    "DC": {"results": [{"id": 400, "name": "dc comics"}]},
}


def _keyword_handler(request: httpx.Request) -> httpx.Response:
    query = request.url.params.get("query", "")
    return httpx.Response(200, json=_KEYWORD_RESPONSES.get(query, {"results": []}))


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_resolves_vibe_keywords_via_the_keyword_search_endpoint():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return _keyword_handler(request)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=["fairy tale"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_keywords"] == "100"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_falls_back_to_per_word_keyword_search_on_a_phrase_miss():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return _keyword_handler(request)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=["quirky humor"],  # the whole phrase has no match
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    # "quirky" resolves even though the full phrase and "humor" don't.
    assert captured_params["with_keywords"] == "200"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_omits_with_keywords_when_nothing_resolves():
    """Unlike providers, vibe_keywords are always soft (data-model.md):
    a descriptor with no TMDB keyword match is dropped, not sent through
    or failed closed.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return httpx.Response(200, json={"results": []})
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=["something nobody has ever tagged"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "with_keywords" not in captured_params


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_caches_keyword_searches_across_calls():
    search_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_count
        if "/search/keyword" in str(request.url):
            search_count += 1
            return _keyword_handler(request)
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    for _ in range(3):
        await client.discover(
            media_type=MediaType.MOVIE,
            region="US",
            provider_names=[],
            included_genres=[],
            excluded_genres=[],
            excluded_keywords=[],
            vibe_keywords=["fairy tale"],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=20,
        )

    assert search_count == 1


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_resolves_excluded_keywords_to_without_keywords():
    """T091: a franchise/studio-level exclusion ("not Marvel or DC")
    resolves via the same keyword-search mechanism as vibe_keywords, but
    feeds without_keywords instead of with_keywords.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return _keyword_handler(request)
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=["Marvel", "DC"],
        vibe_keywords=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    ids = set(captured_params["without_keywords"].split("|"))
    assert ids == {"300", "400"}
    assert "with_keywords" not in captured_params


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_omits_without_keywords_when_nothing_resolves():
    """Unlike providers, an unresolved excluded_keywords entry doesn't
    fail the query closed at this layer -- defense-in-depth text
    matching (Discovery Agent, Recommendation Agent) is what upholds the
    hard-exclusion guarantee when TMDB's own keyword tagging can't.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return httpx.Response(200, json={"results": []})
        captured_params.update(dict(request.url.params))
        return _empty_discover_response(request)

    client = _client_with_handler(handler)

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=["Some Obscure Franchise Nobody Tagged"],
        vibe_keywords=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "without_keywords" not in captured_params
