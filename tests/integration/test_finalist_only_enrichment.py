"""Integration test: the Discovery Agent's detail-level fetch is called
exactly once per candidate surviving hard filtering, and zero times for
candidates eliminated by hard filtering, for a raw pool larger than the
surviving set (FR-029).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


def _raw_candidate(tmdb_id: int, title: str, genre_ids: list[int]) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": "An overview.",
        "genre_ids": genre_ids,
        "release_date": "2020-01-01",
        "vote_average": 7.0,
    }


def _raw_details(tmdb_id: int, title: str, genres: list[dict]) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "overview": "An overview.",
        "genres": genres,
        "release_date": "2020-01-01",
        "vote_average": 7.0,
        "runtime": 100,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_details_fetched_only_for_survivors_of_hard_filtering():
    # 18 = Drama (allowed), 27 = Horror (excluded by the query below).
    raw_pool = [
        _raw_candidate(1, "Keep A", [18]),
        _raw_candidate(2, "Excluded (horror)", [27]),
        _raw_candidate(3, "Keep B", [18]),
        _raw_candidate(4, "Excluded (disliked title)", [18]),
        _raw_candidate(5, "Keep C", [18]),
    ]
    fake_client = FakeTmdbClient(
        discover_results={"movie": raw_pool},
        detail_results={
            1: _raw_details(1, "Keep A", [{"id": 18, "name": "Drama"}]),
            3: _raw_details(3, "Keep B", [{"id": 18, "name": "Drama"}]),
            5: _raw_details(5, "Keep C", [{"id": 18, "name": "Drama"}]),
        },
    )
    agent = DiscoveryAgent(tmdb_client=fake_client)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE,
        region="US",
        excluded_genres=["Horror"],
        exclude_titles=["Excluded (disliked title)"],
        retry_number=0,
        result_limit=20,
    )

    pool = await agent.run(query)

    assert fake_client.details_call_count == 3  # not 5 (the full raw pool)
    returned_ids = {c.tmdb_id for c in pool.candidates}
    assert returned_ids == {1, 3, 5}
