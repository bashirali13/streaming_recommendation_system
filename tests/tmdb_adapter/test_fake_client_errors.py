"""Adapter test: FakeTmdbClient's injectable failure modes yield a
TmdbAdapterError whose .error is a well-formed TmdbErrorInfo -- the same
shape a CandidatePool.error field expects -- never a crash, never a
fabricated candidate (FR-027).
"""

import pytest

from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.tmdb.client import TmdbAdapterError
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["timeout", "http_error", "malformed_response"])
async def test_discover_failure_mode_raises_typed_error(failure_mode):
    client = FakeTmdbClient(failure_mode=failure_mode)

    with pytest.raises(TmdbAdapterError) as exc_info:
        await client.discover(
            media_type=MediaType.MOVIE,
            region="US",
            provider_names=[],
            included_genres=[],
            excluded_genres=[],
            vibe_keywords=[],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=10,
        )

    assert exc_info.value.error.kind == failure_mode


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_caught_error_wraps_into_a_valid_empty_candidate_pool():
    client = FakeTmdbClient(failure_mode="timeout")

    try:
        await client.discover(
            media_type=MediaType.MOVIE,
            region="US",
            provider_names=[],
            included_genres=[],
            excluded_genres=[],
            vibe_keywords=[],
            year_min=None,
            year_max=None,
            runtime_max_minutes=None,
            result_limit=10,
        )
        pytest.fail("expected TmdbAdapterError")
    except TmdbAdapterError as exc:
        pool = CandidatePool(candidates=[], retry_number=0, error=exc.error)

    assert pool.candidates == []
    assert pool.error.kind == "timeout"


@pytest.mark.tmdb_adapter
@pytest.mark.asyncio
async def test_no_failure_mode_returns_results_without_raising():
    client = FakeTmdbClient(
        discover_results={"movie": [{"id": 1, "title": "A", "vote_average": 7.0}]}
    )

    results = await client.discover(
        media_type=MediaType.MOVIE,
        region="US",
        provider_names=[],
        included_genres=[],
        excluded_genres=[],
        vibe_keywords=[],
        year_min=None,
        year_max=None,
        runtime_max_minutes=None,
        result_limit=10,
    )

    assert results == [{"id": 1, "title": "A", "vote_average": 7.0}]
