"""Unit test (T087): DiscoveryAgent passes DiscoveryQuery.vibe_keywords
through to the TMDB client's discover() call -- the wiring that makes a
vibe-only request (no genre, no liked titles) actually searchable,
instead of the query having nothing but provider/region to filter on.
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_keywords_reach_the_tmdb_client():
    tmdb = FakeTmdbClient(discover_results={"movie": []})
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE,
        region="US",
        retry_number=0,
        vibe_keywords=["fairy tale", "quirky humor"],
    )

    await agent.run(query)

    assert len(tmdb.discover_calls) == 1
    assert tmdb.discover_calls[0]["vibe_keywords"] == ["fairy tale", "quirky humor"]
