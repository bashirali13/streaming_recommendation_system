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
        languages=[],
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
        languages=[],
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
        languages=[],
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
        languages=[],
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
        languages=[],
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
            languages=[],
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
        languages=[],
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
        languages=[],
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
        languages=[],
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
            languages=[],
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
        languages=[],
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
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "without_keywords" not in captured_params


_MULTI_KEYWORD_RESPONSES = {
    "road trip": {"results": [{"id": 500, "name": "road trip"}]},
    "found family": {"results": [{"id": 600, "name": "found family"}]},
}


def _multi_keyword_handler(request: httpx.Request) -> httpx.Response:
    query = request.url.params.get("query", "")
    return httpx.Response(200, json=_MULTI_KEYWORD_RESPONSES.get(query, {"results": []}))


def _ladder_client(sizes: dict[str, int]):
    """A client whose discover endpoint returns `sizes[mode]` distinct
    results, where mode is "and" (comma keywords), "or" (a single id or
    pipe keywords) or "none" (no keyword filter). Returns (client, calls).
    """
    calls: list[dict] = []
    base = {"and": 1000, "or": 2000, "none": 3000}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return _multi_keyword_handler(request)
        params = dict(request.url.params)
        calls.append(params)
        keywords = params.get("with_keywords")
        mode = "none" if keywords is None else ("and" if "," in keywords else "or")
        results = [{"id": base[mode] + i, "title": f"{mode}-{i}"} for i in range(sizes[mode])]
        return httpx.Response(200, json={"page": 1, "total_pages": 1, "results": results})

    return _client_with_handler(handler), calls


async def _discover(client, vibe_keywords):
    return await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=vibe_keywords,
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_keywords_are_required_together_when_that_leaves_enough_results():
    """T100: a compound request ("road trip and found family") should
    require all of what was named, as long as that still leaves a usable
    pool (T111)."""
    client, calls = _ladder_client({"and": 12, "or": 12, "none": 12})

    results = await _discover(client, ["road trip", "found family"])

    assert len(calls) == 1
    assert set(calls[0]["with_keywords"].split(",")) == {"500", "600"}
    assert len(results) == 12


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_widens_to_any_keyword_when_requiring_all_leaves_too_few():
    client, calls = _ladder_client({"and": 3, "or": 12, "none": 12})

    results = await _discover(client, ["road trip", "found family"])

    assert len(calls) == 2
    assert set(calls[1]["with_keywords"].split("|")) == {"500", "600"}
    assert all(r["title"].startswith("or-") for r in results)


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_drops_the_keyword_filter_when_even_any_keyword_leaves_too_few():
    """T111: TMDB's keyword tagging is sparse, so a keyword may put its
    best matches first but must never leave the user with a handful of
    results. The narrow matches stay at the front of the wide pool."""
    client, calls = _ladder_client({"and": 0, "or": 2, "none": 20})

    results = await _discover(client, ["road trip", "found family"])

    assert len(calls) == 3
    assert "with_keywords" not in calls[2]
    assert [r["title"] for r in results[:2]] == ["or-0", "or-1"]
    assert len(results) == 20
    assert len({r["id"] for r in results}) == 20


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_a_single_keyword_that_leaves_too_few_is_dropped_too():
    client, calls = _ladder_client({"and": 0, "or": 1, "none": 15})

    results = await _discover(client, ["road trip"])

    assert len(calls) == 2
    assert calls[0]["with_keywords"] == "500"
    assert "with_keywords" not in calls[1]
    assert results[0]["title"] == "or-0"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_a_single_keyword_with_enough_results_is_used_directly():
    client, calls = _ladder_client({"and": 0, "or": 12, "none": 12})

    await _discover(client, ["road trip"])

    assert len(calls) == 1
    assert calls[0]["with_keywords"] == "500"


_LANGUAGES_RESPONSE = [
    {"iso_639_1": "en", "english_name": "English", "name": "English"},
    {"iso_639_1": "ko", "english_name": "Korean", "name": "한국어/조선말"},
    {"iso_639_1": "es", "english_name": "Spanish", "name": "Español"},
    {"iso_639_1": "ja", "english_name": "Japanese", "name": "日本語"},
]


