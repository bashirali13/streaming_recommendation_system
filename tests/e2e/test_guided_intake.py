"""E2E test: a guided-intake session with format/mood answered and
providers/exclusions skipped shows only the answered fields at
confirmation, and a user correction at that step is reflected in the
PreferenceProfile used for discovery (spec.md US6 Acceptance Scenarios
1-2; quickstart.md scenario 6).
"""

import pytest

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.agents.preference_agent import PreferenceAgent, build_preference_prompt
from streaming_discovery.agents.recommendation_agent import (
    RecommendationAgent,
    _RationaleOutput,
    build_rationale_prompt,
)
from streaming_discovery.cli.intake import run_guided_cli
from streaming_discovery.contracts.enums import MediaType
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.fake_provider import FakeModelProvider
from streaming_discovery.tmdb.fake_client import FakeTmdbClient

# format and mood_and_interests answered; services/exclusions/optional_constraints skipped.
_INTAKE_ANSWERS = {
    "format": "movie",
    "services": None,
    "mood_and_interests": "something uplifting",
    "exclusions": None,
    "optional_constraints": None,
}
_INITIAL_PROFILE = PreferenceProfile(media_type=MediaType.MOVIE, tone_descriptors=["uplifting"])
_CORRECTED_PROFILE = PreferenceProfile(media_type=MediaType.TV, tone_descriptors=["uplifting"])

_RAW_MOVIE = {
    "id": 1,
    "title": "Bright Days",
    "overview": "An uplifting story about second chances.",
    "genre_ids": [18],
    "release_date": "2020-01-01",
    "vote_average": 7.0,
}
_DETAILS = {
    1: {
        **_RAW_MOVIE,
        "genres": [{"id": 18, "name": "Drama"}],
        "runtime": 100,
        "watch/providers": {"results": {}},
        "keywords": {"keywords": [{"id": 1, "name": "uplifting"}]},
    }
}


def _scripted_io(inputs: list[str]):
    it = iter(inputs)
    printed: list[str] = []
    return (lambda _prompt="": next(it, "")), printed.append, printed


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_guided_intake_shows_only_answered_fields_and_applies_a_correction():
    prompt = build_preference_prompt(None, _INTAKE_ANSWERS)
    preference_provider = FakeModelProvider(responses={prompt: _INITIAL_PROFILE})
    recommendation_provider = FakeModelProvider()
    rationale_prompt = build_rationale_prompt(
        _CORRECTED_PROFILE,
        title="Bright Days",
        overview=_RAW_MOVIE["overview"],
        weak_evidence=False,
    )
    recommendation_provider._responses[rationale_prompt] = _RationaleOutput(
        text="Bright Days is an uplifting pick."
    )

    orchestrator = Orchestrator(
        preference_agent=PreferenceAgent(provider=preference_provider, max_additional_attempts=2),
        discovery_agent=DiscoveryAgent(
            tmdb_client=FakeTmdbClient(
                discover_results={"tv": [_RAW_MOVIE]}, detail_results=_DETAILS
            )
        ),
        recommendation_agent=RecommendationAgent(
            provider=recommendation_provider, max_additional_attempts=2
        ),
        region="US",
        result_limit=20,
    )

    # Scripted terminal session: skip the free-text prompt, answer format
    # and mood, skip the rest, then correct media_type at confirmation.
    input_func, print_func, printed = _scripted_io(
        [
            "",  # no free text -- go straight to guided questions
            "movie",  # format
            "",  # services (skipped)
            "something uplifting",  # mood_and_interests
            "",  # exclusions (skipped)
            "",  # optional_constraints (skipped)
            "media_type=tv",  # correction at confirmation
        ]
    )

    await run_guided_cli(orchestrator, input_func=input_func, print_func=print_func)

    joined_output = "\n".join(printed)
    assert "Format: movie" in joined_output
    assert "Tone: uplifting" in joined_output
    assert "Providers:" not in joined_output  # skipped fields never shown
    assert "Bright Days" in joined_output  # final rendered recommendation
