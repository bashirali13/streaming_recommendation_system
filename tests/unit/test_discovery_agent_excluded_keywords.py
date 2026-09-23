"""Unit test (T091): the Discovery Agent's bulk-item hard filter also
rejects a candidate whose title/overview literally mentions an excluded
keyword -- defense-in-depth alongside TMDB's own `without_keywords`
(client.py), since TMDB's keyword tagging isn't guaranteed complete for
every excluded concept (e.g. not every Marvel movie is necessarily
tagged with a "marvel" keyword). Rejected before a detail() call is
spent on it, mirroring the existing excluded_genres defensive re-check.
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

_MARVEL_MOVIE = {
    "id": 1,
    "title": "Spider-Man: Into the Spider-Verse",
    "overview": "Miles Morales becomes the Marvel Spider-Man of his reality.",
    "genre_ids": [16],
    "release_date": "2018-12-14",
    "vote_average": 8.4,
}
_UNRELATED_MOVIE = {
    "id": 2,
    "title": "My Hero Academia: Heroes Rising",
    "overview": "Young heroes protect an island under attack.",
    "genre_ids": [16],
    "release_date": "2019-12-20",
    "vote_average": 7.7,
}
_DETAILS = {
    2: {
        **_UNRELATED_MOVIE,
        "genres": [{"id": 16, "name": "Animation"}],
        "runtime": 105,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
    }
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_excluded_keyword_mentioned_in_title_or_overview_is_rejected_before_a_detail_call():
    tmdb = FakeTmdbClient(
        discover_results={"movie": [_MARVEL_MOVIE, _UNRELATED_MOVIE]}, detail_results=_DETAILS
    )
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE, region="US", retry_number=0, excluded_keywords=["Marvel"]
    )

    pool = await agent.run(query)

    titles = {c.title for c in pool.candidates}
    assert "Spider-Man: Into the Spider-Verse" not in titles
    assert "My Hero Academia: Heroes Rising" in titles
    assert tmdb.details_call_count == 1  # only the surviving candidate got a detail() call


# A real TMDB overview almost never names the parent studio/publisher, and
# TMDB's own keyword tagging for a franchise like "Marvel" is inconsistent
# (empirically confirmed: Spider-Man: Into the Spider-Verse's real TMDB
# keywords are ["superhero", "based on comic", "aftercreditsstinger",
# "alternate universe"] -- no "marvel" at all -- while its real
# production_companies includes "Marvel Entertainment"). This fixture
# matches that real shape: neither title nor overview nor keywords mention
# "Marvel", so only a production_companies check can catch it.
_REALISTIC_MARVEL_MOVIE = {
    "id": 3,
    "title": "Into the Spider-Verse",
    "overview": "A teenager gains extraordinary powers and teams up with heroes from other worlds.",
    "genre_ids": [16],
    "release_date": "2018-12-14",
    "vote_average": 8.4,
}
_REALISTIC_DETAILS = {
    3: {
        **_REALISTIC_MARVEL_MOVIE,
        "genres": [{"id": 16, "name": "Animation"}],
        "runtime": 117,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": [{"id": 1, "name": "superhero"}, {"id": 2, "name": "multiverse"}]},
        "production_companies": [
            {"id": 5, "name": "Sony Pictures Animation"},
            {"id": 6, "name": "Marvel Entertainment"},
        ],
    }
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_excluded_keyword_matching_only_a_production_company_name_is_still_rejected():
    """T095: neither the primary text-match check (title/overview) nor
    TMDB's own keyword tagging can be relied on to name the excluded
    franchise -- production_companies is the reliable signal.
    """
    tmdb = FakeTmdbClient(
        discover_results={"movie": [_REALISTIC_MARVEL_MOVIE]}, detail_results=_REALISTIC_DETAILS
    )
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE, region="US", retry_number=0, excluded_keywords=["Marvel"]
    )

    pool = await agent.run(query)

    assert pool.candidates == []
