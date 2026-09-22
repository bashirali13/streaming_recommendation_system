"""Unit test: Settings.demo_mode actually switches build_orchestrator to
fixture-backed fakes (NFR-004, FR-025) -- this field has existed since
Foundational but nothing branched on it until now, the same class of gap
UserSessionState was before Polish wired it in too.
"""

import pytest

from streaming_discovery.cli.output import build_orchestrator
from streaming_discovery.config import Settings
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.demo import DEMO_REQUEST
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient


async def _silent_confirm(profile):
    return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_demo_mode_runs_end_to_end_with_no_credentials():
    settings = Settings(
        tmdb_api_token="unused",
        openrouter_api_key="unused",
        model_name="unused",
        demo_mode=True,
    )

    orchestrator = build_orchestrator(settings)
    package = await orchestrator.run_single_attempt(
        raw_user_input=DEMO_REQUEST, confirm=_silent_confirm
    )

    # A real recommendation came back, produced entirely by fakes.
    assert package.best_match is not None
    assert package.applied_constraints.media_type is MediaType.MOVIE


def test_demo_mode_off_still_builds_real_clients():
    settings = Settings(tmdb_api_token="t", openrouter_api_key="k", model_name="m", demo_mode=False)

    orchestrator = build_orchestrator(settings)

    assert not isinstance(orchestrator._discovery_agent._tmdb, FakeTmdbClient)
    assert not isinstance(orchestrator._preference_agent._provider, FakeModelProvider)
