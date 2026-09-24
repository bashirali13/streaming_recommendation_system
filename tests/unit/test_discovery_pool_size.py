"""Unit test (T114): the candidate pool was 20 titles, so a request that
filters after fetching (a TV season cap, mood ranking) had little to choose
from -- "a crime TV series, no more than 3 seasons" left 2 survivors. The
pool is larger by default, and detail lookups run concurrently so the larger
pool does not make a search slower.
"""

import asyncio

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


class _Unused:
    async def run(self, *args, **kwargs):
        raise NotImplementedError


def test_the_default_pool_is_larger_than_twenty():
    orchestrator = Orchestrator(preference_agent=_Unused(), discovery_agent=_Unused(), region="US")
    profile = PreferenceProfile(media_type=MediaType.MOVIE, genres=["Drama"])

    [query] = orchestrator.build_discovery_queries(profile, retry_number=0)

    assert query.result_limit == 40


class _SlowDetails(FakeTmdbClient):
    """Records how many detail lookups are in flight at once."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.in_flight = 0
        self.max_in_flight = 0

    async def details(self, *, media_type, tmdb_id):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return await super().details(media_type=media_type, tmdb_id=tmdb_id)


def _item(tmdb_id: int) -> dict:
    return {
        "id": tmdb_id,
        "title": f"Title {tmdb_id}",
        "overview": "x",
        "genre_ids": [18],
        "release_date": "2020-01-01",
        "vote_average": 7.0,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detail_lookups_run_concurrently_and_keep_their_order():
    items = [_item(i) for i in range(1, 25)]
    tmdb = _SlowDetails(
        discover_results={"movie": items},
        detail_results={i["id"]: {"runtime": 100 + i["id"]} for i in items},
    )
    query = DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=0, result_limit=40)

    pool = await DiscoveryAgent(tmdb_client=tmdb).run(query)

    assert tmdb.max_in_flight > 1
    assert [c.tmdb_id for c in pool.candidates] == list(range(1, 25))
    assert pool.candidates[0].runtime_minutes == 101
