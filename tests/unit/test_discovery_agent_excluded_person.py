"""Unit test (T107): the Discovery Agent rejects a finalist candidate
whose credits (cast or crew) include an excluded person -- TMDB's
/discover endpoints have no without_people equivalent (confirmed live),
so this can't be a discover() query param the way excluded_keywords/
excluded_genres are; it has to be a defense-in-depth check against the
detail-call credits data, the same shape as T095's production_companies
check but for a real person rather than a studio.
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.contracts.discovery_query import DiscoveryQuery
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

_STATHAM_MOVIE = {
    "id": 1,
    "title": "The Meg",
    "overview": "A deep sea submersible pilot must save a group of scientists from a shark.",
    "genre_ids": [28],
    "release_date": "2018-08-10",
    "vote_average": 7.0,
}
_UNRELATED_MOVIE = {
    "id": 2,
    "title": "Widows",
    "overview": "A group of women pull off a heist planned by their dead husbands.",
    "genre_ids": [80],
    "release_date": "2018-11-16",
    "vote_average": 7.2,
}
_DETAILS = {
    1: {
        **_STATHAM_MOVIE,
        "genres": [{"id": 28, "name": "Action"}],
        "runtime": 113,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
        "credits": {
            "cast": [{"id": 976, "name": "Jason Statham"}, {"id": 12345, "name": "Li Bingbing"}],
            "crew": [],
        },
    },
    2: {
        **_UNRELATED_MOVIE,
        "genres": [{"id": 80, "name": "Crime"}],
        "runtime": 129,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": []},
        "credits": {"cast": [{"id": 999, "name": "Viola Davis"}], "crew": []},
    },
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_excluded_person_in_the_cast_is_rejected():
    tmdb = FakeTmdbClient(
        discover_results={"movie": [_STATHAM_MOVIE, _UNRELATED_MOVIE]},
        detail_results=_DETAILS,
        person_ids={"Jason Statham": 976},
    )
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE, region="US", retry_number=0, excluded_keywords=["Jason Statham"]
    )

    pool = await agent.run(query)

    titles = {c.title for c in pool.candidates}
    assert "The Meg" not in titles
    assert "Widows" in titles


@pytest.mark.unit
@pytest.mark.asyncio
async def test_excluded_person_in_the_crew_is_also_rejected():
    """Covers a director/crew exclusion, not just an actor -- "no
    Christopher Nolan movies" should work the same way "no Jason Statham
    movies" does."""
    details = {
        1: {
            **_STATHAM_MOVIE,
            "genres": [{"id": 28, "name": "Action"}],
            "runtime": 113,
            "watch/providers": {"results": {}},
            "keywords": {"keywords": []},
            "credits": {
                "cast": [],
                "crew": [{"id": 525, "name": "Christopher Nolan", "job": "Director"}],
            },
        },
        2: _DETAILS[2],
    }
    tmdb = FakeTmdbClient(
        discover_results={"movie": [_STATHAM_MOVIE, _UNRELATED_MOVIE]},
        detail_results=details,
        person_ids={"Christopher Nolan": 525},
    )
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(
        media_type=MediaType.MOVIE,
        region="US",
        retry_number=0,
        excluded_keywords=["Christopher Nolan"],
    )

    pool = await agent.run(query)

    titles = {c.title for c in pool.candidates}
    assert "The Meg" not in titles
    assert "Widows" in titles


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_excluded_keywords_means_no_person_resolution_call():
    """excluded_keywords is also used for non-person exclusions
    (franchises, genres-that-don't-fit); when it's empty, no
    resolve_person_ids call should happen at all."""
    tmdb = FakeTmdbClient(
        discover_results={"movie": [_UNRELATED_MOVIE]},
        detail_results={2: _DETAILS[2]},
    )
    agent = DiscoveryAgent(tmdb_client=tmdb)
    query = DiscoveryQuery(media_type=MediaType.MOVIE, region="US", retry_number=0)

    pool = await agent.run(query)

    assert [c.title for c in pool.candidates] == ["Widows"]
