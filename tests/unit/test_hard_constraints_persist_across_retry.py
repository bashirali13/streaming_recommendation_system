"""Unit test: excluded_genres and season_count_max (once added to
hard_override_fields) are byte-for-byte identical between the
retry_number=0 and retry_number=1 DiscoveryQuery (FR-010).
"""

from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.contracts.enums import MediaType, RelaxableConstraint
from streaming_discovery.contracts.preference_profile import PreferenceProfile


def _orchestrator() -> Orchestrator:
    class _Unused:
        async def run(self, *args, **kwargs):
            raise NotImplementedError

    return Orchestrator(
        preference_agent=_Unused(), discovery_agent=_Unused(), region="US", result_limit=20
    )


def test_excluded_genres_and_season_count_max_survive_relaxation_unchanged():
    profile = PreferenceProfile(
        media_type=MediaType.TV,
        genres=["Mystery"],
        excluded_genres=["Crime"],
        season_count_max=3,
        hard_override_fields=["season_count_max"],
        year_min=2015,
    )
    orchestrator = _orchestrator()

    [initial_query] = orchestrator.build_discovery_queries(profile, retry_number=0)
    [retried_query] = orchestrator.build_discovery_queries(
        profile, retry_number=1, relaxed_constraint=RelaxableConstraint.YEAR_RANGE
    )

    assert initial_query.excluded_genres == retried_query.excluded_genres == ["Crime"]
    assert initial_query.season_count_max == retried_query.season_count_max == 3
    assert initial_query.media_type == retried_query.media_type == MediaType.TV
    # The relaxed field itself is the only thing that legitimately differs.
    assert initial_query.year_min == 2015
    assert retried_query.year_min is None
