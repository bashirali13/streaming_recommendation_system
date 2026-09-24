"""Unit test (T115): "movies like Inception, only on Netflix, after 2015" used
to return titles from TMDB's /similar list alone -- an unfiltered list -- so
0 of 20 were on Netflix and 1 of 20 was after 2015. When the user also states
facts that list cannot honor (a service, a year range, a runtime, a language),
the pool now also includes a filtered discover query built from the seed's own
genres. A pure "like X" request still comes only from the similarity lookup
(spec.md US3).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


def _item(tmdb_id: int, title: str) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": "x",
        "genre_ids": [878],
        "release_date": "2018-01-01",
        "vote_average": 7.0,
    }


_SEED_DETAILS = {
    27205: {
        "genres": [
            {"id": 878, "name": "Science Fiction"},
            {"id": 28, "name": "Action"},
            {"id": 12, "name": "Adventure"},
        ]
    }
}


def _client() -> FakeTmdbClient:
    return FakeTmdbClient(
        title_ids={"Inception": 27205},
        similar_results={27205: [_item(1, "Similar One"), _item(2, "Similar Two")]},
        discover_results={"movie": [_item(10, "Filtered One"), _item(11, "Filtered Two")]},
        detail_results=_SEED_DETAILS,
    )


def _query(**kwargs) -> DiscoveryQuery:
    return DiscoveryQuery(
        media_type=MediaType.MOVIE,
        region="US",
        retry_number=0,
        similarity_seed_titles=["Inception"],
        **kwargs,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_stated_service_adds_a_filtered_pool_built_from_the_seed_genres():
    tmdb = _client()

    pool = await DiscoveryAgent(tmdb_client=tmdb).run(_query(provider_names=["Netflix"]))

    call = tmdb.discover_calls[-1]
    assert call["provider_names"] == ["Netflix"]
    assert call["included_genres"] == ["Science Fiction", "Action"]
    assert {c.title for c in pool.candidates} == {
        "Similar One",
        "Similar Two",
        "Filtered One",
        "Filtered Two",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_similar_titles_come_first():
    pool = await DiscoveryAgent(tmdb_client=_client()).run(_query(year_min=2016))

    assert [c.title for c in pool.candidates][:2] == ["Similar One", "Similar Two"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stated_genres_are_kept_instead_of_the_seed_genres():
    tmdb = _client()

    await DiscoveryAgent(tmdb_client=tmdb).run(
        _query(provider_names=["Netflix"], included_genres=["Thriller"])
    )

    assert tmdb.discover_calls[-1]["included_genres"] == ["Thriller"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_title_in_both_lists_appears_once():
    tmdb = FakeTmdbClient(
        title_ids={"Inception": 27205},
        similar_results={27205: [_item(1, "Both")]},
        discover_results={"movie": [_item(1, "Both"), _item(2, "Only Filtered")]},
        detail_results=_SEED_DETAILS,
    )

    pool = await DiscoveryAgent(tmdb_client=tmdb).run(_query(runtime_max_minutes=120))

    assert [c.title for c in pool.candidates] == ["Both", "Only Filtered"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_pure_like_x_request_uses_only_the_similarity_lookup():
    tmdb = _client()

    pool = await DiscoveryAgent(tmdb_client=tmdb).run(_query())

    assert tmdb.discover_calls == []
    assert {c.title for c in pool.candidates} == {"Similar One", "Similar Two"}
