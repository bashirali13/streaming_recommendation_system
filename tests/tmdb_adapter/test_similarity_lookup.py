"""Adapter test: FakeTmdbClient's similarity-lookup path (title -> id
resolution via search_title, then similar-title results via similar)
returns the expected fixture set (User Story 3).
"""

import pytest

from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_title_resolves_to_id_then_similar_returns_the_fixture_set():
    client = FakeTmdbClient(
        title_ids={"Arrival": 329865},
        similar_results={329865: [{"id": 1, "title": "Contact"}, {"id": 2, "title": "Signs"}]},
    )

    seed_id = await client.search_title(media_type=MediaType.MOVIE, title="Arrival")
    assert seed_id == 329865

    similar = await client.similar(media_type=MediaType.MOVIE, tmdb_id=seed_id, result_limit=10)
    assert [item["title"] for item in similar] == ["Contact", "Signs"]


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_unknown_title_resolves_to_none():
    client = FakeTmdbClient(title_ids={})

    seed_id = await client.search_title(media_type=MediaType.MOVIE, title="Nonexistent Movie")

    assert seed_id is None