def _languages_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_LANGUAGES_RESPONSE)


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_resolves_a_language_name_to_its_iso_code():
    """T104: languages was previously a dead field -- captured by the
    Preference Agent but never passed to discover() at all. Resolved via
    TMDB's own language list, the same exact-then-substring approach
    `_match_provider` uses for providers.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/configuration/languages" in str(request.url):
            return _languages_handler(request)
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
        vibe_keywords=[],
        languages=["Korean"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_original_language"] == "ko"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_uses_only_the_first_resolvable_language():
    """with_original_language accepts exactly one ISO code (confirmed
    live -- unlike with_genres/with_keywords/with_companies, it does not
    support comma/pipe multi-value syntax), so a second stated language
    is never sent even though `languages` is a list.
    """
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/configuration/languages" in str(request.url):
            return _languages_handler(request)
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
        vibe_keywords=[],
        languages=["Korean", "Japanese"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_original_language"] == "ko"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_skips_an_unresolvable_language_and_tries_the_next_one():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/configuration/languages" in str(request.url):
            return _languages_handler(request)
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
        vibe_keywords=[],
        languages=["Klingon", "Spanish"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_original_language"] == "es"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_omits_with_original_language_when_nothing_resolves():
    """Unlike providers, an unresolvable language is soft-dropped
    (data-model.md), not failed closed."""
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/configuration/languages" in str(request.url):
            return _languages_handler(request)
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
        vibe_keywords=[],
        languages=["Klingon"],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "with_original_language" not in captured_params


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_caches_the_language_list_across_calls():
    fetch_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetch_count
        if "/configuration/languages" in str(request.url):
            fetch_count += 1
            return _languages_handler(request)
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
            vibe_keywords=[],
            languages=["Korean"],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=20,
        )

    assert fetch_count == 1


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_restricts_provider_matches_to_flatrate_offers():
    """T109: `with_watch_providers` alone matches ANY offer type (rent,
    buy, free, ads). Everything downstream -- FR-019's display, the
    "included with a subscription" meaning of naming a service --
    is flatrate-only, so a title only rentable on a named service must not
    pass the discover-time filter and then show up with no "Available on"
    line at all.
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
        provider_names=["Netflix"],
        included_genres=[],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=[],
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert captured_params["with_watch_monetization_types"] == "flatrate"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_discover_sends_no_monetization_filter_when_no_provider_was_named():
    captured_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
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
        vibe_keywords=[],
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert "with_watch_monetization_types" not in captured_params


async def _discover_tv(client, *, genres, vibe_keywords=()):
    return await client.discover(
        media_type=MediaType.TV,
        region="US",
        provider_names=[],
        included_genres=list(genres),
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=list(vibe_keywords),
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )


def _capturing_client():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/keyword" in str(request.url):
            return _multi_keyword_handler(request)
        calls.append(dict(request.url.params))
        results = [{"id": i} for i in range(12)]
        return httpx.Response(200, json={"page": 1, "total_pages": 1, "results": results})

    return _client_with_handler(handler), calls


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_tv_science_fiction_is_sent_as_the_combined_tv_genre():
    client, calls = _capturing_client()

    await _discover_tv(client, genres=["Science Fiction"])

    assert calls[0]["with_genres"] == "10765"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_a_genre_tv_lacks_is_sent_as_its_keyword_not_dropped():
    """T113: "a romance TV series" used to send no genre at all, so the
    request matched every kind of show."""
    client, calls = _capturing_client()

    await _discover_tv(client, genres=["Romance"])

    assert calls[0]["with_keywords"] == "9840"
    assert "with_genres" not in calls[0]


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_real_tv_genres_and_keyword_stand_ins_are_combined():
    client, calls = _capturing_client()

    await _discover_tv(client, genres=["Comedy", "Romance"])

    assert calls[0]["with_genres"] == "35"
    assert calls[0]["with_keywords"] == "9840"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_the_genre_keyword_takes_precedence_over_soft_theme_keywords_on_tv():
    """TMDB's `with_keywords` takes one separator per call, so the stated
    genre wins and the (soft) theme keywords stay ranking-only for TV."""
    client, calls = _capturing_client()

    await _discover_tv(client, genres=["Romance"], vibe_keywords=["road trip"])

    assert len(calls) == 1
    assert calls[0]["with_keywords"] == "9840"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_movies_never_use_genre_keyword_stand_ins():
    client, calls = _capturing_client()

    await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=["Romance"],
        excluded_genres=[],
        excluded_keywords=[],
        vibe_keywords=[],
        languages=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=20,
    )

    assert calls[0]["with_genres"] == "10749"
    assert "with_keywords" not in calls[0]
